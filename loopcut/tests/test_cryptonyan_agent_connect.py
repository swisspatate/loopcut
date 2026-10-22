# SPDX-License-Identifier: GPL-3.0-or-later
"""Real MCP launcher tests; no external model/client/GPU needed."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio import agent_connect as connect
from cryptonyan_asset_studio.mcp_stdio import PROTOCOL
from cryptonyan_asset_studio.storage import OwnerLock, Store, digest


class LocalPeer:
    """Bounded test peer for the exported launcher, including graceful EOF cleanup."""
    def __init__(self, path, client):
        spec = connect.launch_spec(path, client)
        self.process = subprocess.Popen([spec["command"], *spec["args"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8")
        self.replies = queue.Queue()
        def read():
            for line in self.process.stdout:
                self.replies.put(json.loads(line))
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        self.identity = 0

    def call(self, method, params=None):
        self.identity += 1
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.identity,
            "method": method, "params": params or {}}) + "\n")
        self.process.stdin.flush()
        reply = self.replies.get(timeout=5)
        assert reply["id"] == self.identity, reply
        return reply["result"]

    def tool(self, name, args):
        result = self.call("tools/call", {"name": name, "arguments": args})
        assert not result["isError"], result
        return json.loads(result["content"][0]["text"])

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdout.close()


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cryptonyan connection é-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assets = self.root / "assets with spaces"
        self.assets.mkdir()
        self.path = self.root / "connection.json"
        self.config = {"schema": connect.SCHEMA, "executor": "mock", "python": sys.executable,
                       "workspace": str(self.root / "work"), "asset_root": str(self.assets),
                       "blender": "", "comfy_profiles": "", "game_project": ""}
        connect.save_config(self.path, self.config)

    def save(self):
        connect.save_config(self.path, self.config, replace=True)

    def optional_services(self):
        from cryptonyan_asset_studio.comfyui_adapter import workflow_digest
        project = self.root / "game"
        project.mkdir()
        (project / "CryptoNyan.uproject").write_text('{"FileVersion":3}', encoding="utf-8")
        (project / "Content").mkdir()
        (project / "Content" / "Cat.uasset").write_bytes(b"existing asset")
        workflow = {"1": {"class_type": "Fixture", "inputs": {"text": "rock", "seed": 0}},
                    "2": {"class_type": "SaveImage", "inputs": {}}}
        (self.root / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
        catalog = {"schema": "cryptonyan.comfy-profiles/1", "endpoint": "http://127.0.0.1:8188",
                   "profiles": [{"id": "rock", "description": "Test fixture, no GPU inference",
                       "workflow": "workflow.json", "workflow_sha256": workflow_digest(workflow),
                       "prompt_inputs": [["1", "text"]], "seed_inputs": [["1", "seed"]],
                       "models": [{"name": "test.safetensors", "sha256": "a" * 64,
                                   "license": "unknown", "attribution": "fixture"}],
                       "outputs": {"base_color": ["2", 0]}}]}
        path = self.root / "profiles.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        self.config.update(comfy_profiles=str(path), game_project=str(project))
        self.save()

    def test_roundtrip_json_and_toml_use_isolated_absolute_launcher(self):
        claude = json.loads(connect.export_client(self.path, "claude"))["mcpServers"]["cryptonyan"]
        codex = tomllib.loads(connect.export_client(self.path, "codex"))["mcp_servers"]["cryptonyan"]
        for client, spec in (("claude", claude), ("codex", codex)):
            self.assertEqual(spec["command"], sys.executable)
            self.assertEqual(spec["args"][0], "-I")
            self.assertEqual(spec["args"][-1], client)
            self.assertTrue(Path(spec["args"][1]).is_file())
            self.assertIn(str(self.path), spec["args"])
            self.assertNotIn("env", spec)
        self.assertNotEqual(connect.client_workspace(self.config, "claude"),
                            connect.client_workspace(self.config, "codex"))

    def test_export_does_not_edit_client_settings_or_create_workspace(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        for client in connect.CLIENTS:
            connect.export_client(self.path, client)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()})
        self.assertFalse(Path(self.config["workspace"]).exists())

    def test_schema_rejects_unknown_paths_controls_and_executor(self):
        for changes in ({"executor": "codex"}, {"token": "SECRET"}, {"python": "python"},
                        {"workspace": ""}, {"asset_root": 2}, {"blender": "/a\n/b"},
                        {"executor": "blender"}, {"schema": "other"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                connect.validate_config({**self.config, **changes})

    def test_refuses_overwriting_existing_unrelated_config(self):
        with self.assertRaises(ValueError):
            connect.save_config(self.path, self.config)
        other = self.root / ".mcp.json"
        original = '{"mcpServers":{"existing":{"command":"keep"}}}'
        other.write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            connect.save_config(other, self.config, replace=True)
        self.assertEqual(other.read_text(encoding="utf-8"), original)

    def test_invalid_and_oversized_profiles(self):
        for content in ("x" * 65537, "{", "[]"):
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                connect.load_config(self.path)

    def test_paths_block_overlapping_inputs_and_workspace(self):
        for workspace in (self.assets, self.assets / "jobs", self.root):
            with self.subTest(workspace=workspace), self.assertRaises(ValueError):
                connect.validate_paths({**self.config, "workspace": str(workspace)})
        self.optional_services()
        with self.assertRaisesRegex(ValueError, "game project"):
            connect.validate_paths({**self.config, "workspace": self.config["game_project"]})

    def test_shell_wrappers_and_missing_paths_rejected(self):
        wrapper = self.root / "python.cmd"
        wrapper.write_text("unused", encoding="utf-8")
        for changes in ({"python": str(wrapper)}, {"asset_root": str(self.root / "missing")},
                        {"executor": "blender", "blender": str(self.root / "absent.exe")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                connect.validate_paths({**self.config, **changes})

    def test_unknown_client_rejected(self):
        with self.assertRaises(ValueError):
            connect.launch_spec(self.path, "../../other")

    def test_offline_check_never_starts_process_or_http(self):
        self.optional_services()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("Process started")), \
                mock.patch("cryptonyan_asset_studio.comfyui_adapter.LocalHTTP.__call__",
                           side_effect=AssertionError("Network used")):
            report = connect.diagnose(self.path)
        self.assertEqual(report["status"], "checked")
        self.assertEqual([c["status"] for c in report["checks"]], ["ready", "not_tested", "not_tested"])
        self.assertFalse(Path(self.config["workspace"]).exists())

    def test_real_probe_all_tools_with_optional_services_without_live_comfy(self):
        self.optional_services()
        report = connect.probe_mcp(self.path, "codex")
        self.assertEqual(report["status"], "ready")
        self.assertIn("texture_preflight", report["tools"])
        self.assertIn("project_inventory", report["tools"])
        self.assertFalse(report["model_called"])
        self.assertFalse(report["client_application_verified"])
        self.assertFalse(Path(self.config["workspace"]).exists())

    def test_probe_leaves_live_locked_queue_byte_identical(self):
        folder = connect.client_workspace(self.config, "claude")
        store = Store(folder)
        store.create({"id": "a" * 32, "state": "queued", "executor": "must_not_be_opened"})
        lock = OwnerLock(folder / "owner.lock")
        self.addCleanup(lock.close)
        before = {p.name: digest(p) for p in folder.iterdir() if p.is_file()}
        result = connect.probe_mcp(self.path, "claude")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(before, {p.name: digest(p) for p in folder.iterdir() if p.is_file()})
        self.assertEqual(store.get("a" * 32)["state"], "queued")

    def test_real_launcher_from_unrelated_cwd_calls_inventory(self):
        self.optional_services()
        spec = connect.launch_spec(self.path, "claude")
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "project_inventory", "arguments": {"query": "Cat", "offset": 0, "limit": 10}}}]
        environment = {**os.environ, "PYTHONPATH": str(self.root / "nonexistent")}
        result = subprocess.run([spec["command"], *spec["args"]], cwd=self.assets, env=environment,
            input="\n".join(json.dumps(r) for r in requests) + "\n", capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout.splitlines()[1])["result"]
        self.assertFalse(response["isError"])
        self.assertIn("Cat.uasset", response["content"][0]["text"])
        self.assertTrue((connect.client_workspace(self.config, "claude") / "missions.sqlite3").exists())
        self.assertFalse(connect.client_workspace(self.config, "codex").exists())

    def test_two_clients_can_connect_and_audit_without_queue_lock_conflict(self):
        (self.assets / "mesh.json").write_text(json.dumps({"schema": "cryptonyan.mesh-fixture/1", "objects": [{
            "name": "Triangle", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]]}]}))
        peers = []
        for client in connect.CLIENTS:
            peer = LocalPeer(self.path, client)
            self.addCleanup(peer.close)
            peers.append(peer)
            self.assertEqual(peer.call("initialize")["protocolVersion"], PROTOCOL)
        for peer in peers:
            task = peer.tool("mission_submit", {"mission": {"inputs": ["mesh.json"]}})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                current = peer.tool("mission_query", {"task_id": task["id"]})
                if current["state"] in ("succeeded", "failed", "cancelled"):
                    break
                time.sleep(0.02)
            self.assertEqual(current["state"], "succeeded", current)
            result = peer.tool("mission_result", {"task_id": task["id"]})
            self.assertTrue(result["quality"]["passed"])
        self.assertTrue(all((connect.client_workspace(self.config, c) / "missions.sqlite3").exists()
                            for c in connect.CLIENTS))

    def test_comfy_probe_only_reads_stats(self):
        self.optional_services()
        calls = []
        def http(*args, **kwargs):
            calls.append((args, kwargs))
            return b'{"system":{},"devices":[{"name":"test GPU"}]}'
        report = connect.probe_comfy(self.config, transport=http)
        self.assertEqual(report["status"], "reachable")
        self.assertFalse(report["generation_submitted"])
        self.assertFalse(report["models_and_gpu_verified"])
        self.assertEqual(calls, [(("GET", "/system_stats"), {"limit": 65536, "timeout": 3})])
        self.assertEqual(report["profiles"], ["rock"])

    def test_bad_comfy_responses_are_not_reported_as_ready(self):
        self.optional_services()
        for data in (b"bad json", b"[]", b'{"system":{},"devices":{}}'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                connect.probe_comfy(self.config, transport=lambda *a, **kw: data)
        self.assertEqual(connect.probe_comfy({**self.config, "comfy_profiles": ""}),
                         {"status": "not_configured"})

    def test_failures_have_no_raw_subprocess_or_http_output(self):
        self.optional_services()
        with mock.patch.object(connect, "probe_mcp", side_effect=RuntimeError("SECRET_TOKEN")), \
                mock.patch.object(connect, "probe_comfy", side_effect=ValueError("PRIVATE_ACCOUNT")):
            report = connect.diagnose(self.path, mcp=True, comfy=True)
        self.assertEqual(report["status"], "blocked")
        self.assertNotIn("SECRET_TOKEN", json.dumps(report))
        self.assertNotIn("PRIVATE_ACCOUNT", json.dumps(report))

    def test_probe_timeout_and_invalid_protocol(self):
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 1)):
            with self.assertRaisesRegex(ValueError, "timed out"):
                connect.probe_mcp(self.path, "claude")
        def fake_run(*args, **kwargs):
            kwargs["stdout"].write(b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
            return subprocess.CompletedProcess(args[0], 0)
        with mock.patch.object(subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "handshake"):
                connect.probe_mcp(self.path, "claude")

    def test_cli_init_export_and_check(self):
        path = self.root / "cli.json"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        prefix = [sys.executable, "-m", "cryptonyan_asset_studio.agent_connect"]
        args = ["init", str(path), "--workspace", str(self.root / "cli-work"),
                "--asset-root", str(self.assets), "--executor", "mock"]
        result = subprocess.run(prefix + args, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(prefix + ["export", str(path), "--client", "codex"], env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertIn("cryptonyan", tomllib.loads(result.stdout)["mcp_servers"])
        result = subprocess.run(prefix + ["check", str(path), "--probe-mcp"], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["checks"][1]["status"], "ready")


BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Blender unavailable; optional sidebar validation requires a real executable")
class ConnectionBlenderTests(unittest.TestCase):
    def test_sidebar_register_save_load_copy_unregister_and_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec",
                "--threads", "1", "--python-exit-code", "1", "--python",
                str(ROOT / "loopcut/harness/cryptonyan_connection_fixture.py"), "--", temporary, sys.executable],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CRYPTONYAN_CONNECTION_ASSERTIONS_PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
