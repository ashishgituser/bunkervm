"""
BunkerDesktop - Native Desktop Application
Uses pywebview (WebView2 on Windows) for a native window.
No browser, no Rust, no Node.js - just Python.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

ENGINE_PORT = 9551
ENGINE_URL = f"http://localhost:{ENGINE_PORT}"
STATUS_URL = f"{ENGINE_URL}/engine/status"
POLL_START_TIMEOUT = 30  # seconds to wait for engine to start

# Hide CMD windows when spawning WSL subprocesses on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Resolve asset directory (HTML/CSS/JS)
# When frozen by PyInstaller, assets are in sys._MEIPASS/src/
# When running from source, assets are in ./src/
if getattr(sys, 'frozen', False):
    ASSET_DIR = os.path.join(sys._MEIPASS, "src")
else:
    ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")


def is_engine_running():
    """Check if the engine API is reachable."""
    try:
        req = urllib.request.Request(STATUS_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        return resp.status == 200
    except Exception:
        return False


def get_engine_status():
    """Get engine status as dict, or None if unreachable."""
    try:
        req = urllib.request.Request(STATUS_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=2)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def find_wsl_distro():
    """Find the default WSL distro name."""
    for name in ["Ubuntu", "Ubuntu-22.04", "Ubuntu-24.04", "Debian"]:
        try:
            r = subprocess.run(
                ["wsl", "-d", name, "--", "echo", "ok"],
                capture_output=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            if r.returncode == 0:
                return name
        except Exception:
            continue
    return "Ubuntu"


def find_bunkervm_path(distro):
    """Find the bunkervm executable inside WSL."""
    paths = [
        "~/.bunkervm/venv/bin/bunkervm",
        "~/.local/bin/bunkervm",
        "/usr/local/bin/bunkervm",
    ]
    for p in paths:
        try:
            r = subprocess.run(
                ["wsl", "-d", distro, "--", "bash", "-c", f"test -x {p}"],
                capture_output=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            if r.returncode == 0:
                return p
        except Exception:
            continue
    return "~/.bunkervm/venv/bin/bunkervm"


def start_engine_wsl(distro, bvm_path):
    """Start the engine inside WSL as a detached process."""
    try:
        # Use subprocess.Popen to start WSL detached
        subprocess.Popen(
            ["wsl", "-d", distro, "--", bvm_path, "engine", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        return True
    except Exception as e:
        print(f"Failed to start engine: {e}", file=sys.stderr)
        return False


def fix_kvm_permissions(distro):
    """Fix /dev/kvm permissions from Windows side.

    Uses 'wsl -u root' which runs as root WITHOUT needing a password.
    Also sets up /etc/wsl.conf so it persists across WSL reboots.
    """

    # 1. Immediate fix: chmod 666 /dev/kvm (as root, no password)
    try:
        subprocess.run(
            ["wsl", "-u", "root", "-d", distro, "--",
             "chmod", "666", "/dev/kvm"],
            capture_output=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        pass

    # 2. Persistent fix: add boot command to /etc/wsl.conf
    #    so /dev/kvm is auto-fixed on every WSL startup
    try:
        # Check if already configured
        r = subprocess.run(
            ["wsl", "-u", "root", "-d", distro, "--",
             "grep", "-q", "chmod.*kvm", "/etc/wsl.conf"],
            capture_output=True, timeout=5,
            creationflags=_NO_WINDOW,
        )
        if r.returncode != 0:
            wsl_conf_cmd = (
                "if grep -q '\\[boot\\]' /etc/wsl.conf 2>/dev/null; then "
                "  grep -q 'chmod.*kvm' /etc/wsl.conf || "
                "  sed -i '/\\[boot\\]/a command = chmod 666 /dev/kvm' /etc/wsl.conf; "
                "else "
                "  printf '\\n[boot]\\ncommand = chmod 666 /dev/kvm\\n' >> /etc/wsl.conf; "
                "fi"
            )
            subprocess.run(
                ["wsl", "-u", "root", "-d", distro, "--",
                 "bash", "-c", wsl_conf_cmd],
                capture_output=True, timeout=10,
                creationflags=_NO_WINDOW,
            )
    except Exception:
        pass  # Non-critical - immediate fix is enough


def wait_for_engine(timeout=POLL_START_TIMEOUT):
    """Wait for engine to become reachable."""
    for _ in range(timeout):
        if is_engine_running():
            return True
        time.sleep(1)
    return False


class BunkerDesktopApp:
    """Main application class."""

    def __init__(self):
        self.window = None
        self._distro = None
        self._bvm_path = None

    def start(self):
        """Entry point - create window and run."""
        import webview

        # Check assets exist
        index_path = os.path.join(ASSET_DIR, "index.html")
        if not os.path.exists(index_path):
            self._show_error(f"UI assets not found at:\n{ASSET_DIR}")
            return

        # Start engine in background before showing window
        self._ensure_engine_thread = threading.Thread(
            target=self._ensure_engine, daemon=True
        )
        self._ensure_engine_thread.start()

        # Create native window
        self.window = webview.create_window(
            title="BunkerDesktop",
            url=index_path,
            width=1280,
            height=800,
            min_size=(900, 600),
            resizable=True,
            background_color="#06060b",
            text_select=False,
        )

        # Expose Python functions to JS
        self.window.expose(self.py_get_engine_status)
        self.window.expose(self.py_start_engine)
        self.window.expose(self.py_stop_engine)
        self.window.expose(self.py_get_api_base)

        # Start the webview event loop
        webview.start(
            self._on_loaded,
            debug=("--debug" in sys.argv),
        )

    def _ensure_engine(self):
        """Background thread: make sure engine is running."""
        if is_engine_running():
            return

        self._distro = find_wsl_distro()

        # Fix /dev/kvm permissions silently (no password needed from Windows)
        fix_kvm_permissions(self._distro)

        self._bvm_path = find_bunkervm_path(self._distro)
        start_engine_wsl(self._distro, self._bvm_path)
        wait_for_engine()

    def _on_loaded(self):
        """Called when the webview is ready."""
        # Inject the API base URL so app.js connects to the right endpoint
        if self.window:
            self.window.evaluate_js(
                f"window.BUNKERDESKTOP_API = '{ENGINE_URL}';"
            )

    def _show_error(self, message):
        """Show a simple error dialog."""
        try:
            import webview
            webview.create_window("BunkerDesktop - Error", html=f"""
                <html><body style="background:#1a1a2e;color:#e8e8ed;font-family:sans-serif;
                display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
                <div style="text-align:center;padding:40px">
                <h2 style="color:#f87171">Error</h2>
                <p style="white-space:pre-line">{message}</p>
                </div></body></html>
            """, width=500, height=300)
            webview.start()
        except Exception:
            print(f"ERROR: {message}", file=sys.stderr)
            sys.exit(1)

    # -- JS-exposed functions --

    def py_get_engine_status(self):
        """Called from JS to check engine."""
        return get_engine_status()

    def py_start_engine(self):
        """Called from JS to start engine."""
        if is_engine_running():
            return {"ok": True, "message": "Already running"}
        if not self._distro:
            self._distro = find_wsl_distro()
        if not self._bvm_path:
            self._bvm_path = find_bunkervm_path(self._distro)
        ok = start_engine_wsl(self._distro, self._bvm_path)
        if ok:
            started = wait_for_engine(timeout=15)
            return {"ok": started, "message": "Started" if started else "Timeout"}
        return {"ok": False, "message": "Failed to start"}

    def py_stop_engine(self):
        """Called from JS to stop engine."""
        try:
            req = urllib.request.Request(
                f"{ENGINE_URL}/engine/stop", method="POST",
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return {"ok": resp.status == 200}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def py_get_api_base(self):
        """Return API base URL for JS."""
        return ENGINE_URL


def main():
    """Entry point."""
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    app = BunkerDesktopApp()
    app.start()


if __name__ == "__main__":
    main()
