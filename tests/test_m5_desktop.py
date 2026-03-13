"""
Test suite for M5: Desktop GUI (BunkerDesktop).

Tests verify:
  1. Desktop frontend files exist and are well-formed
  2. Tauri project structure is complete
  3. Engine API serves dashboard static files
  4. API routes connect correctly to dashboard
  5. HTML/CSS/JS structure and content validation

Run:
    python -m pytest tests/test_m5_desktop.py -v
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DESKTOP_DIR = PROJECT_ROOT / "desktop"
SRC_DIR = DESKTOP_DIR / "src"
TAURI_DIR = DESKTOP_DIR / "src-tauri"


# ══════════════════════════════════════════════════════════
#  1. Frontend File Structure
# ══════════════════════════════════════════════════════════

class TestFrontendFiles(unittest.TestCase):
    """Verify all desktop frontend files exist."""

    def test_desktop_dir_exists(self):
        self.assertTrue(DESKTOP_DIR.is_dir(), "desktop/ directory missing")

    def test_src_dir_exists(self):
        self.assertTrue(SRC_DIR.is_dir(), "desktop/src/ directory missing")

    def test_index_html_exists(self):
        self.assertTrue((SRC_DIR / "index.html").is_file())

    def test_styles_css_exists(self):
        self.assertTrue((SRC_DIR / "styles.css").is_file())

    def test_app_js_exists(self):
        self.assertTrue((SRC_DIR / "app.js").is_file())

    def test_package_json_exists(self):
        self.assertTrue((DESKTOP_DIR / "package.json").is_file())


# ══════════════════════════════════════════════════════════
#  2. Tauri Project Structure
# ══════════════════════════════════════════════════════════

class TestTauriStructure(unittest.TestCase):
    """Verify Tauri project scaffolding."""

    def test_src_tauri_exists(self):
        self.assertTrue(TAURI_DIR.is_dir(), "desktop/src-tauri/ missing")

    def test_cargo_toml(self):
        cargo = TAURI_DIR / "Cargo.toml"
        self.assertTrue(cargo.is_file())
        content = cargo.read_text()
        self.assertIn("bunkerdesktop", content)
        self.assertIn("tauri", content)
        self.assertIn("tray-icon", content)

    def test_main_rs(self):
        main = TAURI_DIR / "src" / "main.rs"
        self.assertTrue(main.is_file())
        content = main.read_text()
        self.assertIn("TrayIconBuilder", content)
        self.assertIn("MenuBuilder", content)
        self.assertIn("check_engine", content)

    def test_tauri_conf(self):
        conf = TAURI_DIR / "tauri.conf.json"
        self.assertTrue(conf.is_file())
        data = json.loads(conf.read_text())
        self.assertEqual(data["productName"], "BunkerDesktop")
        self.assertIn("windows", data["app"])
        self.assertEqual(data["app"]["windows"][0]["width"], 1200)

    def test_build_rs(self):
        self.assertTrue((TAURI_DIR / "build.rs").is_file())


# ══════════════════════════════════════════════════════════
#  3. HTML Validation
# ══════════════════════════════════════════════════════════

class TestHTMLContent(unittest.TestCase):
    """Validate index.html structure and pages."""

    @classmethod
    def setUpClass(cls):
        cls.html = (SRC_DIR / "index.html").read_text(encoding="utf-8")

    def test_doctype(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))

    def test_links_styles(self):
        self.assertIn('href="styles.css"', self.html)

    def test_links_app_js(self):
        self.assertIn('src="app.js"', self.html)

    def test_dashboard_page(self):
        self.assertIn('id="page-dashboard"', self.html)

    def test_sandboxes_page(self):
        self.assertIn('id="page-sandboxes"', self.html)

    def test_terminal_page(self):
        self.assertIn('id="page-terminal"', self.html)

    def test_settings_page(self):
        self.assertIn('id="page-settings"', self.html)

    def test_sidebar_nav(self):
        self.assertIn('class="sidebar"', self.html)
        self.assertIn('data-page="dashboard"', self.html)
        self.assertIn('data-page="sandboxes"', self.html)
        self.assertIn('data-page="terminal"', self.html)
        self.assertIn('data-page="settings"', self.html)

    def test_create_modal(self):
        self.assertIn('id="create-modal"', self.html)
        self.assertIn('id="create-name"', self.html)
        self.assertIn('id="create-cpus"', self.html)
        self.assertIn('id="create-memory"', self.html)

    def test_toast_container(self):
        self.assertIn('id="toast-container"', self.html)

    def test_stat_cards(self):
        self.assertIn('id="stat-status"', self.html)
        self.assertIn('id="stat-sandboxes"', self.html)
        self.assertIn('id="stat-uptime"', self.html)
        self.assertIn('id="stat-platform"', self.html)

    def test_terminal_input(self):
        self.assertIn('id="terminal-input"', self.html)
        self.assertIn('id="terminal-output"', self.html)

    def test_sandbox_select(self):
        self.assertIn('id="terminal-sandbox-select"', self.html)


# ══════════════════════════════════════════════════════════
#  4. CSS Validation
# ══════════════════════════════════════════════════════════

class TestCSSContent(unittest.TestCase):
    """Validate styles.css design system."""

    @classmethod
    def setUpClass(cls):
        cls.css = (SRC_DIR / "styles.css").read_text(encoding="utf-8")

    def test_css_variables(self):
        for var in ["--bg", "--surface", "--accent", "--green", "--red", "--cyan", "--text"]:
            self.assertIn(var, self.css, f"CSS variable {var} missing")

    def test_sidebar_styles(self):
        self.assertIn(".sidebar", self.css)
        self.assertIn(".nav-item", self.css)

    def test_stat_card_styles(self):
        self.assertIn(".stat-card", self.css)
        self.assertIn(".stats-row", self.css)

    def test_modal_styles(self):
        self.assertIn(".modal-overlay", self.css)
        self.assertIn(".modal", self.css)

    def test_terminal_styles(self):
        self.assertIn(".terminal-output", self.css)
        self.assertIn(".terminal-input", self.css)

    def test_toast_styles(self):
        self.assertIn("#toast-container", self.css)
        self.assertIn(".toast", self.css)

    def test_animations(self):
        self.assertIn("@keyframes", self.css)
        self.assertIn("page-in", self.css)
        self.assertIn("pulse-glow", self.css)
        self.assertIn("modal-in", self.css)
        self.assertIn("toast-in", self.css)

    def test_responsive(self):
        self.assertIn("@media", self.css)

    def test_dark_theme(self):
        # Ensure background is dark
        self.assertRegex(self.css, r"--bg:\s*#0[0-9a-f]{5}")

    def test_badge_styles(self):
        self.assertIn(".badge-running", self.css)
        self.assertIn(".badge-stopped", self.css)

    def test_sandbox_card_styles(self):
        self.assertIn(".sandbox-card", self.css)
        self.assertIn(".sandbox-grid", self.css)

    def test_button_variants(self):
        for cls_name in [".btn-primary", ".btn-ghost", ".btn-danger", ".btn-success"]:
            self.assertIn(cls_name, self.css)


# ══════════════════════════════════════════════════════════
#  5. JavaScript Validation
# ══════════════════════════════════════════════════════════

class TestJSContent(unittest.TestCase):
    """Validate app.js API client and logic."""

    @classmethod
    def setUpClass(cls):
        cls.js = (SRC_DIR / "app.js").read_text(encoding="utf-8")

    def test_api_base(self):
        self.assertIn("localhost:9551", self.js)

    def test_api_methods(self):
        for method in ["engineStatus", "engineStop", "listSandboxes", "createSandbox",
                        "destroySandbox", "resetSandbox", "exec"]:
            self.assertIn(method, self.js, f"API method {method} missing")

    def test_api_endpoints(self):
        for endpoint in ["/engine/status", "/engine/stop", "/sandboxes"]:
            self.assertIn(endpoint, self.js)

    def test_navigate_function(self):
        self.assertIn("function navigate(", self.js)

    def test_refresh_functions(self):
        for fn in ["refreshAll", "refreshEngine", "refreshSandboxes"]:
            self.assertIn(f"function {fn}", self.js)

    def test_polling(self):
        self.assertIn("POLL_INTERVAL", self.js)
        self.assertIn("startPolling", self.js)

    def test_terminal_exec(self):
        self.assertIn("function terminalExec", self.js)
        self.assertIn("terminalHistory", self.js)

    def test_toast_function(self):
        self.assertIn("function toast(", self.js)

    def test_keyboard_shortcuts(self):
        self.assertIn("keydown", self.js)
        self.assertIn("Escape", self.js)

    def test_sandbox_crud(self):
        self.assertIn("function createSandbox", self.js)
        self.assertIn("function destroySandbox", self.js)
        self.assertIn("function resetSandboxAction", self.js)

    def test_modal_functions(self):
        self.assertIn("function showCreateModal", self.js)
        self.assertIn("function hideCreateModal", self.js)

    def test_utility_functions(self):
        for fn in ["escapeHtml", "formatUptime", "timeAgo"]:
            self.assertIn(f"function {fn}", self.js)

    def test_xss_protection(self):
        """Ensure escapeHtml is used when rendering user-provided data."""
        self.assertIn("escapeHtml(s.name", self.js)
        self.assertIn("escapeHtml(s.id)", self.js)

    def test_dom_content_loaded(self):
        self.assertIn("DOMContentLoaded", self.js)


# ══════════════════════════════════════════════════════════
#  6. Engine API Dashboard Serving
# ══════════════════════════════════════════════════════════

class TestEngineDashboardRoute(unittest.TestCase):
    """Verify engine api.py can serve dashboard files."""

    @classmethod
    def setUpClass(cls):
        cls.api_source = (PROJECT_ROOT / "bunkervm" / "engine" / "api.py").read_text()

    def test_dashboard_route_in_do_get(self):
        self.assertIn("/dashboard", self.api_source)
        self.assertIn("_serve_dashboard", self.api_source)

    def test_serve_dashboard_method(self):
        self.assertIn("def _serve_dashboard(self", self.api_source)

    def test_mime_types(self):
        self.assertIn("_MIME_TYPES", self.api_source)
        for ext in [".html", ".css", ".js"]:
            self.assertIn(ext, self.api_source)

    def test_path_traversal_protection(self):
        self.assertIn("path traversal", self.api_source.lower())
        self.assertIn('".."', self.api_source)

    def test_spa_fallback(self):
        """Dashboard should fall back to index.html for SPA routing."""
        self.assertIn("index.html", self.api_source)

    def test_dashboard_docstring(self):
        self.assertIn("GET  /dashboard", self.api_source)


# ══════════════════════════════════════════════════════════
#  7. Package.json Validation
# ══════════════════════════════════════════════════════════

class TestPackageJson(unittest.TestCase):
    """Validate package.json structure."""

    def test_valid_json(self):
        data = json.loads((DESKTOP_DIR / "package.json").read_text())
        self.assertEqual(data["name"], "bunkerdesktop")
        self.assertIn("version", data)

    def test_has_tauri_cli(self):
        data = json.loads((DESKTOP_DIR / "package.json").read_text())
        self.assertIn("@tauri-apps/cli", data.get("devDependencies", {}))


# ══════════════════════════════════════════════════════════
#  8. Tauri Config Validation
# ══════════════════════════════════════════════════════════

class TestTauriConfig(unittest.TestCase):
    """Validate tauri.conf.json config values."""

    @classmethod
    def setUpClass(cls):
        cls.conf = json.loads((TAURI_DIR / "tauri.conf.json").read_text())

    def test_product_name(self):
        self.assertEqual(self.conf["productName"], "BunkerDesktop")

    def test_identifier(self):
        self.assertEqual(self.conf["identifier"], "com.bunkervm.desktop")

    def test_window_dimensions(self):
        win = self.conf["app"]["windows"][0]
        self.assertGreaterEqual(win["width"], 900)
        self.assertGreaterEqual(win["height"], 600)
        self.assertTrue(win["resizable"])

    def test_tray_icon(self):
        tray = self.conf["app"]["trayIcon"]
        self.assertEqual(tray["id"], "main-tray")
        self.assertEqual(tray["tooltip"], "BunkerDesktop")

    def test_csp_allows_engine_api(self):
        csp = self.conf["app"]["security"]["csp"]
        self.assertIn("localhost:9551", csp)

    def test_frontend_dist(self):
        self.assertEqual(self.conf["build"]["frontendDist"], "../src")


# ══════════════════════════════════════════════════════════
#  9. Rust Backend Validation
# ══════════════════════════════════════════════════════════

class TestRustBackend(unittest.TestCase):
    """Validate main.rs system tray implementation."""

    @classmethod
    def setUpClass(cls):
        cls.rust = (TAURI_DIR / "src" / "main.rs").read_text()

    def test_system_tray_setup(self):
        self.assertIn("TrayIconBuilder", self.rust)

    def test_menu_items(self):
        for item in ["Open Dashboard", "Start Engine", "Stop Engine", "Quit"]:
            self.assertIn(item, self.rust)

    def test_engine_check(self):
        self.assertIn("fn is_engine_running", self.rust)
        self.assertIn("127.0.0.1:9551", self.rust)

    def test_tauri_commands(self):
        self.assertIn("#[tauri::command]", self.rust)
        self.assertIn("fn check_engine", self.rust)
        self.assertIn("fn start_engine", self.rust)

    def test_tray_menu_event_handling(self):
        self.assertIn("on_menu_event", self.rust)
        for event_id in ['"open"', '"start"', '"stop"', '"quit"']:
            self.assertIn(event_id, self.rust)

    def test_windows_subsystem(self):
        self.assertIn("windows_subsystem", self.rust)


# ══════════════════════════════════════════════════════════
#  10. Cross-cutting Concerns
# ══════════════════════════════════════════════════════════

class TestCrossCutting(unittest.TestCase):
    """Verify integration points."""

    def test_all_pages_have_page_class(self):
        """Every page section has the 'page' class."""
        html = (SRC_DIR / "index.html").read_text(encoding="utf-8")
        matches = re.findall(r'id="page-(\w+)"', html)
        self.assertGreaterEqual(len(matches), 4)
        for m in matches:
            self.assertIn(f'id="page-{m}"', html)

    def test_nav_items_match_pages(self):
        """Each nav item data-page should have a matching page."""
        html = (SRC_DIR / "index.html").read_text(encoding="utf-8")
        nav_pages = re.findall(r'data-page="(\w+)"', html)
        for p in nav_pages:
            self.assertIn(f'id="page-{p}"', html)

    def test_js_api_matches_engine_routes(self):
        """JS API endpoints should match engine API route patterns."""
        js = (SRC_DIR / "app.js").read_text(encoding="utf-8")
        api_src = (PROJECT_ROOT / "bunkervm" / "engine" / "api.py").read_text(encoding="utf-8")

        # Check key endpoints exist in both
        for path in ["/engine/status", "/sandboxes"]:
            self.assertIn(path, js, f"JS missing API path {path}")
            self.assertIn(path, api_src, f"Engine missing API path {path}")

    def test_version_consistency(self):
        """Version numbers should be consistent."""
        pkg = json.loads((DESKTOP_DIR / "package.json").read_text())
        cargo = (TAURI_DIR / "Cargo.toml").read_text()
        tauri_conf = json.loads((TAURI_DIR / "tauri.conf.json").read_text())

        # All should have 0.7.x
        self.assertTrue(pkg["version"].startswith("0.7"))
        self.assertIn("0.7", cargo)
        self.assertTrue(tauri_conf["version"].startswith("0.7"))


if __name__ == "__main__":
    unittest.main()
