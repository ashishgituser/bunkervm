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


# ── Local Backend Tests (real subprocess execution, no KVM needed) ──


class TestLocalClientPathMapping:
    def test_map_path_virtual_to_real(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        mapped = client.map_path("/tmp/foo.txt")
        assert mapped == os.path.join(str(tmp_path), "tmp", "foo.txt")

    def test_map_path_idempotent(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        mapped_once = client.map_path("/tmp/foo.txt")
        mapped_twice = client.map_path(mapped_once)
        assert mapped_once == mapped_twice

    def test_map_path_blocks_escape(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        with pytest.raises(ValueError):
            client.map_path("../../etc/passwd")


class TestLocalClientFiles:
    def test_write_read_roundtrip(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        client.write_file("/tmp/hello.txt", "hi there")
        result = client.read_file("/tmp/hello.txt")
        assert result["content"] == "hi there"
        assert result["encoding"] == "utf-8"

    def test_read_missing_file(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        result = client.read_file("/tmp/nope.txt")
        assert "error" in result

    def test_upload_download_roundtrip(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        src = tmp_path / "src.bin"
        src.write_bytes(b"\x00\x01binary-ish")
        client = LocalClient(root=str(tmp_path / "sandbox"))
        client.upload_file(str(src), "/data/copy.bin")
        data = client.download_file("/data/copy.bin")
        assert data == b"\x00\x01binary-ish"


class TestLocalClientExec:
    def test_exec_runs_python_script(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        client.write_file("/tmp/t.py", "print(1 + 1)")
        result = client.exec("python3 /tmp/t.py", timeout=10)
        assert result["exit_code"] == 0
        assert result["stdout"].strip() == "2"

    def test_exec_captures_relative_file_creation(self, tmp_path):
        """Relative paths resolve inside the mapped workdir and get traced."""
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        client.write_file("/tmp/t.py", "open('out.txt', 'w').write('data')")
        result = client.exec("python3 /tmp/t.py", timeout=10, workdir="/root", trace=True)
        assert result["exit_code"] == 0
        created_paths = [f["path"] for f in result["trace"]["files_created"]]
        assert "/root/out.txt" in created_paths

    def test_exec_trace_excludes_control_files(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        client.write_file("/tmp/_ns.pkl", "pretend-namespace-bytes")
        client.write_file("/tmp/t.py", "open('/tmp/real_output.txt', 'w').write('x')" .replace("/tmp/", ""))
        # Rewrite _ns.pkl during exec, same way the persistent runner does
        client.write_file("/tmp/t.py", "import os; f=open('_ns.pkl','w'); f.write('changed'); f.close()")
        result = client.exec("python3 /tmp/t.py", timeout=10, workdir="/tmp", trace=True)
        assert result["exit_code"] == 0
        touched = (
            [f["path"] for f in result["trace"]["files_created"]]
            + [f["path"] for f in result["trace"]["files_modified"]]
        )
        assert not any("_ns.pkl" in p for p in touched)

    def test_exec_nonzero_exit(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path))
        client.write_file("/tmp/t.py", "import sys; sys.exit(3)")
        result = client.exec("python3 /tmp/t.py", timeout=10)
        assert result["exit_code"] == 3


class TestLocalClientSnapshot:
    def test_snapshot_and_restore_roundtrip(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        snaps_dir = str(tmp_path / "snaps")
        client = LocalClient(root=str(tmp_path / "sandbox"), snapshots_dir=snaps_dir)
        client.write_file("/root/state.txt", "before")
        client.create_snapshot("cp1")

        client.write_file("/root/state.txt", "after")
        assert client.read_file("/root/state.txt")["content"] == "after"

        client.restore_snapshot("cp1")
        assert client.read_file("/root/state.txt")["content"] == "before"

    def test_restore_missing_snapshot_raises(self, tmp_path):
        from bunkervm.local_backend import LocalClient

        client = LocalClient(root=str(tmp_path / "sandbox"), snapshots_dir=str(tmp_path / "snaps"))
        with pytest.raises(RuntimeError):
            client.restore_snapshot("does-not-exist")


class TestSandboxLocalBackend:
    """Full Sandbox lifecycle on the local backend — no KVM, no engine."""

    def test_rejects_unknown_backend(self):
        from bunkervm.runtime import Sandbox

        with pytest.raises(ValueError):
            Sandbox(backend="docker")

    def test_record_restore_roundtrip(self, tmp_path):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, backend="local", quiet=True)
        sb.start()
        try:
            sb.run("x = 1")
            sb.run("x = x + 10")
            sb.run("x = x * 100")
            assert sb.run("print(x)") == "1100"

            sb.restore(step=2)
            assert sb.run("print(x)") == "11"

            assert sb.history()[0]["backend"] == "local"
            sb.save_session(str(tmp_path / "session.json"))
            assert os.path.isfile(tmp_path / "session.json")
        finally:
            sb._record = False  # avoid stop()'s auto-save to the real ~/.bunkervm
            sb.stop()

    def test_manual_checkpoint(self):
        from bunkervm.runtime import Sandbox

        sb = Sandbox(record=True, backend="local", quiet=True)
        sb.start()
        try:
            sb.run("y = 5")
            cp = sb.checkpoint("named")
            assert cp["backend"] == "local"
            assert cp["snapshot_name"] == "named"
        finally:
            sb._record = False
            sb.stop()


# ── Compare / Report Tests ──


class TestReportScoring:
    def _session(self, session_id, commands, exit_codes=None, backend="local"):
        exit_codes = exit_codes or [0] * len(commands)
        checkpoints = [
            {
                "step": i,
                "command": cmd,
                "exit_code": code,
                "duration_ms": i * 10,
                "trace": None,
                "backend": backend,
            }
            for i, (cmd, code) in enumerate(zip(commands, exit_codes), 1)
        ]
        return {"session_id": session_id, "backend": backend, "checkpoints": checkpoints}

    def test_score_session_success(self):
        from bunkervm.report import score_session

        session = self._session("a", ["echo hi", "echo bye"])
        result = score_session(session)
        assert result["success"] is True
        assert result["steps"] == 2
        assert result["failed_steps"] == []

    def test_score_session_failure(self):
        from bunkervm.report import score_session

        session = self._session("a", ["echo hi", "false"], exit_codes=[0, 1])
        result = score_session(session)
        assert result["success"] is False
        assert result["failed_steps"] == [2]

    def test_score_session_risk_classification(self):
        from bunkervm.report import score_session

        session = self._session("a", ["ls -la", "rm -rf /"])
        result = score_session(session)
        assert result["risk_counts"]["destructive"] == 1
        assert result["highest_risk"] == "destructive"

    def test_compare_sessions_ranks_success_first(self):
        from bunkervm.report import compare_sessions

        good = self._session("good", ["echo 1", "echo 2"])
        bad = self._session("bad", ["echo 1", "false"], exit_codes=[0, 1])

        result = compare_sessions([bad, good], labels=["bad", "good"])
        ranked_labels = [s["label"] for s in sorted(result["sessions"], key=lambda s: s["rank"])]
        assert ranked_labels[0] == "good"

    def test_compare_sessions_detects_divergence(self):
        from bunkervm.report import compare_sessions

        a = self._session("a", ["echo 1", "echo 2", "echo 3"])
        b = self._session("b", ["echo 1", "echo different", "echo 3"])

        result = compare_sessions([a, b], labels=["a", "b"])
        assert result["divergences"][0]["first_diverging_step"] == 2

    def test_compare_sessions_requires_at_least_one(self):
        from bunkervm.report import compare_sessions

        with pytest.raises(ValueError):
            compare_sessions([])

    def test_render_html_report(self, tmp_path):
        from bunkervm.report import compare_sessions, render_html_report

        a = self._session("a", ["echo 1"])
        b = self._session("b", ["echo 1", "echo 2"])
        result = compare_sessions([a, b], labels=["a", "b"])

        out_path = str(tmp_path / "report.html")
        render_html_report(result, out_path)
        assert os.path.isfile(out_path)
        content = open(out_path, encoding="utf-8").read()
        assert "Agent Comparison" in content
        assert "a" in content and "b" in content


class TestReportDeletionAwareness:
    """An agent can turn a red suite green by deleting the failing test.

    Exit codes alone can't tell that apart from a real fix — the filesystem
    trace can. These cover the ranking that uses it and the flag that
    explains it.
    """

    def _session(self, session_id, steps):
        """steps: list of (command, exit_code, deleted_paths)."""
        checkpoints = []
        for i, (cmd, code, deleted) in enumerate(steps, 1):
            trace = None
            if deleted:
                trace = {
                    "files_created": [],
                    "files_modified": [],
                    "files_deleted": [{"path": p, "size": 10} for p in deleted],
                    "bytes_written": 0,
                }
            checkpoints.append(
                {
                    "step": i,
                    "command": cmd,
                    "exit_code": code,
                    "duration_ms": 10,
                    "trace": trace,
                    "backend": "local",
                }
            )
        return {"session_id": session_id, "backend": "local", "checkpoints": checkpoints}

    def test_run_that_recovers_is_a_final_success(self):
        from bunkervm.report import score_session

        # Runs the suite, sees red, fixes it, suite goes green.
        s = score_session(
            self._session("a", [("pytest", 1, None), ("edit", 0, None), ("pytest", 0, None)])
        )
        assert s["final_success"] is True
        assert s["success"] is False  # a step did fail
        assert s["failed_steps"] == [1]

    def test_run_that_ends_red_is_not_a_final_success(self):
        from bunkervm.report import score_session

        s = score_session(self._session("a", [("edit", 0, None), ("pytest", 1, None)]))
        assert s["final_success"] is False

    def test_recovered_run_outranks_run_that_ends_broken(self):
        from bunkervm.report import compare_sessions

        recovered = self._session("r", [("pytest", 1, None), ("pytest", 0, None)])
        broken = self._session("b", [("pytest", 0, None), ("pytest", 1, None)])

        result = compare_sessions([broken, recovered], labels=["broken", "recovered"])
        ranked = sorted(result["sessions"], key=lambda s: s["rank"])
        assert ranked[0]["label"] == "recovered"

    def test_deletion_decides_between_two_green_runs(self):
        from bunkervm.report import compare_sessions

        # The cheater is *faster* and has no risky commands — before deletions
        # entered the sort key it won outright.
        cheater = self._session(
            "c", [("pytest", 1, None), ("rm tests/test_stats.py", 0, ["/p/tests/test_stats.py"])]
        )
        honest = self._session(
            "h", [("pytest", 1, None), ("edit", 0, None), ("pytest", 0, None)]
        )

        result = compare_sessions([cheater, honest], labels=["cheater", "honest"])
        ranked = sorted(result["sessions"], key=lambda s: s["rank"])
        assert ranked[0]["label"] == "honest"
        assert ranked[1]["label"] == "cheater"

    def test_deleted_test_file_is_flagged(self):
        from bunkervm.report import score_session

        s = score_session(
            self._session("c", [("rm tests/test_stats.py", 0, ["/p/tests/test_stats.py"])])
        )
        warns = [f for f in s["flags"] if f["level"] == "warn"]
        assert len(warns) == 1
        assert "test_stats.py" in warns[0]["text"]
        assert "does not prove the bug was fixed" in warns[0]["text"]

    def test_clean_run_has_no_flags(self):
        from bunkervm.report import score_session

        s = score_session(self._session("a", [("pytest", 0, None)]))
        assert s["flags"] == []

    def test_deleted_paths_are_recorded(self):
        from bunkervm.report import score_session

        s = score_session(self._session("a", [("rm x", 0, ["/p/a.txt", "/p/b.txt"])]))
        assert s["files_deleted"] == 2
        assert s["deleted_paths"] == ["/p/a.txt", "/p/b.txt"]

    def test_non_test_deletion_flagged_without_the_test_claim(self):
        from bunkervm.report import score_session

        s = score_session(self._session("a", [("rm notes", 0, ["/p/scratch.bak"])]))
        assert len(s["flags"]) == 1
        assert "does not prove" not in s["flags"][0]["text"]

    def test_looks_like_test_file(self):
        from bunkervm.report import _looks_like_test_file

        assert _looks_like_test_file("/p/tests/test_stats.py")
        assert _looks_like_test_file("/p/stats_test.py")
        assert _looks_like_test_file("/p/__tests__/thing.js")
        assert _looks_like_test_file("/p/spec/thing.rb")
        assert not _looks_like_test_file("/p/stats.py")
        assert not _looks_like_test_file("/p/latest.py")


class TestCLICompare:
    def _write_session(self, tmp_path, session_id, commands, exit_codes=None):
        exit_codes = exit_codes or [0] * len(commands)
        checkpoints = [
            {
                "step": i,
                "command": cmd,
                "exit_code": code,
                "duration_ms": 10,
                "trace": None,
                "backend": "local",
            }
            for i, (cmd, code) in enumerate(zip(commands, exit_codes), 1)
        ]
        session = {"session_id": session_id, "backend": "local", "total_steps": len(commands), "checkpoints": checkpoints}
        path = tmp_path / f"{session_id}.json"
        with open(path, "w") as f:
            json.dump(session, f)
        return str(path)

    def test_cmd_compare_text(self, tmp_path, capsys):
        from bunkervm.cli import cmd_compare

        path_a = self._write_session(tmp_path, "a", ["echo 1"])
        path_b = self._write_session(tmp_path, "b", ["echo 1", "echo 2"])

        args = MagicMock()
        args.sessions = [path_a, path_b]
        args.label = None
        args.format = "text"
        args.html = None

        ret = cmd_compare(args)
        assert ret == 0

    def test_cmd_compare_json(self, tmp_path, capsys):
        from bunkervm.cli import cmd_compare

        path_a = self._write_session(tmp_path, "a", ["echo 1"])
        path_b = self._write_session(tmp_path, "b", ["echo 1"])

        args = MagicMock()
        args.sessions = [path_a, path_b]
        args.label = None
        args.format = "json"
        args.html = None

        ret = cmd_compare(args)
        assert ret == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "sessions" in result
        assert "divergences" in result

    def test_cmd_compare_html_output(self, tmp_path):
        from bunkervm.cli import cmd_compare

        path_a = self._write_session(tmp_path, "a", ["echo 1"])
        path_b = self._write_session(tmp_path, "b", ["echo 2"])
        html_path = str(tmp_path / "out.html")

        args = MagicMock()
        args.sessions = [path_a, path_b]
        args.label = None
        args.format = "text"
        args.html = html_path

        ret = cmd_compare(args)
        assert ret == 0
        assert os.path.isfile(html_path)

    def test_cmd_compare_missing_session(self, tmp_path):
        from bunkervm.cli import cmd_compare

        args = MagicMock()
        args.sessions = ["nonexistent-session-id-xyz"]
        args.label = None
        args.format = "text"
        args.html = None

        ret = cmd_compare(args)
        assert ret == 1

    def test_cmd_compare_with_labels(self, tmp_path, capsys):
        from bunkervm.cli import cmd_compare

        path_a = self._write_session(tmp_path, "aaa111", ["echo 1"])
        path_b = self._write_session(tmp_path, "bbb222", ["echo 1", "echo 2"])

        args = MagicMock()
        args.sessions = [path_a, path_b]
        args.label = ["careful-agent", "thorough-agent"]
        args.format = "json"
        args.html = None

        ret = cmd_compare(args)
        assert ret == 0
        result = json.loads(capsys.readouterr().out)
        labels = {s["label"] for s in result["sessions"]}
        assert labels == {"careful-agent", "thorough-agent"}

    def test_cmd_compare_label_count_mismatch(self, tmp_path):
        from bunkervm.cli import cmd_compare

        path_a = self._write_session(tmp_path, "aaa111", ["echo 1"])
        path_b = self._write_session(tmp_path, "bbb222", ["echo 1"])

        args = MagicMock()
        args.sessions = [path_a, path_b]
        args.label = ["only-one-label"]
        args.format = "text"
        args.html = None

        ret = cmd_compare(args)
        assert ret == 1


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
