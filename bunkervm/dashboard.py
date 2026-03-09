"""
BunkerVM Web Dashboard — lightweight localhost UI for monitoring.

Provides a real-time dashboard at http://localhost:<port>/dashboard showing:
  - VM status (running, PID, CPU, RAM, disk)
  - Live audit log (tool calls with timestamps)
  - Quick actions (reset sandbox)

Runs alongside the MCP SSE server on the same port.
No external dependencies — pure stdlib HTTP + inline HTML/CSS/JS.

Usage:
    # Auto-starts when using SSE transport:
    sudo python3 -m bunkervm --transport sse

    # Or standalone:
    from bunkervm.dashboard import DashboardServer
    server = DashboardServer(client, audit, vm_manager, port=3000)
    server.start()
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional

logger = logging.getLogger("bunkervm.dashboard")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles each request in a new thread."""
    daemon_threads = True


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BunkerVM Dashboard</title>
<style>
:root {
    --bg: #0a0a0f;
    --surface: #111118;
    --border: #1e1e2e;
    --text: #e0e0e8;
    --muted: #6b6b80;
    --accent: #7c5cfc;
    --green: #34d399;
    --red: #f87171;
    --cyan: #22d3ee;
    --orange: #fb923c;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
}
h1 { font-size: 1.4rem; margin-bottom: 8px; }
h1 span { color: var(--accent); }
.subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }
.grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
}
.card-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.card-value { font-size: 1.8rem; font-weight: 700; }
.card-value.green { color: var(--green); }
.card-value.red { color: var(--red); }
.card-value.cyan { color: var(--cyan); }
.card-value.orange { color: var(--orange); }
.section { margin-bottom: 24px; }
.section h2 { font-size: 1rem; margin-bottom: 12px; color: var(--muted); }
.log-container {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    max-height: 500px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 0.8rem;
    line-height: 1.7;
}
.log-entry { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
.log-ts { color: var(--muted); margin-right: 8px; }
.log-event { color: var(--accent); margin-right: 8px; font-weight: 600; }
.log-detail { color: var(--text); }
.log-exec { color: var(--cyan); }
.log-write { color: var(--green); }
.log-read { color: var(--orange); }
.log-error { color: var(--red); }
.actions { display: flex; gap: 12px; margin-bottom: 24px; }
.btn {
    padding: 10px 20px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
}
.btn:hover { border-color: var(--accent); background: rgba(124,92,252,0.1); }
.btn-danger:hover { border-color: var(--red); background: rgba(248,113,113,0.1); }
.status-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 6px;
}
.status-dot.ok { background: var(--green); box-shadow: 0 0 6px rgba(52,211,153,0.5); }
.status-dot.err { background: var(--red); }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.info-table { width: 100%; font-size: 0.85rem; }
.info-table td { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
.info-table td:first-child { color: var(--muted); width: 40%; }
.vm-count-bar {
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
.vm-count-badge {
    background: var(--accent); color: #fff; font-weight: 700;
    font-size: 1.1rem; padding: 6px 14px; border-radius: 8px;
    min-width: 36px; text-align: center;
}
.vm-table {
    width: 100%; border-collapse: collapse; font-size: 0.85rem;
}
.vm-table th {
    text-align: left; padding: 10px 12px; color: var(--muted);
    font-weight: 600; font-size: 0.75rem; text-transform: uppercase;
    letter-spacing: 0.5px; border-bottom: 1px solid var(--border);
}
.vm-table td {
    padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.vm-table tr:hover td { background: rgba(124,92,252,0.04); }
.vm-status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 600;
}
.vm-status-badge.running { background: rgba(52,211,153,0.12); color: var(--green); }
.vm-status-badge.stopped { background: rgba(248,113,113,0.12); color: var(--red); }
.progress-bar {
    width: 100%; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden;
}
.progress-fill {
    height: 100%; border-radius: 3px; transition: width 0.5s;
}
.progress-fill.mem { background: var(--orange); }
.progress-fill.cpu { background: var(--cyan); }
@media (max-width: 768px) {
    .grid { grid-template-columns: 1fr 1fr; }
    .info-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<h1><span>BunkerVM</span> Dashboard</h1>
<p class="subtitle">Hardware-isolated AI sandbox &mdash; real-time monitoring</p>

<div class="grid">
    <div class="card">
        <div class="card-label">Status</div>
        <div class="card-value green" id="vm-status">Loading...</div>
    </div>
    <div class="card">
        <div class="card-label">CPU</div>
        <div class="card-value cyan" id="vm-cpu">-</div>
    </div>
    <div class="card">
        <div class="card-label">Memory</div>
        <div class="card-value orange" id="vm-memory">-</div>
    </div>
    <div class="card">
        <div class="card-label">Uptime</div>
        <div class="card-value" id="vm-uptime">-</div>
    </div>
</div>

<div class="actions">
    <button class="btn" onclick="refreshStatus()">&#8635; Refresh</button>
    <button class="btn btn-danger" onclick="resetSandbox()">&#9888; Reset Sandbox</button>
</div>

<div class="section">
    <div class="vm-count-bar">
        <h2 style="margin:0">Running VMs</h2>
        <span class="vm-count-badge" id="vm-count">-</span>
    </div>
    <div class="card" style="padding: 0; overflow: hidden;">
        <table class="vm-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>CPU</th>
                    <th>Memory</th>
                    <th>Load (1m)</th>
                    <th>Uptime</th>
                    <th>Network</th>
                    <th>PID</th>
                </tr>
            </thead>
            <tbody id="vm-table-body">
                <tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<div class="info-grid">
    <div class="section">
        <h2>VM Info</h2>
        <div class="card">
            <table class="info-table" id="vm-info">
                <tr><td>Hostname</td><td id="info-hostname">-</td></tr>
                <tr><td>Kernel</td><td id="info-kernel">-</td></tr>
                <tr><td>OS</td><td id="info-os">-</td></tr>
                <tr><td>Disk</td><td id="info-disk">-</td></tr>
                <tr><td>Processes</td><td id="info-procs">-</td></tr>
                <tr><td>Load (1m)</td><td id="info-load">-</td></tr>
            </table>
        </div>
    </div>
    <div class="section">
        <h2>Audit Log <span style="color: var(--muted); font-weight: normal;">(last 50)</span></h2>
        <div class="log-container" id="log-container">
            <div class="log-entry"><span class="log-ts">Loading...</span></div>
        </div>
    </div>
</div>

<script>
const API = '';

async function fetchJSON(path) {
    const r = await fetch(API + path);
    return r.json();
}

function fmtTime(secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
}

async function refreshStatus() {
    try {
        const s = await fetchJSON('/api/status');
        const isUp = (s.status === 'running' || s.status === 'ok');
        document.getElementById('vm-status').innerHTML =
            isUp
                ? '<span class="status-dot ok"></span>Running'
                : '<span class="status-dot err"></span>Down';
        document.getElementById('vm-status').className =
            'card-value ' + (isUp ? 'green' : 'red');

        if (s.cpu) {
            document.getElementById('vm-cpu').textContent = s.cpu.cores + ' cores';
        }
        if (s.memory) {
            const used = Math.round(s.memory.used_bytes / 1048576);
            const total = Math.round(s.memory.total_bytes / 1048576);
            document.getElementById('vm-memory').textContent = used + ' / ' + total + ' MB';
        }
        if (s.uptime_seconds) {
            document.getElementById('vm-uptime').textContent = fmtTime(s.uptime_seconds);
        }
        if (s.hostname) document.getElementById('info-hostname').textContent = s.hostname;
        if (s.disk) {
            const du = Math.round(s.disk.used_bytes / 1048576);
            const dt = Math.round(s.disk.total_bytes / 1048576);
            document.getElementById('info-disk').textContent = du + ' / ' + dt + ' MB';
        }
        if (s.processes) document.getElementById('info-procs').textContent = s.processes;
        if (s.load) document.getElementById('info-load').textContent = s.load['1m'].toFixed(2);
    } catch (e) {
        document.getElementById('vm-status').innerHTML =
            '<span class="status-dot err"></span>Unreachable';
        document.getElementById('vm-status').className = 'card-value red';
    }

    // Fetch kernel/os info via exec
    try {
        const k = await fetchJSON('/api/exec?cmd=' + encodeURIComponent('uname -r'));
        if (k.stdout) document.getElementById('info-kernel').textContent = k.stdout.trim();
    } catch {}
    try {
        const o = await fetchJSON('/api/exec?cmd=' + encodeURIComponent(
            'source /etc/os-release && echo $PRETTY_NAME'));
        if (o.stdout) document.getElementById('info-os').textContent = o.stdout.trim();
    } catch {}
}

async function refreshLogs() {
    try {
        const logs = await fetchJSON('/api/audit?n=50');
        const container = document.getElementById('log-container');
        container.innerHTML = '';
        logs.reverse().forEach(entry => {
            const div = document.createElement('div');
            div.className = 'log-entry';
            const ts = new Date(entry.ts * 1000).toLocaleTimeString();
            const evt = entry.event || '?';
            let cls = 'log-detail';
            if (evt.includes('exec')) cls = 'log-exec';
            else if (evt.includes('write') || evt.includes('upload')) cls = 'log-write';
            else if (evt.includes('read') || evt.includes('download')) cls = 'log-read';
            else if (evt.includes('error') || evt.includes('blocked')) cls = 'log-error';

            let detail = '';
            if (entry.command) detail = entry.command.substring(0, 80);
            else if (entry.path) detail = entry.path;
            else if (entry.local_path) detail = entry.local_path + ' → ' + (entry.remote_path || '');
            else if (entry.transport) detail = 'transport=' + entry.transport;

            div.innerHTML = `<span class="log-ts">${ts}</span>` +
                `<span class="log-event">${evt}</span>` +
                `<span class="${cls}">${detail}</span>`;
            container.appendChild(div);
        });
        if (logs.length === 0) {
            container.innerHTML = '<div class="log-entry"><span class="log-ts">No events yet</span></div>';
        }
    } catch {}
}

async function resetSandbox() {
    if (!confirm('Reset the sandbox? All files and state will be lost.')) return;
    try {
        const r = await fetchJSON('/api/reset');
        alert(r.message || 'Reset initiated');
        setTimeout(refreshStatus, 3000);
    } catch (e) {
        alert('Reset failed: ' + e.message);
    }
}

async function refreshVMs() {
    try {
        const data = await fetchJSON('/api/vms');
        document.getElementById('vm-count').textContent = data.count;
        const tbody = document.getElementById('vm-table-body');
        tbody.innerHTML = '';
        if (!data.vms || data.vms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No VMs running</td></tr>';
            return;
        }
        data.vms.forEach(vm => {
            const tr = document.createElement('tr');
            const isRunning = vm.running;
            const badge = isRunning
                ? '<span class="vm-status-badge running"><span class="status-dot ok"></span>Running</span>'
                : '<span class="vm-status-badge stopped"><span class="status-dot err"></span>Stopped</span>';

            // Memory bar
            let memCell = vm.memory_mb + ' MB';
            if (vm.mem_used_mb !== undefined && vm.mem_total_mb !== undefined && vm.mem_total_mb > 0) {
                const pct = Math.min(100, Math.round((vm.mem_used_mb / vm.mem_total_mb) * 100));
                memCell = '<div style="white-space:nowrap">' + vm.mem_used_mb + ' / ' + vm.mem_total_mb + ' MB</div>' +
                    '<div class="progress-bar"><div class="progress-fill mem" style="width:' + pct + '%"></div></div>';
            }

            const load = vm.load_1m !== undefined ? vm.load_1m.toFixed(2) : '-';
            const uptime = vm.uptime_seconds ? fmtTime(vm.uptime_seconds) : '-';
            const net = vm.vm_ip ? vm.vm_ip : (vm.network || '-');

            tr.innerHTML =
                '<td style="font-weight:600">' + vm.name + '</td>' +
                '<td>' + badge + '</td>' +
                '<td style="color:var(--cyan)">' + vm.cpus + (vm.cpu_cores ? ' (' + vm.cpu_cores + ')' : '') + '</td>' +
                '<td>' + memCell + '</td>' +
                '<td>' + load + '</td>' +
                '<td>' + uptime + '</td>' +
                '<td style="color:var(--muted);font-family:monospace;font-size:0.8rem">' + net + '</td>' +
                '<td style="color:var(--muted)">' + (vm.pid || '-') + '</td>';
            tbody.appendChild(tr);
        });
    } catch (e) {
        document.getElementById('vm-count').textContent = '?';
    }
}

// Initial load
refreshStatus();
refreshLogs();
refreshVMs();

// Auto-refresh every 5 seconds
setInterval(refreshStatus, 5000);
setInterval(refreshLogs, 5000);
setInterval(refreshVMs, 5000);
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for the dashboard API and UI."""

    # Shared state (set by DashboardServer)
    _client = None
    _audit = None
    _vm_manager = None
    _pool = None
    _config = None

    def log_message(self, format, *args):
        """Suppress default HTTP logs."""
        pass

    def handle_one_request(self):
        """Override to catch BrokenPipeError gracefully."""
        try:
            super().handle_one_request()
        except BrokenPipeError:
            pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_vm_list(self) -> dict:
        """Build the list of VMs with resource info for /api/vms."""
        vms = []

        if self._pool is not None:
            # Multi-VM mode: get all VMs from the pool
            for info in self._pool.status_all():
                vm_entry = {
                    "name": info["name"],
                    "running": info.get("running", False),
                    "pid": info.get("pid"),
                    "cpus": info.get("cpus", "-"),
                    "memory_mb": info.get("memory_mb", "-"),
                    "network": info.get("network"),
                    "vm_ip": info.get("vm_ip"),
                }
                # Try to get live metrics from the VM client
                try:
                    client = self._pool.client(info["name"])
                    status = client.status()
                    if status.get("memory"):
                        vm_entry["mem_used_mb"] = round(
                            status["memory"].get("used_bytes", 0) / 1048576
                        )
                        vm_entry["mem_total_mb"] = round(
                            status["memory"].get("total_bytes", 0) / 1048576
                        )
                    if status.get("cpu"):
                        vm_entry["cpu_cores"] = status["cpu"].get("cores", "-")
                    if status.get("load"):
                        vm_entry["load_1m"] = status["load"].get("1m", 0)
                    if status.get("uptime_seconds"):
                        vm_entry["uptime_seconds"] = status["uptime_seconds"]
                except Exception:
                    pass
                vms.append(vm_entry)
        else:
            # Single-VM mode: build info from vm_manager + config + live status
            vm_entry = {
                "name": "default",
                "running": self._vm_manager.is_running() if self._vm_manager else False,
                "pid": self._vm_manager.fc_pid if self._vm_manager else None,
                "cpus": self._config.vcpu_count if self._config else "-",
                "memory_mb": self._config.mem_size_mib if self._config else "-",
                "network": self._config.tap_device if self._config else None,
                "vm_ip": self._config.vm_ip if self._config else None,
            }
            try:
                status = self._client.status()
                if status.get("memory"):
                    vm_entry["mem_used_mb"] = round(
                        status["memory"].get("used_bytes", 0) / 1048576
                    )
                    vm_entry["mem_total_mb"] = round(
                        status["memory"].get("total_bytes", 0) / 1048576
                    )
                if status.get("cpu"):
                    vm_entry["cpu_cores"] = status["cpu"].get("cores", "-")
                if status.get("load"):
                    vm_entry["load_1m"] = status["load"].get("1m", 0)
                if status.get("uptime_seconds"):
                    vm_entry["uptime_seconds"] = status["uptime_seconds"]
            except Exception:
                pass
            vms.append(vm_entry)

        return {"count": len(vms), "vms": vms}

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/dashboard", "/dashboard/", "/"):
            self._send_html(_DASHBOARD_HTML)

        elif path == "/api/status":
            try:
                status = self._client.status()
                self._send_json(status)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)

        elif path == "/api/exec":
            # Parse query params
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            cmd = query.get("cmd", [""])[0]
            if not cmd:
                self._send_json({"error": "Missing cmd parameter"}, 400)
                return
            try:
                result = self._client.exec(cmd, timeout=10)
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/api/audit":
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            n = int(query.get("n", ["50"])[0])
            try:
                entries = self._audit.read_recent(n)
                self._send_json(entries)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/api/reset":
            if self._vm_manager:
                try:
                    self._vm_manager.restart()
                    if self._client.wait_for_health(timeout=30):
                        self._send_json({"message": "Sandbox reset complete"})
                    else:
                        self._send_json({"message": "Reset initiated, health check pending"})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
            else:
                self._send_json({"error": "VM manager not available"}, 400)

        elif path == "/api/health":
            try:
                h = self._client.health()
                self._send_json(h)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)

        elif path == "/api/vms":
            try:
                vms = self._get_vm_list()
                self._send_json(vms)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        else:
            self.send_error(404, "Not Found")


class DashboardServer:
    """Lightweight HTTP dashboard server for BunkerVM monitoring.

    Runs in a background thread alongside the MCP server.

    Args:
        client: SandboxClient instance
        audit: AuditLogger instance
        vm_manager: VMManager instance (optional)
        port: HTTP port (default: 3000)
        pool: VMPool instance (optional, for multi-VM)
        config: BunkerVMConfig instance (optional, for resource info)
    """

    def __init__(self, client, audit, vm_manager=None, port: int = 3000, pool=None, config=None):
        DashboardHandler._client = client
        DashboardHandler._audit = audit
        DashboardHandler._vm_manager = vm_manager
        DashboardHandler._pool = pool
        DashboardHandler._config = config
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the dashboard server in a background thread."""
        self._server = ThreadingHTTPServer(("0.0.0.0", self._port), DashboardHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="bunkervm-dashboard",
        )
        self._thread.start()
        logger.info("Dashboard: http://localhost:%d/dashboard", self._port)

    def stop(self):
        """Stop the dashboard server."""
        if self._server:
            self._server.shutdown()
            self._server = None
