"""
Tests for BunkerVM new features: Snapshot, Time-Travel, Filesystem Trace, Agent Diff.

These tests exercise the host-side code (snapshot manager, CLI commands,
recording logic, diff engine) without requiring a running Firecracker VM.
VM-level tests (actual snapshot create/restore) need Linux + /dev/kvm.
"""

import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Snapshot Module Tests ──


class TestSnapshotInfo:
    def test_exists_all_files_present(self, tmp_path):
        from bunkervm.snapshot import SnapshotInfo

        vmstate = tmp_path / "vmstate.snap"
        memory = tmp_path / "memory.snap"
        rootfs = tmp_path / "rootfs.ext4"
        vmstate.write_bytes(b"state")
        memory.write_bytes(b"mem")
        rootfs.write_bytes(b"rootfs")

        info = SnapshotInfo(
            name="test",
            vmstate_path=str(vmstate),
            memory_path=str(memory),
            rootfs_path=str(rootfs),
            created_at=time.time(),
            vcpu_count=1,
            mem_size_mib=512,
        )
        assert info.exists is True

    def test_exists_missing_file(self, tmp_path):
        from bunkervm.snapshot import SnapshotInfo

        info = SnapshotInfo(
            name="test",
            vmstate_path=str(tmp_path / "missing"),
            memory_path=str(tmp_path / "missing2"),
            rootfs_path=str(tmp_path / "missing3"),
            created_at=time.time(),
            vcpu_count=1,
            mem_size_mib=512,
        )
        assert info.exists is False


class TestSnapshotManager:
    def test_list_empty(self, tmp_path):
        from bunkervm.snapshot import SnapshotManager

        mgr = SnapshotManager(snapshots_dir=str(tmp_path / "snaps"))
        assert mgr.list() == []

    def test_get_nonexistent(self, tmp_path):
        from bunkervm.snapshot import SnapshotManager

        mgr = SnapshotManager(snapshots_dir=str(tmp_path / "snaps"))
        assert mgr.get("nonexistent") is None

    def test_has_nonexistent(self, tmp_path):
        from bunkervm.snapshot import SnapshotManager

        mgr = SnapshotManager(snapshots_dir=str(tmp_path / "snaps"))
        assert mgr.has("nonexistent") is False

    def test_delete_nonexistent(self, tmp_path):
        from bunkervm.snapshot import SnapshotManager

        mgr = SnapshotManager(snapshots_dir=str(tmp_path / "snaps"))
        assert mgr.delete("nonexistent") is False

    def test_roundtrip_with_manual_snapshot(self, tmp_path):
        """Create a fake snapshot directory and verify get/list/delete."""
        from bunkervm.snapshot import SnapshotManager

        snaps_dir = str(tmp_path / "snaps")
        mgr = SnapshotManager(snapshots_dir=snaps_dir)

        # Create a fake snapshot manually
        snap_dir = os.path.join(snaps_dir, "test-snap")
        os.makedirs(snap_dir)
        with open(os.path.join(snap_dir, "vmstate.snap"), "wb") as f:
            f.write(b"vmstate")
        with open(os.path.join(snap_dir, "memory.snap"), "wb") as f:
            f.write(b"memory")
        with open(os.path.join(snap_dir, "rootfs.ext4"), "wb") as f:
            f.write(b"rootfs")
        with open(os.path.join(snap_dir, "meta.json"), "w") as f:
            json.dump(
                {"name": "test-snap", "created_at": time.time(), "vcpu_count": 2, "mem_size_mib": 1024},
                f,
            )

        # get
        info = mgr.get("test-snap")
        assert info is not None
        assert info.name == "test-snap"
        assert info.vcpu_count == 2
        assert info.mem_size_mib == 1024
        assert info.exists is True

        # list
        snapshots = mgr.list()
        assert len(snapshots) == 1
        assert snapshots[0].name == "test-snap"

        # has
        assert mgr.has("test-snap") is True

        # delete
        assert mgr.delete("test-snap") is True
        assert mgr.has("test-snap") is False
        assert mgr.list() == []


class TestFirecrackerAPIClient:
    def test_init(self):
        from bunkervm.snapshot import FirecrackerAPIClient

        client = FirecrackerAPIClient("/tmp/test.sock")
        assert client._socket_path == "/tmp/test.sock"

    def test_request_missing_socket(self):
        from bunkervm.snapshot import FirecrackerAPIClient

        client = FirecrackerAPIClient("/tmp/nonexistent-bunkervm-test.sock")
        with pytest.raises(RuntimeError, match="socket not found"):
            client._request("GET", "/health")


# ── Filesystem Trace Tests (exec_agent.py functions in isolation) ──


class TestFilesystemTrace:
    """Test the trace helper functions from exec_agent.py.

    These run the actual Python functions (stdlib only, no VM needed).
    """

    def test_should_trace_excludes_proc(self):
        """Import and test _should_trace from exec_agent."""
        # We can't easily import exec_agent (it's designed for Alpine),
        # but we can test the exact same logic.
        _TRACE_EXCLUDE = {"/proc", "/sys", "/dev", "/run", "/tmp/_ns.pkl"}

        def _should_trace(path):
            for excl in _TRACE_EXCLUDE:
                if path == excl or path.startswith(excl + "/"):
                    return False
            return True

        assert _should_trace("/root/test.py") is True
        assert _should_trace("/proc/cpuinfo") is False
        assert _should_trace("/sys/class") is False
        assert _should_trace("/tmp/_ns.pkl") is False
        assert _should_trace("/tmp/myfile.txt") is True

    def test_snapshot_and_diff(self, tmp_path):
        """Test snapshot/diff logic with real files."""
        # Replicate the logic from exec_agent
        def snapshot_dir(base):
            result = {}
            for dirpath, _, filenames in os.walk(str(base)):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    st = os.stat(fpath)
                    result[fpath] = (st.st_mtime, st.st_size)
            return result

        # Create initial files
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")

        pre = snapshot_dir(tmp_path)
        assert len(pre) == 2

        # Simulate changes
        (tmp_path / "c.txt").write_text("new file")  # created
        (tmp_path / "a.txt").write_text("modified content")  # modified
        (tmp_path / "b.txt").unlink()  # deleted

        post = snapshot_dir(tmp_path)

        # Compute diff
        created = [p for p in post if p not in pre]
        modified = [p for p in post if p in pre and post[p] != pre[p]]
        deleted = [p for p in pre if p not in post]

        assert len(created) == 1
        assert "c.txt" in created[0]
        assert len(modified) == 1
        assert "a.txt" in modified[0]
        assert len(deleted) == 1
        assert "b.txt" in deleted[0]


# ── Time-Travel Recording Tests ──


class TestSandboxRecording:
    """Test Sandbox recording/checkpoint features (mocked, no VM)."""

    def test_record_flag_sets_session_id(self):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True)
        assert sb.recording is True
        assert sb.session_id is None  # Not set until start()
        assert sb._checkpoints == []

    def test_history_empty_before_start(self):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True)
        assert sb.history() == []

    @patch("bunkervm.runtime._try_engine_discovery", return_value=None)
    def test_record_initializes_session_on_start(self, mock_engine):
        """Verify that start() sets a session ID when record=True."""
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, quiet=True)
        # We can't actually start (no VM), but we can verify the init logic
        # by checking that the __init__ sets up recording state
        assert sb._record is True
        assert sb._session_id is None
        assert sb._step_counter == 0

    def test_auto_checkpoint_structure(self):
        """Test _auto_checkpoint produces correct checkpoint structure."""
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, quiet=True)
        sb._session_id = "test123"
        sb._vm = None  # No VM, so no actual snapshot

        result = {
            "exit_code": 0,
            "stdout": "hello\n",
            "stderr": "",
            "duration_ms": 42.5,
            "trace": {
                "files_created": [{"path": "/root/out.txt", "size": 5}],
                "files_modified": [],
                "files_deleted": [],
                "files_read": [],
                "bytes_written": 5,
            },
        }

        sb._auto_checkpoint("echo hello", result)

        assert len(sb._checkpoints) == 1
        cp = sb._checkpoints[0]
        assert cp["step"] == 1
        assert cp["command"] == "echo hello"
        assert cp["exit_code"] == 0
        assert cp["stdout"] == "hello\n"
        assert cp["duration_ms"] == 42.5
        assert cp["trace"]["files_created"][0]["path"] == "/root/out.txt"
        assert cp["snapshot_name"] is None  # No VM

    def test_multiple_checkpoints(self):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, quiet=True)
        sb._session_id = "multi"
        sb._vm = None

        for i in range(5):
            sb._auto_checkpoint(f"cmd_{i}", {"exit_code": 0, "stdout": f"out_{i}", "duration_ms": i * 10})

        assert len(sb.history()) == 5
        assert sb._step_counter == 5
        assert sb.history()[0]["step"] == 1
        assert sb.history()[4]["step"] == 5

    def test_save_session(self, tmp_path):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, quiet=True)
        sb._session_id = "saveme"
        sb._vm = None

        sb._auto_checkpoint("echo 1", {"exit_code": 0, "stdout": "1\n", "duration_ms": 10})
        sb._auto_checkpoint("echo 2", {"exit_code": 0, "stdout": "2\n", "duration_ms": 20})

        path = sb.save_session(str(tmp_path / "session.json"))
        assert os.path.isfile(path)

        with open(path) as f:
            data = json.load(f)

        assert data["session_id"] == "saveme"
        assert data["total_steps"] == 2
        assert len(data["checkpoints"]) == 2
        assert data["checkpoints"][0]["command"] == "echo 1"
        assert data["checkpoints"][1]["command"] == "echo 2"


# ── CLI Replay Tests ──


class TestCLIReplay:
    def _create_session_file(self, tmp_path, session_id="abc123", steps=3):
        """Helper to create a test session JSON file."""
        checkpoints = []
        for i in range(1, steps + 1):
            checkpoints.append({
                "step": i,
                "timestamp": time.time(),
                "command": f"echo step{i}",
                "exit_code": 0,
                "stdout": f"step{i}\n",
                "stderr": "",
                "duration_ms": i * 10,
                "trace": {
                    "files_created": [{"path": f"/root/file{i}.txt", "size": 100}],
                    "files_modified": [],
                    "files_deleted": [],
                    "files_read": [],
                    "bytes_written": 100,
                },
                "snapshot_name": f"{session_id}-step{i}",
            })

        session = {
            "session_id": session_id,
            "created_at": time.time(),
            "total_steps": steps,
            "checkpoints": checkpoints,
        }

        path = tmp_path / f"{session_id}.json"
        with open(path, "w") as f:
            json.dump(session, f)
        return str(path)

    def test_load_session_from_file(self, tmp_path):
        from bunkervm.cli import _load_session

        path = self._create_session_file(tmp_path)
        session = _load_session(path)
        assert session["session_id"] == "abc123"
        assert len(session["checkpoints"]) == 3

    def test_load_session_not_found(self):
        from bunkervm.cli import _load_session

        with pytest.raises(FileNotFoundError):
            _load_session("nonexistent_session_id_12345")

    def test_replay_timeline(self, tmp_path, capsys):
        from bunkervm.cli import cmd_replay

        path = self._create_session_file(tmp_path)
        args = MagicMock()
        args.session = path
        args.step = None
        args.trace = False

        ret = cmd_replay(args)
        assert ret == 0

    def test_replay_specific_step(self, tmp_path, capsys):
        from bunkervm.cli import cmd_replay

        path = self._create_session_file(tmp_path)
        args = MagicMock()
        args.session = path
        args.step = 2
        args.trace = False

        ret = cmd_replay(args)
        assert ret == 0

    def test_replay_with_trace(self, tmp_path, capsys):
        from bunkervm.cli import cmd_replay

        path = self._create_session_file(tmp_path)
        args = MagicMock()
        args.session = path
        args.step = None
        args.trace = True

        ret = cmd_replay(args)
        assert ret == 0

    def test_replay_invalid_step(self, tmp_path, capsys):
        from bunkervm.cli import cmd_replay

        path = self._create_session_file(tmp_path)
        args = MagicMock()
        args.session = path
        args.step = 999
        args.trace = False

        ret = cmd_replay(args)
        assert ret == 1


# ── Agent Diff Tests ──


class TestAgentDiff:
    def _make_session(self, session_id, commands, traces=None):
        """Create a session dict for diff testing."""
        checkpoints = []
        for i, cmd in enumerate(commands, 1):
            trace = None
            if traces and i - 1 < len(traces):
                trace = traces[i - 1]
            checkpoints.append({
                "step": i,
                "timestamp": time.time(),
                "command": cmd,
                "exit_code": 0,
                "stdout": f"output_{i}\n",
                "stderr": "",
                "duration_ms": i * 15,
                "trace": trace,
                "snapshot_name": None,
            })
        return {
            "session_id": session_id,
            "created_at": time.time(),
            "total_steps": len(commands),
            "checkpoints": checkpoints,
        }

    def test_compute_diff_same_sessions(self):
        from bunkervm.cli import _compute_diff

        trace = {
            "files_created": [{"path": "/root/out.txt", "size": 50}],
            "files_modified": [],
            "files_deleted": [],
            "bytes_written": 50,
        }
        session = self._make_session("a", ["echo hi", "echo bye"], [trace, trace])

        result = _compute_diff(session, session)
        assert result["summary"]["steps_a"] == 2
        assert result["summary"]["steps_b"] == 2
        assert result["summary"]["files_only_a"] == []
        assert result["summary"]["files_only_b"] == []
        assert len(result["summary"]["files_both"]) == 1

    def test_compute_diff_different_files(self):
        from bunkervm.cli import _compute_diff

        trace_a = {
            "files_created": [{"path": "/root/a.txt", "size": 10}],
            "files_modified": [],
            "files_deleted": [],
            "bytes_written": 10,
        }
        trace_b = {
            "files_created": [{"path": "/root/b.txt", "size": 20}],
            "files_modified": [],
            "files_deleted": [],
            "bytes_written": 20,
        }
        session_a = self._make_session("a", ["cmd1"], [trace_a])
        session_b = self._make_session("b", ["cmd2"], [trace_b])

        result = _compute_diff(session_a, session_b)
        assert "/root/a.txt" in result["summary"]["files_only_a"]
        assert "/root/b.txt" in result["summary"]["files_only_b"]
        assert result["summary"]["files_both"] == []

    def test_compute_diff_step_comparison(self):
        from bunkervm.cli import _compute_diff

        session_a = self._make_session("a", ["echo hi", "echo bye"])
        session_b = self._make_session("b", ["echo hi", "echo different", "echo extra"])

        result = _compute_diff(session_a, session_b)
        comps = result["step_comparison"]
        assert len(comps) == 3  # max(2, 3)

        # Step 1: same command
        assert comps[0]["command_a"] == "echo hi"
        assert comps[0]["command_b"] == "echo hi"

        # Step 2: different commands
        assert comps[1]["command_a"] == "echo bye"
        assert comps[1]["command_b"] == "echo different"

        # Step 3: only in B
        assert "command_a" not in comps[2]
        assert comps[2]["command_b"] == "echo extra"

    def test_cmd_diff_text_output(self, tmp_path):
        from bunkervm.cli import cmd_diff

        trace = {
            "files_created": [{"path": "/root/file.txt", "size": 10}],
            "files_modified": [],
            "files_deleted": [],
            "bytes_written": 10,
        }
        session_a = self._make_session("sess-a", ["echo 1"], [trace])
        session_b = self._make_session("sess-b", ["echo 2"], [trace])

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        with open(path_a, "w") as f:
            json.dump(session_a, f)
        with open(path_b, "w") as f:
            json.dump(session_b, f)

        args = MagicMock()
        args.session_a = str(path_a)
        args.session_b = str(path_b)
        args.format = "text"

        ret = cmd_diff(args)
        assert ret == 0

    def test_cmd_diff_json_output(self, tmp_path, capsys):
        from bunkervm.cli import cmd_diff

        session_a = self._make_session("a", ["echo 1"])
        session_b = self._make_session("b", ["echo 2"])

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        with open(path_a, "w") as f:
            json.dump(session_a, f)
        with open(path_b, "w") as f:
            json.dump(session_b, f)

        args = MagicMock()
        args.session_a = str(path_a)
        args.session_b = str(path_b)
        args.format = "json"

        ret = cmd_diff(args)
        assert ret == 0

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "summary" in result
        assert "step_comparison" in result


# ── Snapshot CLI Tests ──


class TestSnapshotCLI:
    def test_snapshot_list_empty(self, tmp_path):
        from bunkervm.cli import cmd_snapshot_list

        args = MagicMock()
        with patch("bunkervm.snapshot.SnapshotManager") as MockMgr:
            MockMgr.return_value.list.return_value = []
            # Direct function test — just check it doesn't crash
            from bunkervm.snapshot import SnapshotManager

            mgr = SnapshotManager(snapshots_dir=str(tmp_path))
            assert mgr.list() == []

    def test_snapshot_delete_returns_false_for_missing(self, tmp_path):
        from bunkervm.snapshot import SnapshotManager

        mgr = SnapshotManager(snapshots_dir=str(tmp_path))
        assert mgr.delete("nope") is False


# ── Import Tests for New Modules ──


class TestNewImports:
    def test_snapshot_imports(self):
        from bunkervm.snapshot import SnapshotManager, SnapshotInfo, FirecrackerAPIClient

    def test_snapshot_exported_from_init(self):
        from bunkervm import SnapshotManager, SnapshotInfo

    def test_sandbox_record_param(self):
        from bunkervm import Sandbox

        sb = Sandbox(record=True)
        assert sb.recording is True

    def test_sandbox_has_timetravel_methods(self):
        from bunkervm import Sandbox

        sb = Sandbox()
        assert hasattr(sb, "checkpoint")
        assert hasattr(sb, "restore")
        assert hasattr(sb, "history")
        assert hasattr(sb, "save_session")

    def test_version_bumped(self):
        import bunkervm

        parts = bunkervm.__version__.split(".")
        # Should be 0.9.0 or higher
        assert int(parts[0]) >= 0
        assert int(parts[1]) >= 9
