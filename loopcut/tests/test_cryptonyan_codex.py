# SPDX-License-Identifier: GPL-3.0-or-later
"""Real stdio subprocess tests with a scripted Codex peer; no model or network."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "addons_core"))
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.codex_executor import CodexAppServerExecutor
from cryptonyan_asset_studio.executors import ExecutionContext, MockCodexExecutor
from cryptonyan_asset_studio.storage import write_json


class ScriptedCodex(CodexAppServerExecutor):
    def __init__(self, scenario, record, worker=None):
        super().__init__(sys.executable, worker or MockCodexExecutor())
        self.scenario, self.record = scenario, record

    def command(self):
        return [sys.executable, str(Path(__file__).with_name("fake_cryptonyan_codex.py")), self.scenario, str(self.record)]


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.trace = self.root / "test-wire.jsonl"
        write_json(self.assets / "mesh.json", {"schema": "cryptonyan.mesh-fixture/1", "objects": [{
            "name": "Platform", "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]]}]})

    def bridge(self, scenario, worker=None):
        bridge = MissionBridge(self.root / "jobs", self.assets, ScriptedCodex(scenario, self.trace, worker))
        self.addCleanup(bridge.close)
        return bridge

    def messages(self):
        return [json.loads(line) for line in self.trace.read_text(encoding="utf-8").splitlines()]

    def run_scenario(self, scenario):
        bridge = self.bridge(scenario)
        task = bridge.submit({"inputs": ["mesh.json"], "constraints": {"timeout_seconds": 5}})
        return bridge, bridge.wait(task["id"], 8)

    def test_complete_dispatch_has_measured_quality(self):
        bridge, final = self.run_scenario("tool")
        self.assertEqual(final["state"], "succeeded", final)
        result = bridge.result(final["id"])
        self.assertEqual(result["quality"]["reports"][0]["objects"][0]["vertices"], 3)
        self.assertEqual({a["path"] for a in final["artifacts"]}, {"attempt-1/quality.json", "attempt-1/codex-dispatch.json"})
        thread = next(m["params"] for m in self.messages() if m.get("method") == "thread/start")
        self.assertEqual(thread["sandbox"], "read-only")
        self.assertTrue(thread["ephemeral"])
        self.assertEqual(thread["environments"], [])
        self.assertEqual(len(thread["dynamicTools"]), 1)
        self.assertNotIn("PRIVATE_ACCOUNT_EMAIL", json.dumps(result))

    def test_repeated_tool_is_idempotent(self):
        class Counting(MockCodexExecutor):
            calls = 0
            def execute(self, mission, context):
                self.calls += 1
                return super().execute(mission, context)
        worker = Counting()
        bridge = self.bridge("repeat", worker)
        task = bridge.submit({"inputs": ["mesh.json"]})
        self.assertEqual(bridge.wait(task["id"], 8)["state"], "succeeded")
        self.assertEqual(worker.calls, 1)

    def test_early_notification_before_turn_response(self):
        _, final = self.run_scenario("early")
        self.assertEqual(final["state"], "succeeded", final)

    def test_native_approval_declined(self):
        _, final = self.run_scenario("approval")
        self.assertEqual(final["state"], "succeeded", final)
        response = next(m for m in self.messages() if m.get("id") == "approval")
        self.assertEqual(response["result"], {"decision": "decline"})

    def test_scope_change_rejected(self):
        _, final = self.run_scenario("alter_scope")
        self.assertEqual(final["state"], "succeeded", final)
        first = next(m for m in self.messages() if m.get("id") == "tool-1")
        self.assertFalse(first["result"]["success"])

    def test_unknown_tool_rejected(self):
        _, final = self.run_scenario("unknown_tool")
        self.assertEqual(final["state"], "succeeded", final)
        first = next(m for m in self.messages() if m.get("id") == "tool-1")
        self.assertFalse(first["result"]["success"])

    def test_failure_modes_fail_closed(self):
        scenarios = {"no_auth": "codex_auth_required", "api_key": "codex_auth_required",
                     "permissions": "codex_permissions", "no_audit": "codex_no_audit",
                     "failed": "codex_turn_failed", "wrong_thread": "codex_protocol",
                     "malformed": "codex_protocol", "oversized": "codex_protocol",
                     "rpc_error": "codex_request_rejected", "exit": "codex_unresponsive"}
        for scenario, code in scenarios.items():
            with self.subTest(scenario=scenario):
                bridge, final = self.run_scenario(scenario)
                self.assertEqual(final["state"], "failed", final)
                self.assertTrue(final["error"].startswith(code + ":"), final)
                self.assertNotIn("SECRET_RAW_ERROR", json.dumps(final))
                self.assertEqual(final["artifacts"], [])
                bridge.close()

    def test_timeout_interrupts_turn(self):
        bridge = self.bridge("wait")
        task = bridge.submit({"inputs": ["mesh.json"], "constraints": {"timeout_seconds": 0.3}})
        final = bridge.wait(task["id"], 5)
        self.assertEqual(final["state"], "failed")
        self.assertTrue(final["error"].startswith("timeout:"))

    def test_cancel_in_flight(self):
        bridge = self.bridge("wait")
        task = bridge.submit({"inputs": ["mesh.json"]})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.trace.exists() and '"method": "turn/start"' in self.trace.read_text():
                break
            time.sleep(0.01)
        else:
            self.fail("Turn never started")
        bridge.cancel(task["id"])
        self.assertEqual(bridge.wait(task["id"], 5)["state"], "cancelled")

    def test_probe_never_starts_thread_or_model(self):
        context = ExecutionContext(self.root, self.root, (), threading.Event(), time.monotonic() + 5)
        executor = ScriptedCodex("no_auth", self.trace)
        result = executor.probe(context)
        self.assertTrue(result["protocol_ready"])
        self.assertFalse(result["chatgpt_authenticated"])
        self.assertFalse(result["model_called"])
        self.assertEqual([m.get("method") for m in self.messages()], ["initialize", "initialized", "account/read"])

    def test_existing_profile_and_proxy_without_keys(self):
        profile = self.root / "profile"
        profile.mkdir()
        (profile / "config.toml").write_text('[mcp_servers."named.server"]\ncommand = "unused"\n')
        executor = CodexAppServerExecutor(sys.executable, MockCodexExecutor(), codex_home=profile)
        command = executor.command()
        self.assertIn('mcp_servers."named.server".enabled=false', command)
        self.assertIn('features.shell_tool=false', command)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET", "CODEX_API_KEY": "SECRET", "HTTPS_PROXY": "http://proxy:8080"}):
            environment = executor.environment()
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertEqual(environment["HTTPS_PROXY"], "http://proxy:8080")
        self.assertEqual(environment["CODEX_HOME"], str(profile.resolve()))


if __name__ == "__main__":
    unittest.main()
