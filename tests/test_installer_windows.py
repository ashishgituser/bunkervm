"""
Test suite for Windows Installer (BunkerDesktop).

Tests verify:
  1. All installer files exist and are well-formed
  2. PowerShell installer has required structure (9 steps, params)
  3. Inno Setup script has correct metadata and sections
  4. Launcher .cmd has engine check + wait loop
  5. Build script has ISCC detection patterns
  6. Uninstall helper has cleanup logic
  7. Version consistency across all installer files
  8. README covers both installation methods

Run:
    python -m pytest tests/test_installer_windows.py -v
"""

import os
import re
import sys
import unittest
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INSTALLER_DIR = PROJECT_ROOT / "installer" / "windows"
EXPECTED_VERSION = "0.8.3"


# ══════════════════════════════════════════════════════════
#  1. File Existence
# ══════════════════════════════════════════════════════════

class TestInstallerFilesExist(unittest.TestCase):
    """All required installer files must be present."""

    def test_installer_dir_exists(self):
        self.assertTrue(INSTALLER_DIR.is_dir(), "installer/windows/ missing")

    def test_install_desktop_ps1_exists(self):
        self.assertTrue((INSTALLER_DIR / "install-desktop.ps1").is_file())

    def test_bunkerdesktop_cmd_exists(self):
        self.assertTrue((INSTALLER_DIR / "BunkerDesktop.cmd").is_file())

    def test_inno_setup_iss_exists(self):
        self.assertTrue((INSTALLER_DIR / "BunkerDesktopSetup.iss").is_file())

    def test_build_installer_ps1_exists(self):
        self.assertTrue((INSTALLER_DIR / "build-installer.ps1").is_file())

    def test_uninstall_helper_ps1_exists(self):
        self.assertTrue((INSTALLER_DIR / "uninstall-helper.ps1").is_file())

    def test_legacy_install_ps1_exists(self):
        self.assertTrue((INSTALLER_DIR / "install.ps1").is_file(),
                        "Legacy M4 installer should still exist")

    def test_readme_exists(self):
        self.assertTrue((INSTALLER_DIR / "README.md").is_file())


# ══════════════════════════════════════════════════════════
#  2. PowerShell Installer (install-desktop.ps1)
# ══════════════════════════════════════════════════════════

class TestPowerShellInstaller(unittest.TestCase):
    """Validate structure and content of install-desktop.ps1."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "install-desktop.ps1").read_text(encoding="utf-8")

    # ── Parameters ──

    def test_has_cmdletbinding(self):
        self.assertIn("[CmdletBinding()]", self.content)

    def test_param_skipreboot(self):
        self.assertIn("$SkipReboot", self.content)

    def test_param_autostart(self):
        self.assertIn("$AutoStart", self.content)

    def test_param_distro(self):
        self.assertIn("$Distro", self.content)

    def test_param_installdir(self):
        self.assertIn("$InstallDir", self.content)

    # ── App metadata ──

    def test_app_name(self):
        self.assertRegex(self.content, r'\$AppName\s*=\s*"BunkerDesktop"')

    def test_app_version(self):
        self.assertRegex(self.content, rf'\$AppVersion\s*=\s*"{re.escape(EXPECTED_VERSION)}"')

    # ── 9 installation steps ──

    def test_step1_windows_version(self):
        self.assertIn("Step 1", self.content)
        self.assertIn("Windows version", self.content)
        self.assertIn("19041", self.content)

    def test_step2_wsl2(self):
        self.assertIn("Step 2", self.content)
        self.assertIn("WSL2", self.content)

    def test_step3_distro(self):
        self.assertIn("Step 3", self.content)
        self.assertIn("distro", self.content.lower())

    def test_step4_wslconfig(self):
        self.assertIn("Step 4", self.content)
        self.assertIn(".wslconfig", self.content)
        self.assertIn("nestedVirtualization", self.content)

    def test_step5_bunkervm_install(self):
        self.assertIn("Step 5", self.content)
        self.assertIn("pip install", self.content)

    def test_step6_firecracker(self):
        self.assertIn("Step 6", self.content)
        match = re.search(r"[Ff]irecracker|bundle", self.content)
        self.assertIsNotNone(match, "Step 6 should mention firecracker/bundle")

    def test_step7_deploy_files(self):
        self.assertIn("Step 7", self.content)
        self.assertIn("dashboard", self.content.lower())

    def test_step8_shortcuts(self):
        self.assertIn("Step 8", self.content)
        self.assertIn("Start Menu", self.content)
        self.assertIn("Desktop", self.content)

    def test_step9_registry(self):
        self.assertIn("Step 9", self.content)
        self.assertIn("Add/Remove Programs", self.content)

    # ── Key functionality ──

    def test_creates_install_dir(self):
        self.assertIn("LOCALAPPDATA", self.content)

    def test_admin_check(self):
        self.assertIn("WindowsBuiltInRole", self.content)

    def test_wsl_invoke(self):
        self.assertIn("wsl -d", self.content)

    def test_creates_shortcut(self):
        self.assertIn("WScript.Shell", self.content)
        self.assertIn("CreateShortcut", self.content)

    def test_registry_uninstall(self):
        self.assertIn("Uninstall\\", self.content)
        self.assertIn("UninstallString", self.content)

    def test_scheduled_task_autostart(self):
        self.assertIn("ScheduledTask", self.content)
        self.assertIn("AtLogOn", self.content)

    def test_generates_inline_uninstaller(self):
        self.assertIn("uninstall.ps1", self.content)

    def test_completion_banner(self):
        self.assertIn("Installed!", self.content)

    def test_has_logging(self):
        self.assertIn("install-log.txt", self.content)

    def test_correct_engine_port(self):
        self.assertIn("9551", self.content)


# ══════════════════════════════════════════════════════════
#  3. Launcher (BunkerDesktop.cmd)
# ══════════════════════════════════════════════════════════

class TestLauncher(unittest.TestCase):
    """Validate the BunkerDesktop.cmd launcher."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "BunkerDesktop.cmd").read_text(encoding="utf-8")

    def test_is_batch_file(self):
        self.assertTrue(self.content.strip().startswith("@echo off"))

    def test_engine_port(self):
        self.assertIn("9551", self.content)

    def test_dashboard_url(self):
        self.assertIn("localhost", self.content)
        self.assertIn("/dashboard", self.content)

    def test_checks_engine_status(self):
        self.assertIn("/engine/status", self.content)

    def test_starts_engine_via_wsl(self):
        self.assertIn("wsl", self.content)
        self.assertIn("engine start", self.content)

    def test_wait_loop(self):
        self.assertIn("wait", self.content.lower())
        self.assertIn("30", self.content)  # 30 second timeout

    def test_opens_browser(self):
        self.assertIn("start ", self.content)  # start command opens default browser

    def test_delayed_expansion(self):
        self.assertIn("EnableDelayedExpansion", self.content)

    def test_has_title(self):
        self.assertIn("title BunkerDesktop", self.content)

    def test_handles_already_running(self):
        self.assertIn("already running", self.content)


# ══════════════════════════════════════════════════════════
#  4. Inno Setup Script (BunkerDesktopSetup.iss)
# ══════════════════════════════════════════════════════════

class TestInnoSetupScript(unittest.TestCase):
    """Validate the Inno Setup .iss installer script."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")

    # ── Metadata ──

    def test_app_name(self):
        self.assertIn('#define MyAppName "BunkerDesktop"', self.content)

    def test_app_version(self):
        self.assertIn(f'#define MyAppVersion "{EXPECTED_VERSION}"', self.content)

    def test_app_publisher(self):
        self.assertIn('#define MyAppPublisher "BunkerVM"', self.content)

    def test_app_id(self):
        # Inno Setup uses {{ to escape literal brace
        self.assertRegex(self.content, r"AppId=\{\{[A-Fa-f0-9\-]+\}")

    # ── Setup section ──

    def test_default_dir(self):
        self.assertIn("{localappdata}", self.content)

    def test_compression(self):
        self.assertIn("lzma2", self.content)

    def test_min_version(self):
        self.assertIn("10.0.19041", self.content)

    def test_64bit_mode(self):
        self.assertIn("x64compatible", self.content)

    def test_license_file(self):
        self.assertIn("LicenseFile", self.content)

    def test_icon_file(self):
        self.assertIn("icon.ico", self.content)

    def test_output_filename(self):
        # .iss uses {#MyAppVersion} preprocessor variable in OutputBaseFilename
        self.assertIn("BunkerDesktopSetup-{#MyAppVersion}", self.content)

    # ── Tasks ──

    def test_task_desktopicon(self):
        self.assertIn('Name: "desktopicon"', self.content)

    def test_task_autostart(self):
        self.assertIn('Name: "autostart"', self.content)

    def test_task_setupwsl(self):
        self.assertIn('Name: "setupwsl"', self.content)

    # ── Files section ──

    def test_dashboard_files(self):
        self.assertIn("dashboard", self.content)
        self.assertIn("desktop\\src", self.content)

    def test_includes_launcher(self):
        self.assertIn("BunkerDesktop.cmd", self.content)

    def test_includes_license(self):
        self.assertIn("LICENSE", self.content)

    def test_includes_uninstall_helper(self):
        self.assertIn("uninstall-helper.ps1", self.content)

    # ── Icons section ──

    def test_start_menu_icon(self):
        self.assertIn("{group}", self.content)

    def test_desktop_icon(self):
        self.assertIn("{commondesktop}", self.content)

    # ── Registry ──

    def test_path_registry(self):
        self.assertIn("HKCU", self.content)
        self.assertIn("Environment", self.content)
        self.assertIn("Path", self.content)

    # ── Code section ──

    def test_needs_add_path_function(self):
        self.assertIn("NeedsAddPath", self.content)

    def test_initialize_wizard(self):
        self.assertIn("InitializeWizard", self.content)

    def test_wsl_check(self):
        self.assertIn("wsl.exe", self.content)

    # ── Uninstall ──

    def test_uninstall_stops_engine(self):
        self.assertIn("[UninstallRun]", self.content)
        self.assertIn("engine/stop", self.content)

    def test_uninstall_deletes_files(self):
        self.assertIn("[UninstallDelete]", self.content)


# ══════════════════════════════════════════════════════════
#  5. Build Script (build-installer.ps1)
# ══════════════════════════════════════════════════════════

class TestBuildScript(unittest.TestCase):
    """Validate the build-installer.ps1 script."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "build-installer.ps1").read_text(encoding="utf-8")

    def test_has_innosetuppath_param(self):
        self.assertIn("$InnoSetupPath", self.content)

    def test_searches_program_files(self):
        self.assertIn("ProgramFiles", self.content)

    def test_searches_localappdata(self):
        self.assertIn("LOCALAPPDATA", self.content)

    def test_checks_path_env(self):
        self.assertIn("Get-Command", self.content)
        self.assertIn("ISCC.exe", self.content)

    def test_creates_assets_dir(self):
        self.assertIn("assets", self.content)
        self.assertIn("New-Item", self.content)

    def test_creates_placeholder_icon(self):
        self.assertIn("icon.ico", self.content)
        self.assertIn("placeholder", self.content.lower())

    def test_compiles_iss(self):
        self.assertIn("BunkerDesktopSetup.iss", self.content)
        self.assertIn("iscc", self.content.lower())

    def test_reports_output_size(self):
        self.assertIn("MB", self.content)

    def test_fallback_message(self):
        self.assertIn("install-desktop.ps1", self.content)

    def test_creates_output_dir(self):
        self.assertIn("Output", self.content)


# ══════════════════════════════════════════════════════════
#  6. Uninstall Helper (uninstall-helper.ps1)
# ══════════════════════════════════════════════════════════

class TestUninstallHelper(unittest.TestCase):
    """Validate the uninstall-helper.ps1 cleanup script."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "uninstall-helper.ps1").read_text(encoding="utf-8")

    def test_stops_engine(self):
        self.assertIn("engine/stop", self.content)
        self.assertIn("9551", self.content)

    def test_removes_scheduled_task(self):
        self.assertIn("Unregister-ScheduledTask", self.content)
        self.assertIn("BunkerVM Engine", self.content)

    def test_optional_wsl_cleanup(self):
        self.assertIn("~/.bunkervm", self.content)
        self.assertIn("wsl", self.content)

    def test_asks_before_wsl_removal(self):
        self.assertIn("Read-Host", self.content)


# ══════════════════════════════════════════════════════════
#  7. Version Consistency
# ══════════════════════════════════════════════════════════

class TestVersionConsistency(unittest.TestCase):
    """All installer files must reference the same version."""

    def test_ps1_installer_version(self):
        content = (INSTALLER_DIR / "install-desktop.ps1").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_VERSION, content)

    def test_iss_version(self):
        content = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_VERSION, content)

    def test_build_script_version(self):
        content = (INSTALLER_DIR / "build-installer.ps1").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_VERSION, content)

    def test_readme_version(self):
        content = (INSTALLER_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_VERSION, content)

    def test_pyproject_version_matches(self):
        """Installer version should match pyproject.toml version."""
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*"([^"]+)"', pyproject)
        self.assertIsNotNone(match, "version not found in pyproject.toml")
        self.assertEqual(match.group(1), EXPECTED_VERSION,
                         f"pyproject.toml version {match.group(1)} != installer {EXPECTED_VERSION}")


# ══════════════════════════════════════════════════════════
#  8. README Coverage
# ══════════════════════════════════════════════════════════

class TestReadme(unittest.TestCase):
    """README covers both installation methods and usage."""

    @classmethod
    def setUpClass(cls):
        cls.content = (INSTALLER_DIR / "README.md").read_text(encoding="utf-8")

    def test_title(self):
        self.assertIn("BunkerDesktop", self.content)

    def test_method1_powershell(self):
        self.assertIn("PowerShell", self.content)
        self.assertIn("install-desktop.ps1", self.content)

    def test_method2_inno_setup(self):
        self.assertIn("Inno Setup", self.content)
        self.assertIn("BunkerDesktopSetup", self.content)

    def test_prerequisites(self):
        self.assertIn("Windows", self.content)
        self.assertIn("WSL2", self.content)

    def test_file_layout(self):
        self.assertIn("BunkerDesktop.cmd", self.content)
        self.assertIn("bunkervm.cmd", self.content)
        self.assertIn("dashboard", self.content)

    def test_usage_instructions(self):
        self.assertIn("engine start", self.content)
        self.assertIn("engine status", self.content)
        self.assertIn("sandbox", self.content)

    def test_uninstall_instructions(self):
        self.assertIn("Uninstall", self.content)

    def test_no_stale_m4_content(self):
        """Ensure old M4 content has been removed."""
        self.assertNotIn("BunkerVM\\", self.content,
                         "Stale M4 reference to BunkerVM\\ (should be BunkerDesktop)")


# ══════════════════════════════════════════════════════════
#  9. Cross-File References
# ══════════════════════════════════════════════════════════

class TestCrossFileReferences(unittest.TestCase):
    """Validate cross-references between installer files are consistent."""

    def test_iss_references_launcher(self):
        iss = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")
        self.assertIn("BunkerDesktop.cmd", iss)

    def test_iss_references_uninstall_helper(self):
        iss = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")
        self.assertIn("uninstall-helper.ps1", iss)

    def test_build_references_iss(self):
        build = (INSTALLER_DIR / "build-installer.ps1").read_text(encoding="utf-8")
        self.assertIn("BunkerDesktopSetup.iss", build)

    def test_readme_references_all_files(self):
        readme = (INSTALLER_DIR / "README.md").read_text(encoding="utf-8")
        for filename in ["install-desktop.ps1", "build-installer.ps1",
                         "BunkerDesktopSetup.iss", "BunkerDesktop.cmd",
                         "uninstall-helper.ps1"]:
            with self.subTest(file=filename):
                self.assertIn(filename, readme,
                              f"README should reference {filename}")

    def test_engine_port_consistent(self):
        """All files that reference the engine port should use 9551."""
        for filename in ["install-desktop.ps1", "BunkerDesktop.cmd",
                         "uninstall-helper.ps1"]:
            with self.subTest(file=filename):
                content = (INSTALLER_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("9551", content,
                              f"{filename} should reference port 9551")

    def test_distro_default_ubuntu(self):
        """All files should default to Ubuntu distro."""
        for filename in ["install-desktop.ps1", "BunkerDesktop.cmd"]:
            with self.subTest(file=filename):
                content = (INSTALLER_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("Ubuntu", content)


# ══════════════════════════════════════════════════════════
#  10. Security & Best Practices
# ══════════════════════════════════════════════════════════

class TestSecurityPractices(unittest.TestCase):
    """Validate installer follows security best practices."""

    def test_ps1_strict_mode(self):
        content = (INSTALLER_DIR / "install-desktop.ps1").read_text(encoding="utf-8")
        self.assertIn("Set-StrictMode", content)

    def test_ps1_error_action_stop(self):
        content = (INSTALLER_DIR / "install-desktop.ps1").read_text(encoding="utf-8")
        self.assertIn('$ErrorActionPreference = "Stop"', content)

    def test_build_script_error_action_stop(self):
        content = (INSTALLER_DIR / "build-installer.ps1").read_text(encoding="utf-8")
        self.assertIn('$ErrorActionPreference = "Stop"', content)

    def test_iss_lowest_privileges(self):
        """Installer should not require admin unless WSL setup is chosen."""
        iss = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", iss)

    def test_iss_localappdata_install(self):
        """Should install to per-user location, not Program Files."""
        iss = (INSTALLER_DIR / "BunkerDesktopSetup.iss").read_text(encoding="utf-8")
        self.assertIn("{localappdata}", iss)

    def test_launcher_no_hardcoded_paths(self):
        """Launcher should use environment variables, not hardcoded paths."""
        content = (INSTALLER_DIR / "BunkerDesktop.cmd").read_text(encoding="utf-8")
        self.assertNotIn("C:\\Users\\", content)


if __name__ == "__main__":
    unittest.main()
