# SPDX-License-Identifier: GPL-3.0-or-later
"""Agent/profile integration, including real stdio + loopback HTTP (scripted GPU)."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.comfy_profiles import TextureService, load_catalog
from cryptonyan_asset_studio.comfyui_adapter import ComfyError, workflow_digest
from cryptonyan_asset_studio.materials import load_material
from cryptonyan_asset_studio.mcp_stdio import MCPServer
from test_cryptonyan_comfyui import Peer
from test_cryptonyan_materials import png


class ProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20}},
                         "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "operator-model.safetensors"}},
                         "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "template"}},
                         "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "CryptoNyan"}}}
        self.profile = {"id": "rock", "description": "Reviewed rock base-color workflow, fixed resolution/model",
                        "workflow": "workflow.json", "workflow_sha256": workflow_digest(self.workflow),
                        "prompt_inputs": [["6", "text"]], "seed_inputs": [["3", "seed"]],
                        "models": [{"name": "operator-model.safetensors", "sha256": "a" * 64,
                                    "license": "unknown", "attribution": "operator declaration"}],
                        "outputs": {"base_color": ["9", 0]}}
        self.catalog = {"schema": "cryptonyan.comfy-profiles/1", "endpoint": "http://127.0.0.1:8188",
                        "profiles": [self.profile]}
        self.save()
        self.peer = Peer()
        self.service = self.open()

    def save(self):
        (self.root / "workflow.json").write_text(json.dumps(self.workflow))
        (self.root / "profiles.json").write_text(json.dumps(self.catalog))

    def open(self):
        service = TextureService(self.root / "profiles.json", self.root / "jobs", transport=self.peer)
        self.addCleanup(service.lock.close)
        return service

    def submit(self, **kwargs):
        return self.service.submit(**{"profile": "rock", "prompt": "volcanic rock", "seed": 42,
                                      "request_id": "lava-001", **kwargs})

    def test_only_declared_parameters_change_and_template_stays_intact(self):
        result = self.submit()
        submitted = self.peer.calls[0][2]["prompt"]
        expected = copy.deepcopy(self.workflow)
        expected["6"]["inputs"]["text"] = "volcanic rock"
        expected["3"]["inputs"]["seed"] = 42
        self.assertEqual(submitted, expected)
        self.assertEqual(result["submission"], "accepted")
        self.assertEqual(json.loads((self.root / "workflow.json").read_text()), self.workflow)
        self.assertEqual(self.service.catalog()["profiles"][0]["channels"], ["base_color"])
        self.assertFalse(self.service.catalog()["model_provenance_verified"])

    def test_changed_workflow_and_duplicate_profiles_rejected(self):
        self.workflow["3"]["inputs"]["steps"] = 500
        self.save()
        with self.assertRaisesRegex(ComfyError, "approved hash"):
            load_catalog(self.root / "profiles.json")
        self.profile["workflow_sha256"] = workflow_digest(self.workflow)
        self.catalog["profiles"].append(copy.deepcopy(self.profile))
        self.save()
        with self.assertRaisesRegex(ComfyError, "Duplicate profile"):
            load_catalog(self.root / "profiles.json")

    def test_invalid_bindings_models_and_channels_rejected(self):
        original = copy.deepcopy(self.profile)
        for changes in ({"prompt_inputs": [["3", "steps"]]}, {"seed_inputs": [["6", "text"]]},
                        {"prompt_inputs": [["6", "text"], ["6", "text"]]},
                        {"outputs": {"normal": ["9", 0]}},
                        {"outputs": {"base_color": ["9", 0], "normal": ["9", 0]}},
                        {"outputs": {"base_color": ["missing", 0]}},
                        {"models": [{"name": "incomplete"}]}, {"workflow": "../outside.json"}):
            self.catalog["profiles"] = [{**original, **changes}]
            self.save()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                load_catalog(self.root / "profiles.json")

    def test_unknown_profile_and_bad_agent_parameters_make_no_requests(self):
        for changes in ({"profile": "missing"}, {"request_id": "../outside"}, {"request_id": "C:\\bad"},
                        {"seed": True}, {"seed": -1}, {"seed": 2**64}, {"prompt": " "},
                        {"prompt": "x" * 4097}, {"prompt": "x\x00"}, {"profile": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.submit(**changes)
        self.assertFalse(self.peer.calls)

    def test_idempotency_survives_restart_and_profile_change(self):
        first = self.submit()
        self.service.lock.close()
        self.catalog["profiles"] = []
        self.save()
        self.service = self.open()
        self.assertEqual(self.submit(), first)
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(self.service.status("lava-001")["status"], "queued")
        with self.assertRaisesRegex(ComfyError, "different parameters"):
            self.submit(seed=43)

    def test_uncertain_submission_returns_identity_and_never_auto_retries(self):
        self.peer.fail_submit = True
        result = self.submit()
        self.assertEqual(result["submission"], "uncertain")
        self.assertEqual(result["prompt_id"], self.peer.identity)
        self.assertTrue(result["manual_inspection_required"])
        self.service.lock.close()
        self.service = self.open()
        self.submit()
        self.assertEqual(len(self.peer.calls), 1)
        self.assertEqual(self.service.jobs()["requests"][0]["submission"], "uncertain")

    def test_crash_before_post_is_not_automatically_retried(self):
        with patch("cryptonyan_asset_studio.comfy_profiles.ComfyUIClient.submit_workflow", side_effect=OSError):
            result = self.submit()
        self.assertIsNone(result["prompt_id"])
        self.assertEqual(self.submit()["submission"], "uncertain")
        self.assertEqual(self.service.status("lava-001")["status"], "unknown")
        self.assertFalse(self.peer.calls)

    def test_unknown_request_and_incomplete_receipt_do_not_control_server(self):
        with self.assertRaises(FileNotFoundError):
            self.service.cancel("not-owned")
        (self.root / "jobs/requests/incomplete").mkdir()
        self.assertTrue(self.service.jobs()["requests"][0]["manual_inspection_required"])
        with self.assertRaises(FileNotFoundError):
            self.submit(request_id="incomplete")
        self.assertFalse(self.peer.calls)

    def test_all_remote_states_and_targeted_queue_deletion(self):
        self.submit()
        for state in ("queued", "running", "succeeded", "failed", "cancelled", "unknown"):
            self.peer.state = state
            self.assertEqual(self.service.status("lava-001")["status"], state)
        self.peer.state = "running"
        with self.assertRaises(ComfyError):
            self.service.cancel("lava-001")
        self.peer.state = "queued"
        result = self.service.cancel("lava-001")
        self.assertFalse(result["cancellation_confirmed"])
        self.assertIn(("POST", "/queue", {"delete": [self.peer.identity]}), self.peer.calls)
        self.assertFalse(any(path == "/interrupt" for _, path, _ in self.peer.calls))

    def test_collect_material_provenance_offline_reuse_and_corruption(self):
        self.submit()
        self.peer.state = "succeeded"
        result = self.service.collect("lava-001")
        material = load_material(result["material_manifest"])
        self.assertEqual(set(material["channels"]), {"base_color"})
        generation = json.loads(Path(result["generation_receipt"]).read_text())
        self.assertEqual(generation["workflow"]["6"]["inputs"]["text"], "volcanic rock")
        self.assertEqual(generation["seed"], 42)
        self.assertEqual(generation["models_declared"], self.profile["models"])
        self.assertFalse(generation["distribution_approved"])
        count = len(self.peer.calls)
        self.service.lock.close()
        self.service = self.open()
        self.assertEqual(self.service.collect("lava-001"), result)
        self.assertEqual(len(self.peer.calls), count)
        Path(result["generation_receipt"]).write_text("{}")
        with self.assertRaisesRegex(ComfyError, "integrity"):
            self.service.collect("lava-001")

    def test_pbr_outputs_are_explicit_distinct_and_dimension_checked(self):
        self.service.lock.close()
        self.profile["outputs"]["normal"] = ["9", 1]
        self.save()
        self.service = self.open()
        peer = self.peer

        def multiple(method, path, payload=None, **kwargs):
            raw = peer(method, path, payload, **kwargs)
            if path.startswith("/history/"):
                history = json.loads(raw)
                images = history[peer.identity]["outputs"]["9"]["images"]
                images.append({"filename": "normal.png", "subfolder": "", "type": "output"})
                return json.dumps(history).encode()
            if path.startswith("/view?") and "normal.png" in path:
                return png(width=self.normal_size, height=self.normal_size)
            return raw

        self.service.transport = multiple
        self.submit()
        self.peer.state = "succeeded"
        self.normal_size = 4
        with self.assertRaisesRegex(ValueError, "share dimensions"):
            self.service.collect("lava-001")
        self.assertFalse((self.root / "jobs/requests/lava-001/result").exists())
        self.normal_size = 2
        result = self.service.collect("lava-001")
        material = load_material(result["material_manifest"])
        self.assertEqual(material["normal_convention"], "OpenGL")
        self.assertEqual(material["channels"]["normal"]["color_space"], "Non-Color")

    def test_missing_channel_corrupt_png_and_failed_jobs_do_not_publish(self):
        self.submit()
        for state, image in (("queued", png()), ("failed", png()), ("succeeded", b"invalid")):
            self.peer.state, self.peer.image = state, image
            with self.assertRaises(ValueError):
                self.service.collect("lava-001")
            self.assertFalse((self.root / "jobs/requests/lava-001/result").exists())
        self.peer.image = png()
        record_path = self.root / "jobs/requests/lava-001/request.json"
        record = json.loads(record_path.read_text())
        record["outputs"]["base_color"] = ["9", 1]
        record_path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ComfyError, "missing a declared channel"):
            self.service.collect("lava-001")
        self.assertFalse(list((self.root / "jobs/requests/lava-001").glob(".collect-*")))

    def test_service_single_owner_and_request_capacity(self):
        with self.assertRaises(RuntimeError):
            TextureService(self.root / "profiles.json", self.root / "jobs")
        self.submit()
        with patch("cryptonyan_asset_studio.comfy_profiles.MAX_REQUESTS", 1):
            self.submit()  # Recovery remains possible at capacity.
            with self.assertRaisesRegex(ComfyError, "capacity"):
                self.submit(request_id="lava-002")

    def test_symlink_request_cannot_escape_workspace(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / "jobs/requests/escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable for this Windows account")
        with self.assertRaises(ValueError):
            self.submit(request_id="escape")
        self.assertFalse(list(outside.iterdir()))

    def test_mcp_opt_in_arguments_and_error_responses(self):
        for textures, count in ((None, 8), (self.service, 20)):
            server = MCPServer(None, textures)
            server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
            response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(len(response["result"]["tools"]), count)
        for arguments in ({"request_id": "not-owned"}, {"request_id": "lava-001", "workflow": {}}, {"request_id": []}):
            response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "texture_status", "arguments": arguments}})
            self.assertTrue("error" in response or response["result"]["isError"])
        self.assertFalse(self.peer.calls)

    def test_real_stdio_cli_to_http_to_material(self):
        peer = self.peer
        peer.state = "succeeded"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))

            def respond(self, payload=None):
                data = peer(self.command, self.path, payload)
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        try:
            http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            if os.environ.get("CI"):
                raise  # The GitHub acceptance test must exercise real HTTP.
            self.skipTest("Local sandbox forbids sockets; real stdio/HTTP test is required in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:" + str(http.server_port)
        self.save()
        (self.root / "assets").mkdir()
        messages = [{"jsonrpc": "2.0", "id": 0, "method": "initialize"}]
        for name, args in (("texture_profiles", {}),
                           ("texture_submit", {"profile": "rock", "prompt": "rock", "seed": 7, "request_id": "stdio-001"}),
                           ("texture_status", {"request_id": "stdio-001"}),
                           ("texture_collect", {"request_id": "stdio-001"}),
                           ("texture_inspect", {"request_id": "stdio-001"}),
                           ("texture_image", {"request_id": "stdio-001", "channel": "base_color"}),
                           ("texture_jobs", {})):
            messages.append({"jsonrpc": "2.0", "id": len(messages), "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
        try:
            process = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root / "cli"),
                                      "--asset-root", str(self.root / "assets"), "--comfy-profiles", str(self.root / "profiles.json"), "serve"],
                                     input="".join(json.dumps(m) + "\n" for m in messages), capture_output=True,
                                     text=True, timeout=30, env={**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")})
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), len(messages))
        for response in responses[1:]:
            self.assertFalse(response["result"]["isError"], response)
        status = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertEqual(status["status"], "succeeded")
        result = json.loads(responses[4]["result"]["content"][0]["text"])
        self.assertIn("base_color", load_material(result["material_manifest"])["channels"])
        review = json.loads(responses[5]["result"]["content"][0]["text"])
        self.assertTrue(review['studio']['available'])
        self.assertEqual(review['studio']['source_root'],'work:textures')
        self.assertEqual(responses[6]['result']['content'][0]['type'],'image')
        self.assertEqual(sum(path == "/prompt" for _, path, _ in peer.calls), 1)


if __name__ == "__main__":
    unittest.main()
