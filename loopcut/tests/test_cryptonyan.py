# SPDX-License-Identifier: GPL-3.0-or-later
"""Mission/doctor tests: real Python subprocesses, no model or network calls."""
import copy
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "addons_core"))

from cryptonyan_asset_studio.asset_doctor import audit_fixture, audit_mesh, report
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.executors import (BudgetExpired, ExecutionContext, MockCodexExecutor,
                                              RetryableFailure, run_process)
from cryptonyan_asset_studio.mcp_stdio import MCPServer, serve
from cryptonyan_asset_studio.schema import Mission, State, SuccessCriteria, transition
from cryptonyan_asset_studio.storage import Store, digest, safe_path, write_json

TRIANGLE = {"name": "Platform", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "faces": [[0, 1, 2]], "uv_layers": ["UVMap"], "material_slots": ["M_Test"]}


def quality(output):
    write_json(output / "quality.json", {"schema": "cryptonyan.quality-batch/1", "passed": True,
                                         "reports": [report([audit_mesh(TRIANGLE)])]})
    return ["quality.json"]


class SchemaTests(unittest.TestCase):
    def test_roundtrip_and_defaults(self):
        mission = Mission.parse({"inputs": ["asset.blend"]})
        self.assertEqual(Mission.parse(mission.json()), mission)
        self.assertFalse(mission.constraints.repair_copy)

    def test_invalid_values(self):
        values = [{}, {"inputs": "asset.blend"}, {"inputs": []}, {"inputs": ["a", "a"]},
                  {"inputs": ["a"], "api_key": "not-stored"}, {"inputs": ["a"], "type": "run_python"},
                  {"inputs": ["a"], "schema": "future/2"},
                  *[{"inputs": ["a"], "constraints": {"timeout_seconds": x}} for x in (True, 0, -1, float("nan"), float("inf"))],
                  *[{"inputs": ["a"], "constraints": {"max_attempts": x}} for x in (True, 0, 4, 1.2)],
                  {"inputs": ["a"], "constraints": {"repair_copy": "true"}},
                  {"inputs": ["a"], "success_criteria": {"max_triangles": -1}},
                  {"inputs": ["a"], "success_criteria": {"allow_warnings": "yes"}}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                Mission.parse(value)

    def test_transitions(self):
        transition(State.QUEUED, State.RUNNING)
        transition(State.RUNNING, State.CANCELLING)
        for a, b in ((State.SUCCEEDED, State.RUNNING), (State.CANCELLED, State.SUCCEEDED), (State.QUEUED, State.SUCCEEDED)):
            with self.assertRaises(ValueError):
                transition(a, b)


class PathTests(unittest.TestCase):
    def test_traversal_and_windows_paths(self):
        with tempfile.TemporaryDirectory() as root:
            for path in ("../x", "a/../../x", "/tmp/x", "C:/x", "C:\\x", "//server/x", "a\\x", "a//x", "./x", "x/", "x\x00"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    safe_path(root, path)
            self.assertEqual(safe_path(root, "a/b.json"), Path(root).resolve() / "a/b.json")

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            link = Path(root) / "linked"
            try:
                link.symlink_to(other, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation not permitted")
            with self.assertRaises(ValueError):
                safe_path(root, "linked/output.json")


class DoctorTests(unittest.TestCase):
    def test_metrics_and_json(self):
        row = audit_mesh(TRIANGLE)
        self.assertEqual((row["vertices"], row["edges"], row["faces"], row["triangles"]), (3, 3, 1, 1))
        self.assertEqual(row["bounds_local"], [[0, 0, 0], [1, 1, 0]])
        result = report([row])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["passed"])
        self.assertEqual(json.loads(json.dumps(result))["schema"], "cryptonyan.asset-doctor/1")

    def test_invalid_degenerate_duplicate_faces(self):
        mesh = copy.deepcopy(TRIANGLE)
        mesh["faces"] += [[0, 0, 1], [0, 1, 9], [0, 1, 2]]
        codes = {f["code"] for f in audit_mesh(mesh)["findings"]}
        self.assertTrue({"invalid_faces", "degenerate_candidates", "duplicate_candidates"} <= codes)

    def test_triangle_budget_and_warnings(self):
        criteria = SuccessCriteria(max_triangles=0)
        self.assertFalse(report([audit_mesh(TRIANGLE, criteria)], criteria)["passed"])
        self.assertFalse(report([audit_mesh(TRIANGLE)], SuccessCriteria(allow_warnings=False))["passed"])

    def test_closed_tetrahedron(self):
        mesh = copy.deepcopy(TRIANGLE)
        mesh["vertices"].append([0, 0, 1])
        mesh["faces"] = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
        row = audit_mesh(mesh)
        self.assertEqual(row["topology"]["boundary_edges"], 0)
        self.assertEqual(row["topology"]["inconsistent_winding_edges"], 0)

    def test_guard_and_nonfinite(self):
        mesh = {**TRIANGLE, "repair_guards": ["shape_keys"], "scale": [-1, 2, 1]}
        self.assertTrue({"repair_guard", "unapplied_scale"} <= {f["code"] for f in audit_mesh(mesh)["findings"]})
        with self.assertRaises(ValueError):
            audit_mesh({**TRIANGLE, "vertices": [[float("nan"), 0, 0]]})

    def test_complexity_budget(self):
        with mock.patch("cryptonyan_asset_studio.asset_doctor.MAX_VERTICES", 2):
            with self.assertRaises(ValueError):
                audit_mesh(TRIANGLE)

    def test_non_mesh_only_is_not_an_asset_pass(self):
        self.assertFalse(report([{"name": "Rig", "type": "ARMATURE", "findings": []}])["passed"])

    def test_fixtures_cannot_spoof_measured_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "spoof.json"
            write_json(path, {"schema": "cryptonyan.mesh-fixture/1", "objects": [{**TRIANGLE, "triangle_count": 0}]})
            with self.assertRaises(ValueError):
                audit_fixture(path)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.source = self.assets / "triangle.json"
        write_json(self.source, {"schema": "cryptonyan.mesh-fixture/1", "objects": [TRIANGLE]})
        self.payload = {"inputs": ["triangle.json"]}

    def bridge(self, executor=None, **kwargs):
        bridge = MissionBridge(self.root / "jobs", self.assets, executor or MockCodexExecutor(), **kwargs)
        self.addCleanup(bridge.close)
        return bridge

    def test_end_to_end_persistence_source_unchanged(self):
        before = digest(self.source)
        bridge = self.bridge()
        task = bridge.submit(self.payload)
        self.assertEqual(bridge.wait(task["id"], 10)["state"], "succeeded")
        result = bridge.result(task["id"])
        self.assertTrue(result["quality"]["passed"])
        self.assertEqual(before, digest(self.source))
        self.assertEqual([e["event"] for e in bridge.store.events(task["id"])], ["queued", "running", "attempt", "succeeded"])
        bridge.close()
        self.assertEqual(Store(self.root / "jobs").get(task["id"])["state"], "succeeded")

    def test_revision_keeps_original(self):
        bridge = self.bridge()
        task = bridge.submit(self.payload)
        original = bridge.wait(task["id"], 10)
        revision = bridge.revise(task["id"], {**self.payload, "success_criteria": {"max_triangles": 0}})
        final = bridge.wait(revision["id"], 10)
        self.assertEqual(final["revision_of"], task["id"])
        self.assertFalse(final["quality_passed"])
        self.assertEqual(final["state"], "succeeded")  # Audit ran; asset failed acceptance.
        self.assertEqual(bridge.query(task["id"]), original)

    def test_artifact_tampering(self):
        bridge = self.bridge()
        task = bridge.submit(self.payload)
        final = bridge.wait(task["id"], 10)
        safe_path(bridge.store.folder(task["id"]), final["artifacts"][0]["path"]).write_text("{}")
        with self.assertRaises(ValueError):
            bridge.result(task["id"])

    def test_path_attack_does_not_create_record(self):
        bridge = self.bridge()
        with self.assertRaises(ValueError):
            bridge.submit({"inputs": ["../outside.blend"]})
        self.assertEqual(bridge.store.all(), [])

    def test_second_owner_rejected(self):
        self.bridge()
        with self.assertRaises(RuntimeError):
            MissionBridge(self.root / "jobs", self.assets, MockCodexExecutor())

    def test_cancel_running_and_queued_and_revise_guard(self):
        started = threading.Event()

        class Blocking:
            name = "test"
            def execute(self, mission, context):
                started.set()
                while True:
                    context.checkpoint()
                    context.cancelled.wait(0.01)

        bridge = self.bridge(Blocking(), max_workers=1, max_pending=2)
        first = bridge.submit(self.payload)
        self.assertTrue(started.wait(3))
        second = bridge.submit(self.payload)
        with self.assertRaises(ValueError):
            bridge.submit(self.payload)
        with self.assertRaises(ValueError):
            bridge.revise(first["id"], self.payload)
        self.assertEqual(bridge.cancel(second["id"])["state"], "cancelled")
        bridge.cancel(first["id"])
        self.assertEqual(bridge.wait(first["id"], 3)["state"], "cancelled")
        self.assertEqual(bridge.wait(second["id"], 3)["attempts"], 0)
        self.assertEqual(bridge.cancel(first["id"])["state"], "cancelled")

    def test_bounded_retries(self):
        class Flaky:
            name = "test"
            calls = 0
            def execute(self, mission, context):
                self.calls += 1
                if self.calls < 3:
                    raise RetryableFailure("secret must never be persisted")
                return quality(context.output)

        executor = Flaky()
        bridge = self.bridge(executor)
        task = bridge.submit({**self.payload, "constraints": {"max_attempts": 3}})
        final = bridge.wait(task["id"], 5)
        self.assertEqual((final["state"], final["attempts"]), ("succeeded", 3))
        self.assertNotIn("secret", json.dumps(bridge.store.events(task["id"])))

    def test_retry_exhaustion_sanitized(self):
        class Failing:
            name = "test"
            def execute(self, mission, context):
                raise RetryableFailure("API_KEY=private-value")
        bridge = self.bridge(Failing())
        task = bridge.submit({**self.payload, "constraints": {"max_attempts": 2}})
        final = bridge.wait(task["id"], 5)
        self.assertEqual(final["attempts"], 2)
        self.assertEqual(final["state"], "failed")
        self.assertNotIn("private-value", json.dumps(final))

    def test_timeout_terminates_real_subprocess(self):
        class Sleeping:
            name = "test"
            def execute(self, mission, context):
                run_process([sys.executable, "-c", "import time; time.sleep(30)"], context)
        bridge = self.bridge(Sleeping())
        task = bridge.submit({**self.payload, "constraints": {"timeout_seconds": 0.1, "max_attempts": 3}})
        final = bridge.wait(task["id"], 5)
        self.assertEqual(final["attempts"], 1)
        self.assertEqual(final["state"], "failed")
        self.assertTrue(final["error"].startswith("timeout:"))

    def test_retry_budget_is_total(self):
        elapsed = [100.0]
        deadlines = []
        clock = SimpleNamespace(monotonic=lambda: elapsed[0])
        class Failing:
            name = "test"
            def execute(self, mission, context):
                deadlines.append(context.deadline)
                elapsed[0] += 0.6
                raise RetryableFailure()
        bridge = self.bridge(Failing())
        # Control only execution-budget clocks; OS waits and Future timeouts stay real.
        # Windows Event.wait may return before a 50 ms deadline, so an exact retry
        # count from wall-clock backoff is not a portable assertion of this contract.
        with mock.patch("cryptonyan_asset_studio.bridge.time", clock), \
                mock.patch("cryptonyan_asset_studio.executors.time", clock):
            task = bridge.submit({**self.payload, "constraints": {"timeout_seconds": 1, "max_attempts": 3}})
            final = bridge.wait(task["id"], 5)
        self.assertEqual(deadlines, [101.0, 101.0])
        self.assertEqual(final["attempts"], 2)
        self.assertEqual(final["state"], "failed")
        self.assertTrue(final["error"].startswith("timeout:"))

    def test_worker_artifact_escape(self):
        class Escaping:
            name = "test"
            def execute(self, mission, context):
                quality(context.output)
                return ["quality.json", "../source-0.json"]
        bridge = self.bridge(Escaping())
        task = bridge.submit(self.payload)
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "failed")

    def test_source_snapshot_is_immutable(self):
        started, release = threading.Event(), threading.Event()
        class Snapshot:
            name = "test"
            def execute(self, mission, context):
                started.set()
                release.wait(3)
                result = audit_fixture(context.folder / context.snapshots[0])
                write_json(context.output / "quality.json", {"schema": "cryptonyan.quality-batch/1", "reports": [result], "passed": result["passed"]})
                return ["quality.json"]
        bridge = self.bridge(Snapshot())
        task = bridge.submit(self.payload)
        self.assertTrue(started.wait(3))
        self.source.write_text("changed source")
        release.set()
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "succeeded")

    def test_restart_marks_interrupted_without_retry(self):
        bridge = self.bridge()
        task = bridge.submit(self.payload)
        bridge.wait(task["id"], 5)
        bridge.close()
        record = bridge.query(task["id"])
        record.update(state="running", artifacts=[])
        with bridge.store.connect() as conn:
            conn.execute("UPDATE tasks SET record=? WHERE id=?", (json.dumps(record), task["id"]))
        reopened = self.bridge()
        self.assertEqual(reopened.query(task["id"])["error"], "interrupted: service restarted")

    def test_missing_target_and_invalid_fixture(self):
        bridge = self.bridge()
        task = bridge.submit({**self.payload, "target_assets": ["missing"]})
        final = bridge.wait(task["id"], 5)
        self.assertEqual(final["state"], "failed")
        self.assertTrue(final["error"].startswith("target_not_found:"))

    def test_concurrency_limit(self):
        two_started = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        class Counting:
            name = "test"
            active = 0
            maximum = 0
            def execute(self, mission, context):
                with lock:
                    self.active += 1
                    self.maximum = max(self.maximum, self.active)
                    if self.active == 2:
                        two_started.set()
                try:
                    release.wait(3)
                    context.checkpoint()
                    return quality(context.output)
                finally:
                    with lock:
                        self.active -= 1
        executor = Counting()
        bridge = self.bridge(executor, max_workers=2)
        tasks = [bridge.submit(self.payload) for _ in range(5)]
        self.assertTrue(two_started.wait(3))
        release.set()
        for task in tasks:
            self.assertEqual(bridge.wait(task["id"], 5)["state"], "succeeded")
        self.assertEqual(executor.maximum, 2)

    def test_cancel_real_child_stops_before_completion(self):
        entered = threading.Event()
        class Sleeping:
            name = "test"
            def execute(self, mission, context):
                def launch(*args, **kwargs):
                    child = subprocess.Popen(*args, **kwargs)
                    entered.set()
                    return child
                run_process([sys.executable, "-c", "import time; time.sleep(30)"], context, popen=launch)
        bridge = self.bridge(Sleeping())
        task = bridge.submit(self.payload)
        self.assertTrue(entered.wait(3))
        bridge.cancel(task["id"])
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "cancelled")

    def test_inconsistent_quality_rejected(self):
        class Invalid:
            name = "test"
            def execute(self, mission, context):
                write_json(context.output / "quality.json", {"schema": "cryptonyan.quality-batch/1", "passed": True,
                    "reports": [{"schema": "cryptonyan.asset-doctor/1", "passed": False, "objects": []}]})
                return ["quality.json"]
        bridge = self.bridge(Invalid())
        task = bridge.submit(self.payload)
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "failed")

    def test_multiple_inputs(self):
        shutil_source = self.assets / "other.json"
        shutil_source.write_bytes(self.source.read_bytes())
        bridge = self.bridge()
        task = bridge.submit({"inputs": ["triangle.json", "other.json"]})
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "succeeded")
        self.assertEqual(len(bridge.result(task["id"])["quality"]["reports"]), 2)

    def test_mcp_mission_and_result(self):
        bridge = self.bridge()
        server = MCPServer(bridge)
        def call(method, params=None):
            return server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
        self.assertIn("error", call("tools/list"))
        self.assertEqual(call("initialize")["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(len(call("tools/list")["result"]["tools"]), 8)
        reply = call("tools/call", {"name": "mission_submit", "arguments": {"mission": self.payload}})
        task = json.loads(reply["result"]["content"][0]["text"])
        bridge.wait(task["id"], 5)
        reply = call("tools/call", {"name": "mission_result", "arguments": {"task_id": task["id"]}})
        self.assertFalse(reply["result"]["isError"])
        self.assertTrue(json.loads(reply["result"]["content"][0]["text"])["quality"]["passed"])

    def test_mcp_parse_errors_notifications_and_strict_arguments(self):
        bridge = self.bridge()
        source = io.StringIO('not json\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"initialize"}\n')
        destination = io.StringIO()
        serve(bridge, source, destination)
        replies = [json.loads(line) for line in destination.getvalue().splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        server = MCPServer(bridge)
        server.initialized = True
        result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "mission_query", "arguments": {"task_id": "bad", "extra": 1}}})
        self.assertEqual(result["error"]["code"], -32602)


class ProcessTests(unittest.TestCase):
    def test_no_secrets_and_mock_process(self):
        process = mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        popen = mock.Mock(return_value=process)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            context = ExecutionContext(path, path, (), threading.Event(), time.monotonic() + 10)
            with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "secret", "CUSTOM_TOKEN": "secret"}):
                run_process(["blender", "--background"], context, popen=popen)
            env = popen.call_args.kwargs["env"]
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("CUSTOM_TOKEN", env)
            self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)


class MCPSubprocessTests(unittest.TestCase):
    def test_cli_stdio_lifecycle_without_sockets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / "assets"
            assets.mkdir()
            write_json(assets / "mesh.json", {"schema": "cryptonyan.mesh-fixture/1", "objects": [TRIANGLE]})
            package_root = Path(__file__).resolve().parents[2] / "scripts" / "addons_core"
            process = subprocess.Popen([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace",
                str(root / "jobs"), "--asset-root", str(assets), "serve"],
                env={**os.environ, "PYTHONPATH": str(package_root)}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8")
            replies = queue.Queue()
            def read():
                for line in process.stdout:
                    replies.put(json.loads(line))
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            counter = 0
            def call(method, params):
                nonlocal counter
                counter += 1
                process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter, "method": method, "params": params}) + "\n")
                process.stdin.flush()
                response = replies.get(timeout=5)
                self.assertEqual(response["id"], counter)
                return response["result"]
            def tool(name, args):
                reply = call("tools/call", {"name": "mission_" + name, "arguments": args})
                self.assertFalse(reply["isError"], reply)
                return json.loads(reply["content"][0]["text"])
            try:
                call("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "test", "version": "1"}, "capabilities": {}})
                process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                process.stdin.flush()
                self.assertEqual(len(call("tools/list", {})["tools"]), 18)
                task = tool("submit", {"mission": {"inputs": ["mesh.json"]}})
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    current = tool("query", {"task_id": task["id"]})
                    if current["state"] in ("succeeded", "failed", "cancelled"):
                        break
                    time.sleep(0.02)
                self.assertEqual(current["state"], "succeeded")
                self.assertTrue(tool("result", {"task_id": task["id"]})["quality"]["passed"])
                self.assertEqual(tool("cancel", {"task_id": task["id"]})["state"], "succeeded")
                revision = tool("revise", {"task_id": task["id"], "mission": {"inputs": ["mesh.json"]}})
                self.assertEqual(revision["revision_of"], task["id"])
                process.stdin.close()
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                reader.join(timeout=2)
                if not process.stdin.closed:
                    process.stdin.close()
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
