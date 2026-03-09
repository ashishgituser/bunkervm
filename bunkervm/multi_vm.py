"""
BunkerVM Multi-VM Manager — run multiple named sandbox instances.

Each VM gets its own:
  - Firecracker process
  - Vsock UDS socket
  - Rootfs working copy
  - SandboxClient

Usage:
    from bunkervm.multi_vm import VMPool

    pool = VMPool(config)
    pool.start("sandbox-1")
    pool.start("sandbox-2", cpus=4, memory=4096)

    client1 = pool.client("sandbox-1")
    client1.exec("echo hello from VM 1")

    pool.stop("sandbox-1")
    pool.stop_all()
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from .config import BunkerVMConfig
from .sandbox_client import SandboxClient
from .vm_manager import VMManager

logger = logging.getLogger("bunkervm.pool")

# Base CID for vsock — each VM gets base + index
_BASE_CID = 3
_BASE_PORT_OFFSET = 0


@dataclass
class VMInstance:
    """A running VM instance in the pool."""
    name: str
    manager: VMManager
    client: SandboxClient
    config: BunkerVMConfig
    index: int


class VMPool:
    """Manages multiple BunkerVM instances simultaneously.

    Each VM is identified by a unique name and gets isolated resources:
    - Separate vsock socket (e.g., /tmp/bunkervm-vm-<name>.sock)
    - Separate Firecracker API socket
    - Separate rootfs working copy
    - Separate vsock CID

    Args:
        base_config: Base configuration to clone for each VM.
        network: Enable TAP networking (default: True).
        max_vms: Maximum number of concurrent VMs (default: 10).
    """

    def __init__(
        self,
        base_config: BunkerVMConfig,
        network: bool = True,
        max_vms: int = 10,
    ):
        self._base_config = base_config
        self._network = network
        self._max_vms = max_vms
        self._instances: Dict[str, VMInstance] = {}
        self._lock = threading.Lock()
        self._next_index = 0

    @property
    def names(self) -> list[str]:
        """List names of all running VMs."""
        with self._lock:
            return list(self._instances.keys())

    @property
    def count(self) -> int:
        """Number of running VMs."""
        return len(self._instances)

    def start(
        self,
        name: str,
        cpus: Optional[int] = None,
        memory: Optional[int] = None,
        network: Optional[bool] = None,
    ) -> SandboxClient:
        """Start a new named VM instance.

        Args:
            name: Unique name for this VM (e.g., "sandbox-1", "data-analysis")
            cpus: Override vCPU count (default: from base config)
            memory: Override memory in MB (default: from base config)
            network: Override network setting (default: from pool)

        Returns:
            SandboxClient connected to the new VM.

        Raises:
            ValueError: If name already exists or pool is full.
        """
        with self._lock:
            if name in self._instances:
                raise ValueError(f"VM '{name}' already exists. Stop it first or use a different name.")

            if len(self._instances) >= self._max_vms:
                raise ValueError(
                    f"Pool limit reached ({self._max_vms} VMs). "
                    f"Stop an existing VM or increase max_vms."
                )

            index = self._next_index
            self._next_index += 1

        # Clone config with unique paths
        config = self._make_instance_config(name, index, cpus, memory)
        use_network = network if network is not None else self._network

        # Unique TAP device per VM (if networking enabled)
        if use_network:
            config.tap_device = f"tap{index}"
            # Unique subnet per VM to avoid IP conflicts
            config.host_ip = f"172.16.{index}.1"
            config.vm_ip = f"172.16.{index}.2"

        vm = VMManager(config, network=use_network)

        logger.info("Starting VM '%s' (CID=%d, cpus=%d, mem=%dMB)",
                     name, config.vsock_cid, config.vcpu_count, config.mem_size_mib)

        try:
            vm.start()
        except Exception as e:
            logger.error("Failed to start VM '%s': %s", name, e)
            raise

        # Create client
        client = SandboxClient(
            vsock_uds=config.vsock_uds_path,
            vsock_port=config.vm_port,
        )

        # Wait for health
        logger.info("Waiting for VM '%s' to become ready...", name)
        if client.wait_for_health(timeout=config.health_timeout):
            logger.info("VM '%s' ready (PID %d)", name, vm.fc_pid)
        else:
            logger.warning("VM '%s' health check timed out — may still be booting", name)

        instance = VMInstance(
            name=name,
            manager=vm,
            client=client,
            config=config,
            index=index,
        )

        with self._lock:
            self._instances[name] = instance

        return client

    def stop(self, name: str) -> None:
        """Stop and remove a named VM instance."""
        with self._lock:
            instance = self._instances.pop(name, None)

        if instance is None:
            logger.warning("VM '%s' not found in pool", name)
            return

        logger.info("Stopping VM '%s'...", name)
        try:
            instance.manager.stop()
        except Exception as e:
            logger.error("Error stopping VM '%s': %s", name, e)

        logger.info("VM '%s' stopped", name)

    def stop_all(self) -> None:
        """Stop all running VMs."""
        names = self.names
        logger.info("Stopping all VMs: %s", names)
        for name in names:
            self.stop(name)

    def restart(self, name: str) -> SandboxClient:
        """Restart a named VM with fresh rootfs."""
        with self._lock:
            instance = self._instances.get(name)
            if instance is None:
                raise ValueError(f"VM '{name}' not found")

        logger.info("Restarting VM '%s'...", name)
        instance.manager.restart()

        if instance.client.wait_for_health(timeout=instance.config.health_timeout):
            logger.info("VM '%s' restarted successfully", name)
        else:
            logger.warning("VM '%s' restart health check timed out", name)

        return instance.client

    def client(self, name: str) -> SandboxClient:
        """Get the SandboxClient for a named VM.

        Args:
            name: VM name.

        Returns:
            SandboxClient connected to the named VM.

        Raises:
            KeyError: If VM not found.
        """
        with self._lock:
            instance = self._instances.get(name)
            if instance is None:
                raise KeyError(
                    f"VM '{name}' not found. Running VMs: {list(self._instances.keys())}"
                )
            return instance.client

    def status(self, name: str) -> dict:
        """Get status info for a named VM."""
        with self._lock:
            instance = self._instances.get(name)
            if instance is None:
                raise KeyError(f"VM '{name}' not found")

        return {
            "name": name,
            "running": instance.manager.is_running(),
            "pid": instance.manager.fc_pid,
            "cpus": instance.config.vcpu_count,
            "memory_mb": instance.config.mem_size_mib,
            "vsock": instance.config.vsock_uds_path,
            "cid": instance.config.vsock_cid,
            "network": instance.config.tap_device if instance.manager._network else None,
            "vm_ip": instance.config.vm_ip if instance.manager._network else None,
        }

    def status_all(self) -> list[dict]:
        """Get status info for all VMs."""
        return [self.status(name) for name in self.names]

    def _make_instance_config(
        self,
        name: str,
        index: int,
        cpus: Optional[int],
        memory: Optional[int],
    ) -> BunkerVMConfig:
        """Create an isolated config copy for a VM instance."""
        import copy
        config = copy.deepcopy(self._base_config)

        # Unique vsock CID (must be unique per VM)
        config.vsock_cid = _BASE_CID + index

        # Unique socket paths
        safe_name = name.replace("/", "-").replace(" ", "-")
        config.vsock_uds_path = f"/tmp/bunkervm-vm-{safe_name}.sock"
        config.socket_path = f"/tmp/bunkervm-fc-{safe_name}.sock"
        config.rootfs_work_path = f"/tmp/bunkervm-rootfs-{safe_name}.ext4"

        # Override resources if specified
        if cpus is not None:
            config.vcpu_count = cpus
        if memory is not None:
            config.mem_size_mib = memory

        return config

    def __del__(self):
        """Clean up all VMs on garbage collection."""
        try:
            self.stop_all()
        except Exception:
            pass

    def __contains__(self, name: str) -> bool:
        return name in self._instances

    def __len__(self) -> int:
        return len(self._instances)
