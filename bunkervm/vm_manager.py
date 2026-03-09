"""
BunkerVM VM Manager — Firecracker MicroVM lifecycle management.

Handles:
  - Firecracker process start/stop/restart
  - VM configuration generation (vsock + TAP by default)
  - Rootfs working copies for clean resets

Default mode:
  - VSOCK for host↔VM communication (no sudo needed)
  - TAP for VM internet access (needs sudo, auto-configured)
  - Pass --no-network to disable TAP (offline/airgapped mode)

Requires:
  - Firecracker binary (default: /usr/local/bin/firecracker)
  - Linux with /dev/kvm accessible
  - Kernel image (vmlinux)
  - Root filesystem image (rootfs.ext4)
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

logger = logging.getLogger("bunkervm.vm")


class VMError(Exception):
    """VM lifecycle error."""
    pass


class VMManager:
    """Manages a single Firecracker MicroVM instance.

    Default mode (vsock + TAP):
        vm = VMManager(config)
        vm.start()              # Sets up TAP, boots VM with vsock + internet
        # host talks to VM via /tmp/bunkervm-vsock.sock

    Offline mode (vsock only, no internet in VM):
        vm = VMManager(config, network=False)
        vm.start()              # Boots VM with vsock, no internet
    """

    def __init__(self, config, network: bool = True):
        self.config = config
        self._network = network
        self._process: Optional[subprocess.Popen] = None
        self._socket_path: str = config.socket_path
        self._config_path: Optional[str] = None
        self._tap_created: bool = False
        self._rootfs_copy: Optional[str] = None

    @property
    def vsock_uds_path(self) -> str:
        """Path to the vsock UDS that Firecracker creates."""
        return self.config.vsock_uds_path

    @property
    def fc_pid(self) -> Optional[int]:
        if self._process:
            return self._process.pid
        return None

    # ── VM Lifecycle ──

    def start(self) -> None:
        """Start the Firecracker VM.

        In default mode: creates vsock config, no networking.
        In network mode: also sets up TAP device (needs sudo).
        """
        if self.is_running():
            logger.warning("VM already running (PID %d)", self._process.pid)
            return

        self._validate()

        # Optional: setup TAP networking
        if self._network:
            self._setup_network()

        # Create working copy of rootfs (enables clean resets)
        self._create_rootfs_copy()

        # Generate VM config with vsock
        self._generate_config()

        # Clean up old sockets
        for sock_path in [self._socket_path, self.config.vsock_uds_path]:
            if os.path.exists(sock_path):
                os.unlink(sock_path)

        # Launch Firecracker
        fc_bin = self.config.firecracker_bin
        logger.info("Starting Firecracker: %s", fc_bin)

        try:
            self._process = subprocess.Popen(
                [
                    fc_bin,
                    "--api-sock", self._socket_path,
                    "--config-file", self._config_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise VMError(
                f"Firecracker binary not found at '{fc_bin}'. "
                f"Install: https://github.com/firecracker-microvm/firecracker/releases"
            )
        except PermissionError:
            raise VMError(
                f"Permission denied running '{fc_bin}'. "
                f"Check /dev/kvm permissions: sudo chmod 666 /dev/kvm"
            )

        # Wait for startup
        time.sleep(0.5)

        if not self.is_running():
            stderr = ""
            try:
                _, stderr_bytes = self._process.communicate(timeout=2)
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            except Exception:
                pass
            raise VMError(f"Firecracker exited immediately.\nStderr: {stderr}")

        logger.info("VM started (PID %d), vsock UDS: %s",
                     self._process.pid, self.config.vsock_uds_path)

    def stop(self) -> None:
        """Stop the Firecracker VM and clean up everything."""
        if self._process is not None:
            pid = self._process.pid
            logger.info("Stopping VM (PID %d)...", pid)

            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("VM did not stop gracefully, killing...")
                self._process.kill()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            except Exception as e:
                logger.error("Error stopping VM: %s", e)

            self._process = None
            logger.info("VM stopped")

        # Clean up files
        for path in [self._socket_path, self.config.vsock_uds_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

        if self._config_path and os.path.exists(self._config_path):
            try:
                os.unlink(self._config_path)
            except OSError:
                pass
            self._config_path = None

        if self._rootfs_copy and self._rootfs_copy != self.config.rootfs_path:
            if os.path.exists(self._rootfs_copy):
                try:
                    os.unlink(self._rootfs_copy)
                    logger.info("Removed rootfs working copy")
                except OSError:
                    pass
            self._rootfs_copy = None

        # Clean up TAP if we created it
        if self._tap_created:
            self._cleanup_network()

    def cleanup(self) -> None:
        """Alias for stop(), registered with atexit."""
        self.stop()

    def restart(self) -> None:
        """Restart the VM with a fresh rootfs copy."""
        logger.info("Restarting sandbox VM...")
        self.stop()
        time.sleep(1)
        self.start()

    def is_running(self) -> bool:
        """Check if the Firecracker process is alive."""
        if self._process is None:
            return False
        return self._process.poll() is None

    # ── Network (TAP — gives VM internet, enabled by default) ──

    def _setup_network(self) -> None:
        """Create TAP device for VM internet access. Needs sudo."""
        tap = self.config.tap_device
        host_ip = self.config.host_ip
        subnet = self.config.subnet_mask

        logger.info("Setting up TAP device: %s (%s/%s)", tap, host_ip, subnet)

        try:
            self._run_sudo(["ip", "link", "del", tap], check=False)
            self._run_sudo(["ip", "tuntap", "add", tap, "mode", "tap"])
            self._run_sudo(["ip", "addr", "add", f"{host_ip}/{subnet}", "dev", tap])
            self._run_sudo(["ip", "link", "set", tap, "up"])
            self._tap_created = True

            self._run_sudo(["sysctl", "-w", "net.ipv4.ip_forward=1"], check=False)

            # NAT for internet access
            default_iface = self._get_default_iface()
            if default_iface:
                self._run_sudo([
                    "iptables", "-t", "nat", "-A", "POSTROUTING",
                    "-o", default_iface, "-s", f"{host_ip}/{subnet}",
                    "-j", "MASQUERADE",
                ], check=False)

            logger.info("TAP device %s ready", tap)
        except subprocess.CalledProcessError as e:
            raise VMError(
                f"Failed to setup TAP device. Need sudo.\n"
                f"Fix: run with sudo, or use --no-network for offline mode.\n"
                f"Error: {e}"
            )

    def _cleanup_network(self) -> None:
        """Remove TAP device."""
        if self._tap_created:
            self._run_sudo(["ip", "link", "del", self.config.tap_device], check=False)
            self._tap_created = False

    @staticmethod
    def _get_default_iface() -> Optional[str]:
        """Find the default network interface."""
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            for word in result.stdout.split():
                if word.startswith("eth") or word.startswith("wl") or word.startswith("en"):
                    return word
        except Exception:
            pass
        return None

    # ── Internal helpers ──

    def _validate(self) -> None:
        """Check prerequisites with clear, actionable error messages."""
        # Check KVM first (most common failure)
        if not os.path.exists("/dev/kvm"):
            raise VMError(
                "\n╔══════════════════════════════════════════════════════╗\n"
                "║  KVM is not available                                ║\n"
                "╚══════════════════════════════════════════════════════╝\n\n"
                "BunkerVM requires KVM for hardware-isolated sandboxes.\n\n"
                "Fix:\n"
                "  WSL2 (Windows):\n"
                "    1. Add to %USERPROFILE%\\.wslconfig:\n"
                "       [wsl2]\n"
                "       nestedVirtualization=true\n"
                "    2. Restart WSL: wsl --shutdown\n\n"
                "  Linux:\n"
                "    1. Enable virtualization in BIOS\n"
                "    2. sudo modprobe kvm_intel  (or kvm_amd)\n"
                "    3. sudo chmod 666 /dev/kvm\n"
            )

        # Check KVM permissions
        if not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise VMError(
                "\n╔══════════════════════════════════════════════════════╗\n"
                "║  Permission denied: /dev/kvm                         ║\n"
                "╚══════════════════════════════════════════════════════╝\n\n"
                "Fix:\n"
                "  sudo chmod 666 /dev/kvm\n"
                "  Or run BunkerVM with sudo: sudo bunkervm demo\n"
            )

        # Check required files
        checks = {
            "Firecracker binary": self.config.firecracker_bin,
            "Kernel image (vmlinux)": self.config.kernel_path,
            "Root filesystem (rootfs.ext4)": self.config.rootfs_path,
        }
        for name, path in checks.items():
            if not os.path.exists(path):
                raise VMError(
                    f"\n{name} not found: {path}\n\n"
                    f"Fix: Run 'bunkervm demo' to auto-download,\n"
                    f"or download from: https://github.com/ashishgituser/bunkervm/releases\n"
                )

    def _create_rootfs_copy(self) -> None:
        """Create a working copy of rootfs for clean resets."""
        src = self.config.rootfs_path
        dst = self.config.rootfs_work_path

        if dst and dst != src:
            logger.info("Creating rootfs working copy...")
            shutil.copy2(src, dst)
            self._rootfs_copy = dst
        else:
            self._rootfs_copy = src

    def _generate_config(self) -> None:
        """Generate Firecracker VM config JSON."""
        rootfs = self._rootfs_copy or self.config.rootfs_path

        config = {
            "boot-source": {
                "kernel_image_path": self.config.kernel_path,
                "boot_args": (
                    "console=ttyS0 reboot=k panic=1 pci=off "
                    "init=/init quiet loglevel=1"
                ),
            },
            "drives": [{
                "drive_id": "rootfs",
                "path_on_host": rootfs,
                "is_root_device": True,
                "is_read_only": False,
            }],
            "machine-config": {
                "vcpu_count": self.config.vcpu_count,
                "mem_size_mib": self.config.mem_size_mib,
            },
            # VSOCK — the key piece. Zero-config host↔guest communication.
            "vsock": {
                "guest_cid": self.config.vsock_cid,
                "uds_path": self.config.vsock_uds_path,
            },
        }

        # Add TAP networking (default on, disable with --no-network)
        if self._network and self.config.tap_device:
            config["network-interfaces"] = [{
                "iface_id": "eth0",
                "guest_mac": self.config.guest_mac,
                "host_dev_name": self.config.tap_device,
            }]

        fd, path = tempfile.mkstemp(prefix="bunkervm-vm-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
        self._config_path = path
        logger.debug("VM config written to %s", path)

    @staticmethod
    def _run_sudo(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command with sudo."""
        full_cmd = ["sudo", "-n"] + cmd
        try:
            return subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=10, check=check,
            )
        except FileNotFoundError:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=check,
            )
