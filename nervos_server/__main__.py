#!/usr/bin/env python3
"""
NervOS MCP Server — Entry point.

Usage:
  python -m nervos_server                    # Boots VM with internet. Needs sudo.
  python -m nervos_server --transport sse    # SSE transport (remote/web clients)
  python -m nervos_server --no-network       # Offline mode (no internet in VM)
  python -m nervos_server --skip-vm          # VM already running externally
  python -m nervos_server --help

Claude Desktop config (claude_desktop_config.json):
  {
    "mcpServers": {
      "nervos": {
        "command": "wsl",
        "args": ["-d", "Ubuntu", "--", "sudo", "python3", "-m", "nervos_server"]
      }
    }
  }

One line. VM boots with internet access. sudo needed for TAP networking.
"""

import argparse
import atexit
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="nervos-sandbox",
        description="NervOS — Hardware-isolated sandbox for AI agents",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="MCP transport: stdio (default, for Claude) or sse (remote)",
    )
    parser.add_argument(
        "--port", type=int, default=3000,
        help="Port for SSE transport (default: 3000)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to nervos.toml config file",
    )
    parser.add_argument(
        "--no-network", action="store_true",
        help="Disable TAP networking (no internet in VM, no sudo needed)",
    )
    parser.add_argument(
        "--skip-vm", action="store_true",
        help="Don't start VM (assume externally managed)",
    )
    parser.add_argument(
        "--vm-ip", default=None,
        help="Override VM IP (only with --network or --skip-vm)",
    )
    parser.add_argument(
        "--vm-port", type=int, default=None,
        help="Override VM exec-agent port",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Logging to stderr (stdout reserved for MCP stdio protocol)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("nervos")

    # ── Load config ──
    from .config import load_config
    config = load_config(args.config)

    if args.vm_ip:
        config.vm_ip = args.vm_ip
    if args.vm_port:
        config.vm_port = args.vm_port

    # ── Audit logger ──
    from .audit import AuditLogger
    audit = AuditLogger(config.audit_log_path)
    network = not args.no_network
    audit.log("server_start", transport=args.transport, network=network)

    # ── Bootstrap: ensure NervOS bundle is ready ──
    if not args.skip_vm:
        from .bootstrap import ensure_ready

        bundle = ensure_ready()
        # Override config paths with bootstrap-provided paths
        config.firecracker_bin = bundle.firecracker
        config.kernel_path = bundle.kernel
        config.rootfs_path = bundle.rootfs

    # ── Start VM ──
    vm = None
    if not args.skip_vm:
        from .vm_manager import VMManager

        vm = VMManager(config, network=network)
        try:
            vm.start()
            logger.info("VM started (PID %d)", vm.fc_pid)
            atexit.register(vm.cleanup)
        except Exception as e:
            logger.error("Failed to start VM: %s", e)
            sys.exit(1)

    # ── Connect to sandbox ──
    from .sandbox_client import SandboxClient

    if args.skip_vm and args.vm_ip:
        # External VM via TCP
        client = SandboxClient(host=args.vm_ip, port=args.vm_port or config.vm_port)
    else:
        # Default: vsock (works with or without TAP)
        client = SandboxClient(vsock_uds=config.vsock_uds_path, vsock_port=config.vm_port)

    logger.info("Connecting to sandbox via %s...", client.label)

    if client.wait_for_health(timeout=config.health_timeout):
        logger.info("Sandbox ready!")
    else:
        if args.skip_vm:
            logger.warning("Sandbox not responding — tools will fail until VM is available")
        else:
            logger.error("Sandbox did not become ready in time")
            sys.exit(1)

    # ── Start MCP server ──
    from .mcp_server import create_server, set_globals

    set_globals(client=client, audit=audit, vm_manager=vm, config=config)
    server = create_server()

    logger.info("NervOS MCP server ready (transport: %s)", args.transport)
    audit.log("server_ready", transport=args.transport)

    if args.transport == "sse":
        logger.info("SSE endpoint: http://0.0.0.0:%d/sse", args.port)
        server.run(transport="sse", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
