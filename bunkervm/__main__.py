#!/usr/bin/env python3
"""
BunkerVM MCP Server — Entry point.

Usage:
  python -m bunkervm                    # Boots VM with internet. Needs sudo.
  python -m bunkervm --transport sse    # SSE transport (remote/web clients)
  python -m bunkervm --no-network       # Offline mode (no internet in VM)
  python -m bunkervm --skip-vm          # VM already running externally
  python -m bunkervm --help

Claude Desktop config (claude_desktop_config.json):
  {
    "mcpServers": {
      "bunkervm": {
        "command": "wsl",
        "args": ["-d", "Ubuntu", "--", "sudo", "python3", "-m", "bunkervm"]
      }
    }
  }

One line. VM boots with internet access. sudo needed for TAP networking.
"""

import argparse
import atexit
import logging
import sys


# Route new CLI subcommands (demo, run, info) to the new CLI
_CLI_COMMANDS = {"demo", "run", "info", "server"}


def main():
    # If first arg is a new CLI subcommand, delegate to bunkervm.cli
    if len(sys.argv) > 1 and sys.argv[1] in _CLI_COMMANDS:
        from .cli import main as cli_main
        raise SystemExit(cli_main())

    parser = argparse.ArgumentParser(
        prog="bunkervm",
        description="BunkerVM — Hardware-isolated sandbox for AI agents",
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
        help="Path to bunkervm.toml config file",
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
        "--cpus", type=int, default=None,
        help="Number of vCPUs for the VM (default: 2)",
    )
    parser.add_argument(
        "--memory", type=int, default=None,
        help="VM memory in MB (default: 2048)",
    )
    parser.add_argument(
        "--max-exec-timeout", type=int, default=None,
        help="Maximum allowed command timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--name", default=None,
        help="VM instance name (for multi-VM support)",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Enable web dashboard at http://localhost:<port+1>/dashboard",
    )
    parser.add_argument(
        "--dashboard-port", type=int, default=None,
        help="Dashboard port (default: MCP port + 1, i.e. 3001)",
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
    logger = logging.getLogger("bunkervm")

    # ── Load config ──
    from .config import load_config
    config = load_config(args.config)

    if args.vm_ip:
        config.vm_ip = args.vm_ip
    if args.vm_port:
        config.vm_port = args.vm_port
    if args.cpus:
        config.vcpu_count = args.cpus
    if args.memory:
        config.mem_size_mib = args.memory
    if args.max_exec_timeout:
        config.max_exec_timeout = args.max_exec_timeout

    # ── Audit logger ──
    from .audit import AuditLogger
    audit = AuditLogger(config.audit_log_path)
    network = not args.no_network
    audit.log("server_start", transport=args.transport, network=network)

    # ── Bootstrap: ensure BunkerVM bundle is ready ──
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

        # If --name is provided, use unique paths for this instance
        if args.name:
            safe_name = args.name.replace("/", "-").replace(" ", "-")
            config.vsock_uds_path = f"/tmp/bunkervm-vm-{safe_name}.sock"
            config.socket_path = f"/tmp/bunkervm-fc-{safe_name}.sock"
            config.rootfs_work_path = f"/tmp/bunkervm-rootfs-{safe_name}.ext4"
            logger.info("Named instance: %s", args.name)

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
    server = create_server(port=args.port, host="0.0.0.0")

    logger.info("BunkerVM MCP server ready (transport: %s)", args.transport)
    audit.log("server_ready", transport=args.transport)

    # ── Start dashboard (if enabled or SSE transport) ──
    if args.dashboard or args.transport == "sse":
        from .dashboard import DashboardServer
        dash_port = args.dashboard_port or (args.port + 1)
        dashboard = DashboardServer(client, audit, vm, port=dash_port, config=config)
        dashboard.start()

    if args.transport == "sse":
        logger.info("SSE endpoint: http://0.0.0.0:%d/sse", args.port)
        server.run(transport="sse")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
