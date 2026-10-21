# SPDX-License-Identifier: GPL-3.0-or-later
"""Static profile diagnostics and actual stdio/HTTP wiring; no GPU inference."""
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
from cryptonyan_asset_studio.comfy_preflight import inspect_profile, preflight, MAX_INFO_BYTES
from cryptonyan_asset_studio.comfy_profiles import TextureService
from cryptonyan_asset_studio.comfyui_adapter import ComfyError, workflow_digest
from cryptonyan_asset_studio.mcp_stdio import MCPServer


def fixtures():
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    workflow = {
        "1": node("CheckpointLoaderSimple", ckpt_name="rock.safetensors"),
        "2": node("CLIPTextEncode", text="template", clip=["1", 1]),
        "3": node("EmptyLatentImage", width=512, height=512, batch_size=1),
        "4": node("KSampler", seed=0, steps=20, cfg=7.0, sampler_name="euler", scheduler="normal",
                  denoise=1.0, model=["1", 0], positive=["2", 0], negative=["2", 0], latent_image=["3", 0]),
        "5": node("VAEDecode", samples=["4", 0], vae=["1", 2]),
        "6": node("SaveImage", images=["5", 0], filename_prefix="CryptoNyan"),
    }

    def meta(inputs, outputs, output_node=False):
        return {"input": {"required": inputs}, "output": outputs, "output_node": output_node}

    info = {
        "CheckpointLoaderSimple": meta({"ckpt_name": [["rock.safetensors"]]}, ["MODEL", "CLIP", "VAE"]),
        "CLIPTextEncode": meta({"text": ["STRING", {"multiline": True}], "clip": ["CLIP"]}, ["CONDITIONING"]),
        "EmptyLatentImage": meta({"width": ["INT", {"min": 16, "max": 8192}], "height": ["INT"], "batch_size": ["INT"]}, ["LATENT"]),
        "KSampler": meta({"seed": ["INT", {"min": 0, "max": 2**64-1}], "steps": ["INT", {"min": 1, "max": 10000}],
                          "cfg": ["FLOAT"], "sampler_name": [["euler", "heun"]], "scheduler": [["normal"]],
                          "denoise": ["FLOAT", {"min": 0, "max": 1}], "model": ["MODEL"], "positive": ["CONDITIONING"],
                          "negative": ["CONDITIONING"], "latent_image": ["LATENT"]}, ["LATENT"]),
        "VAEDecode": meta({"samples": ["LATENT"], "vae": ["VAE"]}, ["IMAGE"]),
        "SaveImage": meta({"images": ["IMAGE"], "filename_prefix": ["STRING"]}, [], True),
    }
    profile = {"id": "rock", "description": "Configured rock texture", "workflow": "workflow.json",
               "workflow_sha256": workflow_digest(workflow), "template": workflow,
               "prompt_inputs": [["2", "text"]], "seed_inputs": [["4", "seed"]],
               "models": [{"name": "rock.safetensors", "sha256": "a"*64, "license": "unknown", "attribution": "declared"}],
               "outputs": {"base_color": ["6", 0]}}
    return profile, info


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.info = fixtures()
        self.calls = []

    def transport(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload, kwargs))
        return json.dumps(self.info).encode()

    def inspect(self, **kwargs):
        return inspect_profile(self.profile, self.info, kwargs.get("prompt", "wet rock"), kwargs.get("seed", 42))

    def codes(self, report=None):
        return {i["code"] for i in (report or self.inspect())["issues"]}

    def test_effective_graph_and_metadata_hash_without_mutating_template(self):
        original = copy.deepcopy(self.profile)
        report = preflight(self.profile, "http://127.0.0.1:8188", "wet rock", 42, transport=self.transport)
        self.assertEqual(report["status"], "compatible")
        effective = copy.deepcopy(self.profile["template"])
        effective["2"]["inputs"]["text"] = "wet rock"
        effective["4"]["inputs"]["seed"] = 42
        self.assertEqual(report["effective_workflow_sha256"], workflow_digest(effective))
        self.assertEqual(report["object_info_sha256"], workflow_digest(self.info))
        self.assertEqual(report["checked_choices"], 3)
        self.assertEqual(self.profile, original)
        self.assertEqual(self.calls, [("GET", "/object_info", None, {"limit": MAX_INFO_BYTES, "timeout": 10})])
        for key in ("submission_performed", "gpu_execution_validated", "model_provenance_verified", "distribution_approved"):
            self.assertFalse(report[key])
        self.assertNotIn("wet rock", json.dumps(report))

    def test_missing_node_and_selected_checkpoint_are_actionable(self):
        del self.info["VAEDecode"]
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [["different.safetensors"]]
        report = self.inspect()
        self.assertEqual(report["status"], "blocked")
        self.assertIn({"severity": "error", "code": "choice_unavailable", "node": "1", "input": "ckpt_name"}, report["issues"])
        self.assertIn("node_unavailable", self.codes(report))

    def test_required_input_and_invalid_literal_type(self):
        del self.profile["template"]["4"]["inputs"]["cfg"]
        self.profile["template"]["3"]["inputs"]["width"] = True
        self.assertTrue({"required_input_missing", "literal_type_mismatch"} <= self.codes())

    def test_proposed_seed_and_numeric_bounds_not_only_template_checked(self):
        self.info["KSampler"]["input"]["required"]["seed"][1]["max"] = 100
        self.assertIn("literal_out_of_range", self.codes(self.inspect(seed=101)))
        self.assertEqual(self.inspect(seed=100)["status"], "compatible")
        self.profile["template"]["3"]["inputs"]["width"] = 8
        self.assertIn("literal_out_of_range", self.codes())

    def test_proposed_prompt_checked_against_combo(self):
        self.info["CLIPTextEncode"]["input"]["required"]["text"] = [["template"]]
        self.assertIn("choice_unavailable", self.codes())

    def test_missing_nodes_outputs_and_mismatched_links(self):
        for value, code in ((["absent", 0], "link_node_missing"), (["1", 9], "link_output_missing"),
                            (["1", 0], "link_type_mismatch"), (["1", True], "invalid_link"), (["1"], "invalid_link")):
            with self.subTest(value=value):
                self.profile["template"]["2"]["inputs"]["clip"] = value
                self.assertIn(code, self.codes())

    def test_cycle_and_disconnected_nodes_checked(self):
        self.profile["template"]["4"]["inputs"]["latent_image"] = ["4", 0]
        self.profile["template"]["unused"] = {"class_type": "MissingCustomNode", "inputs": {}}
        self.assertTrue({"workflow_cycle", "node_unavailable"} <= self.codes())

    def test_modern_combo_and_empty_choices(self):
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = ["COMBO", {"options": ["rock.safetensors"]}]
        self.assertEqual(self.inspect()["status"], "compatible")
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][1]["options"] = []
        self.assertIn("choice_unavailable", self.codes())

    def test_custom_dynamic_inputs_and_remote_nodes_need_review(self):
        self.info["KSampler"]["api_node"] = True
        self.info["KSampler"]["input"]["required"]["seed"] = ["CUSTOM_SEED"]
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0].append("second.safetensors")
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"].append({"remote": {"route": "/models"}})
        report = self.inspect()
        self.assertEqual(report["status"], "needs_review")
        self.assertTrue({"custom_literal_unchecked", "remote_api_node", "dynamic_input_unchecked"} <= self.codes(report))

    def test_malformed_schemas_and_wildcard_links_never_claim_compatibility(self):
        for spec in (None, [], [None], ["INT", []], ["INT", {}, {}], ["INT", {"max": "lots"}]):
            with self.subTest(spec=spec):
                self.info["KSampler"]["input"]["required"]["seed"] = spec
                self.assertEqual(self.inspect()["status"], "needs_review")
        self.info["KSampler"]["input"]["required"]["seed"] = ["INT"]
        self.info["CLIPTextEncode"]["input"]["required"]["clip"] = ["*"]
        self.assertIn("dynamic_link_type", self.codes())

    def test_output_bindings_require_output_nodes_and_custom_png_review(self):
        self.info["SaveImage"]["output_node"] = False
        self.assertIn("channel_not_output_node", self.codes())
        self.info["SaveImage"]["output_node"] = True
        self.info["CustomSave"] = self.info["SaveImage"]
        self.profile["template"]["6"]["class_type"] = "CustomSave"
        self.assertEqual(self.inspect()["status"], "needs_review")
        self.assertIn("custom_saved_png_output_unchecked", self.codes())

    def test_invalid_parameters_and_nonloopback_endpoint_make_no_calls(self):
        for prompt, seed in (("", 0), ("x", True), ("x", -1), ("x", 2**64), ("x\0", 1)):
            with self.assertRaises(ComfyError):
                preflight(self.profile, "http://127.0.0.1:8188", prompt, seed, transport=self.transport)
        with self.assertRaises(ComfyError):
            preflight(self.profile, "http://example.com:8188", "rock", 1, transport=self.transport)
        self.assertFalse(self.calls)

    def test_unavailable_invalid_and_oversized_responses_do_not_leak_raw_errors(self):
        for raw in (b"not-json", b"[]", b"{}", b'{"node":NaN}', b"x"*(MAX_INFO_BYTES+1)):
            with self.subTest(length=len(raw)):
                report = preflight(self.profile, "http://127.0.0.1:8188", "x", 1, transport=lambda *a, **k: raw)
                self.assertEqual(report["status"], "unavailable")
                self.assertFalse(report["submission_performed"])
        def failed(*args, **kwargs):
            raise OSError("private traceback and paths")
        report = preflight(self.profile, "http://127.0.0.1:8188", "x", 1, transport=failed)
        self.assertNotIn("private", json.dumps(report))
        self.assertEqual(report["status"], "unavailable")

    def test_budgets_cap_work_and_diagnostics(self):
        with patch("cryptonyan_asset_studio.comfy_preflight.MAX_NODES", 2):
            self.assertIn("workflow_node_budget", self.codes())
        self.info["KSampler"]["input"]["required"] = {str(i): ["INT"] for i in range(120)}
        report = self.inspect()
        self.assertEqual(len(report["issues"]), 100)
        self.assertGreater(report["omitted_issues"], 0)
        self.assertEqual(report["status"], "blocked")

    def test_metadata_is_refetched_and_checks_are_not_cached(self):
        first = preflight(self.profile, "http://127.0.0.1:8188", "x", 1, transport=self.transport)
        self.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[]]
        second = preflight(self.profile, "http://127.0.0.1:8188", "x", 1, transport=self.transport)
        self.assertNotEqual(first["object_info_sha256"], second["object_info_sha256"])
        self.assertEqual(second["status"], "blocked")
        self.assertEqual(len(self.calls), 2)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile, self.info = fixtures()
        self.catalog = {"schema": "cryptonyan.comfy-profiles/1", "endpoint": "http://127.0.0.1:8188",
                        "profiles": [{k: v for k, v in self.profile.items() if k != "template"}]}
        self.save()

    def save(self):
        (self.root / "profiles.json").write_text(json.dumps(self.catalog))
        (self.root / "workflow.json").write_text(json.dumps(self.profile["template"]))

    def test_mcp_tool_readonly_service_recovery_and_unknown_profiles(self):
        calls = []
        def peer(method, path, payload=None, **kwargs):
            calls.append((method, path))
            return json.dumps(self.info).encode()
        with TextureService(self.root / "profiles.json", self.root / "jobs", transport=peer) as service:
            def snapshot():
                # Windows protects the lock byte against reads through another
                # handle. Check its metadata, and all other file bytes, instead.
                lock_path = Path(service.lock.file.name).resolve()
                return {p.relative_to(self.root): (p.stat().st_size, p.stat().st_mtime_ns)
                        if p.resolve() == lock_path else p.read_bytes()
                        for p in self.root.rglob("*") if p.is_file()}
            before = snapshot()
            server = MCPServer(None, service)
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            message = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "texture_preflight",
                       "arguments": {"profile": "rock", "prompt": "wet rock", "seed": 42}}}
            result = server.handle(message)["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"])["status"], "compatible")
            self.assertEqual(before, snapshot())
            self.assertEqual(service.jobs()["requests"], [])
            message["params"]["arguments"]["profile"] = "missing"
            self.assertTrue(server.handle(message)["result"]["isError"])
            message["params"]["arguments"]["workflow"] = {}
            self.assertIn("error", server.handle(message))
        self.assertEqual(calls, [("GET", "/object_info")])
        with TextureService(self.root / "profiles.json", self.root / "jobs", transport=peer) as service:
            self.assertEqual(service.preflight("rock", "wet rock", 42)["status"], "compatible")

    def test_real_cli_and_stdio_read_only_http_diagnostic(self):
        calls, info = [], self.info
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append((self.command, self.path))
                data = json.dumps(info).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_POST(self):
                calls.append((self.command, self.path))
                self.send_error(405)
            def log_message(self, *args):
                pass
        try:
            http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            if os.environ.get("CI"):
                raise
            self.skipTest("Local sandbox forbids sockets; real CLI/stdio/HTTP is required in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:" + str(http.server_port)
        self.save()
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        try:
            args = [sys.executable, "-m", "cryptonyan_asset_studio.comfy_preflight", str(self.root / "profiles.json"),
                    "--profile", "rock", "--prompt", "wet rock", "--seed", "42"]
            cli = subprocess.run(args, capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)["status"], "compatible")
            info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[]]
            cli = subprocess.run(args, capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(cli.returncode, 2, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)["status"], "blocked")
            (self.root / "assets").mkdir()
            messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "texture_preflight",
                         "arguments": {"profile": "rock", "prompt": "wet rock", "seed": 42}}}]
            cli = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root / "jobs"),
                                  "--asset-root", str(self.root / "assets"), "--comfy-profiles", str(self.root / "profiles.json"), "serve"],
                                 input="".join(json.dumps(m)+"\n" for m in messages), capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            response = json.loads(cli.stdout.splitlines()[1])["result"]
            self.assertFalse(response["isError"])
            self.assertEqual(json.loads(response["content"][0]["text"])["status"], "blocked")
            self.assertFalse(list((self.root / "jobs/textures/requests").iterdir()))
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=5)
        self.assertEqual(calls, [("GET", "/object_info")] * 3)


if __name__ == "__main__":
    unittest.main()
