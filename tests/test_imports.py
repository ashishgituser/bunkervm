"""Verify all BunkerVM imports work after rename."""
import sys

def test_imports():
    errors = []

    try:
        import bunkervm
        print(f"  ok: import bunkervm -> {bunkervm.__doc__.strip()}")
    except Exception as e:
        errors.append(f"import bunkervm: {e}")

    try:
        from bunkervm.config import BunkerVMConfig
        cfg = BunkerVMConfig()
        print(f"  ok: BunkerVMConfig, vsock_uds_path={cfg.vsock_uds_path}")
    except Exception as e:
        errors.append(f"BunkerVMConfig: {e}")

    try:
        from bunkervm.mcp_server import mcp
        print(f"  ok: FastMCP server name={mcp.name}")
    except Exception as e:
        errors.append(f"mcp_server: {e}")

    try:
        from bunkervm.safety import SafetyLevel, SafetyResult
        print(f"  ok: SafetyLevel, SafetyResult")
    except Exception as e:
        errors.append(f"safety: {e}")

    try:
        from bunkervm.audit import AuditLogger
        print(f"  ok: AuditLogger")
    except Exception as e:
        errors.append(f"AuditLogger: {e}")

    try:
        from bunkervm.bootstrap import BUNDLE_DIR, GITHUB_REPO, BUNDLE_FILENAME
        print(f"  ok: Bootstrap repo={GITHUB_REPO}, filename={BUNDLE_FILENAME}")
        print(f"      bundle_dir={BUNDLE_DIR}")
    except Exception as e:
        errors.append(f"bootstrap: {e}")

    try:
        from bunkervm.vm_manager import VMManager
        print(f"  ok: VMManager")
    except Exception as e:
        errors.append(f"VMManager: {e}")

    try:
        from bunkervm.sandbox_client import SandboxClient
        print(f"  ok: SandboxClient")
    except Exception as e:
        errors.append(f"SandboxClient: {e}")

    # Check no old nervos references in module attributes
    try:
        from bunkervm.config import BunkerVMConfig
        cfg = BunkerVMConfig()
        assert "bunkervm" in str(cfg.vsock_uds_path), f"vsock_uds_path should contain 'bunkervm': {cfg.vsock_uds_path}"
        print(f"  ok: No old 'nervos' in config paths")
    except AssertionError as e:
        errors.append(f"config paths: {e}")
    except Exception as e:
        errors.append(f"config paths check: {e}")

    try:
        from bunkervm.bootstrap import GITHUB_REPO, BUNDLE_FILENAME
        assert "bunkervm" in GITHUB_REPO.lower(), f"GITHUB_REPO should contain 'bunkervm': {GITHUB_REPO}"
        assert "bunkervm" in BUNDLE_FILENAME, f"BUNDLE_FILENAME should contain 'bunkervm': {BUNDLE_FILENAME}"
        print(f"  ok: No old 'nervos' in bootstrap constants")
    except AssertionError as e:
        errors.append(f"bootstrap constants: {e}")
    except Exception as e:
        errors.append(f"bootstrap constants check: {e}")

    return errors


if __name__ == "__main__":
    print("=" * 50)
    print("BunkerVM Import Test")
    print("=" * 50)
    errors = test_imports()
    print()
    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  X {e}")
        sys.exit(1)
    else:
        print("ALL IMPORTS PASSED!")
        sys.exit(0)
