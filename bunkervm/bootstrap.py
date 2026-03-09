"""
BunkerVM Bootstrap — Zero-config first-run setup.

On first run, automatically downloads the pre-built BunkerVM bundle:
  - firecracker (static binary)
  - vmlinux (Linux kernel)
  - rootfs.ext4 (BunkerVM micro-OS — Alpine + Python + exec_agent)

Everything goes into ~/.bunkervm/. Users never touch build scripts.

    from .bootstrap import ensure_ready
    paths = ensure_ready()  # Downloads if needed, returns paths
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import stat
import sys
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("bunkervm.bootstrap")

# ── Constants ──

BUNKERVM_HOME = Path.home() / ".bunkervm"
BUNDLE_DIR = BUNKERVM_HOME / "bundle"
META_FILE = BUNDLE_DIR / "bundle.json"

# GitHub release config
GITHUB_REPO = "ashishgituser/bunkervm"
BUNDLE_FILENAME = "bunkervm-bundle-x86_64.tar.gz"

# Expected files in the bundle
REQUIRED_FILES = {
    "firecracker": "firecracker",
    "kernel": "vmlinux",
    "rootfs": "rootfs.ext4",
}


@dataclass
class BundlePaths:
    """Paths to the BunkerVM bundle components."""
    firecracker: str
    kernel: str
    rootfs: str
    home: str

    @property
    def ready(self) -> bool:
        return all(os.path.exists(p) for p in [self.firecracker, self.kernel, self.rootfs])


def ensure_ready(version: Optional[str] = None, force: bool = False) -> BundlePaths:
    """Ensure BunkerVM bundle is downloaded and ready.

    This is the main entry point. Call it before starting the VM.
    On first run, downloads everything automatically.
    On subsequent runs, returns instantly.

    Args:
        version: Specific release version (default: latest)
        force: Force re-download even if bundle exists

    Returns:
        BundlePaths with firecracker, kernel, rootfs paths
    """
    paths = _get_paths()

    if paths.ready and not force:
        logger.debug("Bundle ready at %s", BUNDLE_DIR)
        return paths

    # First run — need to download
    _print_status("BunkerVM first-run setup...")

    # Check prerequisites
    _check_prerequisites()

    # Create directories
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    # Try downloading pre-built bundle from GitHub Releases
    if _download_bundle(version):
        paths = _get_paths()
        if paths.ready:
            _print_status("BunkerVM ready! VM will boot in ~2 seconds.\n")
            return paths

    # Fallback: check if files exist in the project's build/ dir (dev mode)
    paths = _try_dev_mode()
    if paths and paths.ready:
        _print_status("Using local build (dev mode).\n")
        return paths

    # Nothing worked
    raise RuntimeError(
        "BunkerVM bundle not found.\n\n"
        "Options:\n"
        f"  1. Download a release from: https://github.com/{GITHUB_REPO}/releases\n"
        f"     Extract to: {BUNDLE_DIR}\n\n"
        "  2. Build locally (for contributors):\n"
        "     sudo bash build/setup-firecracker.sh\n"
        "     sudo bash build/build-sandbox-rootfs.sh\n"
    )


def _get_paths() -> BundlePaths:
    """Get bundle file paths (may not exist yet)."""
    return BundlePaths(
        firecracker=str(BUNDLE_DIR / REQUIRED_FILES["firecracker"]),
        kernel=str(BUNDLE_DIR / REQUIRED_FILES["kernel"]),
        rootfs=str(BUNDLE_DIR / REQUIRED_FILES["rootfs"]),
        home=str(BUNKERVM_HOME),
    )


def _check_prerequisites() -> None:
    """Verify the host can run Firecracker."""
    arch = platform.machine()
    if arch not in ("x86_64", "amd64", "AMD64"):
        _print_status(f"Warning: BunkerVM is built for x86_64, detected {arch}")

    # Check if we're on Linux (or WSL)
    if sys.platform != "linux":
        # We might be on Windows calling into WSL — that's fine
        # The actual VM runs in WSL/Linux
        logger.debug("Not on Linux directly (platform: %s)", sys.platform)

    # Check /dev/kvm
    if sys.platform == "linux" and not os.path.exists("/dev/kvm"):
        _print_status(
            "Warning: /dev/kvm not found. KVM is required for Firecracker.\n"
            "  WSL2: Add to .wslconfig:\n"
            "    [wsl2]\n"
            "    nestedVirtualization=true\n"
        )


def _download_bundle(version: Optional[str] = None) -> bool:
    """Download the pre-built bundle from GitHub Releases.

    Returns True if download succeeded.
    """
    try:
        # Get download URL
        if version:
            url = f"https://github.com/{GITHUB_REPO}/releases/download/{version}/{BUNDLE_FILENAME}"
        else:
            # Latest release
            url = f"https://github.com/{GITHUB_REPO}/releases/latest/download/{BUNDLE_FILENAME}"

        _print_status(f"Downloading BunkerVM bundle (~100MB)...")
        _print_status(f"  From: {url}")

        # Download to temp file
        tmp_path = BUNKERVM_HOME / f".{BUNDLE_FILENAME}.tmp"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            _download_with_progress(url, str(tmp_path))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            logger.debug("Download failed: %s", e)
            _print_status(f"  Download not available yet (this is expected for unreleased versions)")
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        # Extract
        _print_status("  Extracting...")
        try:
            with tarfile.open(str(tmp_path), "r:gz") as tar:
                # Security: check for path traversal
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise ValueError(f"Unsafe path in archive: {member.name}")
                tar.extractall(path=str(BUNDLE_DIR))
        except Exception as e:
            _print_status(f"  Extraction failed: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            return False

        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()

        # Make firecracker executable
        fc_path = BUNDLE_DIR / REQUIRED_FILES["firecracker"]
        if fc_path.exists():
            fc_path.chmod(fc_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        _print_status("  Done!")
        return True

    except Exception as e:
        logger.debug("Bundle download failed: %s", e)
        return False


def _download_with_progress(url: str, dest: str) -> None:
    """Download a file with progress indication."""
    req = urllib.request.Request(url, headers={"User-Agent": "BunkerVM-Bootstrap/0.1"})
    response = urllib.request.urlopen(req, timeout=120)

    total = int(response.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    with open(dest, "wb") as f:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = int(downloaded * 100 / total)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                _print_status(f"  [{pct:3d}%] {mb_done:.0f}/{mb_total:.0f} MB", end="\r")

    if total > 0:
        _print_status(f"  [100%] {total / (1024*1024):.0f} MB      ")


def _try_dev_mode() -> Optional[BundlePaths]:
    """Check if bundle files exist in the project build/ directory (dev mode).

    This allows contributors who build locally to skip the download.
    Files are symlinked (or copied) into ~/.bunkervm/bundle/ for consistency.
    """
    # Find project root by looking for bunkervm.toml
    candidates = [
        Path.cwd(),
        Path(__file__).parent.parent,  # bunkervm/../
    ]

    for project_root in candidates:
        kernel = project_root / "build" / "vmlinux"
        rootfs = project_root / "build" / "rootfs.ext4"

        if kernel.exists() and rootfs.exists():
            logger.info("Found local build at %s", project_root)

            # Check for firecracker
            fc_bin = shutil.which("firecracker")
            if not fc_bin:
                fc_bin = "/usr/local/bin/firecracker"
                if not os.path.exists(fc_bin):
                    _print_status("  Firecracker binary not found. Run: sudo bash build/setup-firecracker.sh")
                    return None

            # Symlink/copy into bundle dir for consistency
            BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

            _link_or_copy(fc_bin, BUNDLE_DIR / "firecracker")
            _link_or_copy(str(kernel), BUNDLE_DIR / "vmlinux")
            _link_or_copy(str(rootfs), BUNDLE_DIR / "rootfs.ext4")

            return _get_paths()

    return None


def _link_or_copy(src: str, dst: Path) -> None:
    """Symlink or copy a file into the bundle directory."""
    if dst.exists() or dst.is_symlink():
        dst.unlink()

    try:
        dst.symlink_to(src)
    except OSError:
        # Symlinks might fail on some filesystems
        shutil.copy2(src, str(dst))


def _print_status(msg: str, end: str = "\n") -> None:
    """Print bootstrap status to stderr (stdout is for MCP protocol)."""
    print(msg, file=sys.stderr, end=end, flush=True)
