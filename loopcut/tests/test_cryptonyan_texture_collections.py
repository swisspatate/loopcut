# SPDX-License-Identifier: GPL-3.0-or-later
"""Collection recovery, ownership and actual MCP/HTTP wiring; scripted GPU outputs."""
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
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.comfy_profiles import TextureService
from cryptonyan_asset_studio.comfyui_adapter import ComfyError
from cryptonyan_asset_studio.game_project import GameProject, LFS_HEADER
from cryptonyan_asset_studio.storage import digest
from cryptonyan_asset_studio.texture_collections import TextureCollections, requests_for
from test_cryptonyan_comfy_preflight import fixtures
from test_cryptonyan_materials import png


class MultiPeer:
    def __init__(self, info):
        self.info, self.calls, self.jobs = info, [], {}
        self.fail_submit, self.auto_success = False, False

    def __call__(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload))
        if path == "/object_info":
            return json.dumps(self.info).encode()
        if path == "/prompt":
            identity = payload["prompt_id"]
            self.jobs[identity] = {"state": "succeeded" if self.auto_success else "queued", "workflow": payload["prompt"]}
            if self.fail_submit:
                raise ComfyError("Response lost after accepted POST")
            result = {"prompt_id": identity, "node_errors": {}}
        elif path.startswith("/history/"):
            identity = path.rsplit("/", 1)[1]
            state = self.jobs[identity]["state"]
            result = {} if state in ("queued", "running", "unknown") else {identity: {
                "status": {"completed": True, "status_str": "success" if state == "succeeded" else "error",
                           "messages": [["execution_interrupted", {}]] if state == "cancelled" else []},
                "outputs": {"6": {"images": [{"filename": identity + ".png", "subfolder": "", "type": "output"}]}}}}
        elif path == "/queue" and method == "POST":
            for identity in payload["delete"]:
                self.jobs[identity]["state"] = "unknown"
            return b""
        elif path == "/queue":
            result = {"queue_running": [[0, k] for k, v in self.jobs.items() if v["state"] == "running"],
                      "queue_pending": [[0, k] for k, v in self.jobs.items() if v["state"] == "queued"]}
        elif path.startswith("/view?"):
            identity = parse_qs(urlsplit(path).query)["filename"][0][:-4]
            return png(rgb=(self.jobs[identity]["workflow"]["4"]["inputs"]["seed"] % 256, 100, 50))
        else:
            raise AssertionError(path)
        return json.dumps(result).encode()


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "game"
        (self.game / "Content").mkdir(parents=True)
        (self.game / "Game.uproject").write_text('{"FileVersion":3}')
        for name in ("Rock", "Wall"):
            (self.game / "Content" / (name + ".uasset")).write_bytes((name + " opaque fixture").encode())
        self.profile, info = fixtures()
        self.catalog = {"schema": "cryptonyan.comfy-profiles/1", "endpoint": "http://127.0.0.1:8188",
                        "profiles": [{k: v for k, v in self.profile.items() if k != "template"}]}
        self.save_catalog()
        self.peer = MultiPeer(info)
        self.spec = {"schema": "cryptonyan.texture-collection/1", "collection_id": "garden", "profile": "rock",
                     "style": "Stylized garden, cool jade palette, uniform light", "seed": 42,
                     "items": [{"id": "rock-wet", "target": "Content/Rock.uasset", "surface": "Rock / Stone",
                                "description": "Wet stone, fine cracks"},
                               {"id": "wall-moss", "target": "Content/Wall.uasset", "surface": "Wall / Stone",
                                "description": "Mossy brickwork"}]}
        self.open()

    def save_catalog(self):
        (self.root / "profiles.json").write_text(json.dumps(self.catalog))
        (self.root / "workflow.json").write_text(json.dumps(self.profile["template"]))

    def open(self):
        self.textures = TextureService(self.root / "profiles.json", self.root / "jobs", transport=self.peer)
        self.addCleanup(self.textures.lock.close)
        self.project = GameProject(self.game, self.textures)
        self.collections = TextureCollections(self.project)

    def plan(self):
        return self.collections.plan(self.spec)

    def advance(self):
        return self.collections.advance("garden")

    def collect(self):
        return self.collections.collect("garden")

    def posts(self):
        return [call for call in self.peer.calls if call[1] == "/prompt"]

    def succeed(self):
        for job in self.peer.jobs.values():
            job["state"] = "succeeded"

    def test_offline_reviewable_plan_seed_stability_and_project_unchanged(self):
        before = {p.relative_to(self.game): digest(p) for p in self.game.rglob("*") if p.is_file()}
        result = self.plan()
        self.assertFalse(self.peer.calls)
        self.assertFalse(result["submission_performed"])
        self.assertFalse(result["visual_consistency_verified"])
        self.assertEqual(self.plan(), result)
        self.assertEqual(self.collections.listing()["collections"], [{"collection_id": "garden", "items": 2, "collected": 0}])
        requests = requests_for(self.spec)
        reordered = {**self.spec, "items": list(reversed(self.spec["items"]))}
        self.assertEqual(requests_for(reordered), list(reversed(requests)))
        self.assertNotEqual(requests[0]["request"]["seed"], requests[1]["request"]["seed"])
        self.assertEqual(requests[0]["request"]["prompt"], self.spec["style"] + "\n\n" + self.spec["items"][0]["description"])
        self.assertEqual(before, {p.relative_to(self.game): digest(p) for p in self.game.rglob("*") if p.is_file()})

    def test_full_collection_sequential_requests_verified_index_and_offline_recovery(self):
        plan = self.plan()["plan"]
        self.assertEqual(self.advance()["action"], "submitted")
        self.assertEqual(self.advance()["action"], "wait_or_inspect")
        self.assertEqual(len(self.posts()), 1)
        self.succeed()
        self.assertEqual(self.advance()["action"], "collect")
        self.assertIsNone(self.collect()["index_file"])
        self.assertEqual(self.advance()["action"], "submitted")
        self.succeed()
        index_path = Path(self.collect()["index_file"])
        index = json.loads(index_path.read_text())
        self.assertEqual([x["id"] for x in index["items"]], [x["id"] for x in self.spec["items"]])
        self.assertFalse(index["visual_consistency_verified"])
        for entry, planned in zip(index["items"], plan["items"]):
            self.assertEqual(entry["candidate_sha256"], digest(self.textures.root / entry["candidate"]))
            self.assertEqual(entry["source"], planned["source"])
        calls = len(self.peer.calls)
        self.textures.lock.close()
        self.catalog["profiles"] = []
        self.save_catalog()
        self.open()
        self.assertEqual(self.collect()["index_file"], str(index_path))
        self.assertEqual(self.advance()["action"], "complete")
        self.assertEqual(len(self.peer.calls), calls)
        self.assertEqual(len(self.posts()), 2)

    def test_lost_post_response_restart_does_not_resubmit_or_advance(self):
        self.plan()
        self.peer.fail_submit = True
        result = self.advance()
        self.assertEqual(result["result"]["submission"], "uncertain")
        self.textures.lock.close()
        self.open()
        self.assertEqual(self.advance()["action"], "wait_or_inspect")
        self.assertEqual(len(self.posts()), 1)
        self.succeed()  # Accepted job can still be recovered using its original prompt receipt.
        self.collect()
        self.assertEqual(len(self.posts()), 1)

    def test_interruption_before_submit_and_after_binding_safely_resumes_same_id(self):
        self.plan()
        with patch.object(self.project, "texture_submit", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError):
                self.advance()
        self.assertEqual(self.collections.status("garden")["items"][0]["state"], "prepared")
        with patch.object(self.textures, "submit", side_effect=RuntimeError("interrupted after binding")):
            with self.assertRaises(RuntimeError):
                self.advance()
        self.assertFalse(self.posts())
        self.advance()
        self.advance()
        self.assertEqual(len(self.posts()), 1)

    def test_missing_request_receipt_requires_inspection_never_resubmits(self):
        self.plan()
        self.advance()
        request_id = requests_for(self.spec)[0]["request"]["request_id"]
        (self.textures._folder(request_id) / "request.json").unlink()
        self.assertEqual(self.advance()["action"], "manual_inspection_required")
        self.assertEqual(len(self.posts()), 1)

    def test_source_drift_before_preflight_and_during_preflight_blocks_post(self):
        self.plan()
        path = self.game / "Content/Wall.uasset"
        original = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.advance()
        self.assertFalse(self.peer.calls)
        path.write_bytes(original)
        preflight = self.textures.preflight
        def change(*args):
            result = preflight(*args)
            path.write_bytes(b"changed during metadata read")
            return result
        with patch.object(self.textures, "preflight", side_effect=change), self.assertRaisesRegex(ValueError, "source changed"):
            self.advance()
        self.assertFalse(self.posts())

    def test_changed_profile_stops_new_jobs_but_existing_jobs_can_be_collected(self):
        self.plan()
        self.advance()
        self.succeed()
        self.textures.profiles["rock"]["models"] = []
        self.collect()
        with self.assertRaisesRegex(ValueError, "profile or endpoint changed"):
            self.advance()
        self.assertEqual(len(self.posts()), 1)

    def test_descriptor_drift_during_preflight_blocks_before_binding_and_post(self):
        self.plan()
        preflight = self.textures.preflight
        def change(*args):
            result = preflight(*args)
            (self.game / "Game.uproject").write_text('{"FileVersion":3,"EngineAssociation":"changed"}')
            return result
        with patch.object(self.textures, "preflight", side_effect=change), self.assertRaisesRegex(ValueError, "descriptor changed"):
            self.advance()
        self.assertFalse(self.posts())
        self.assertFalse(list(self.project.bindings.iterdir()))

    def test_template_drift_and_contract_drift_during_preflight_prevent_post(self):
        self.plan()
        profile = self.textures.profiles["rock"]
        original = copy.deepcopy(profile["template"])
        profile["template"]["4"]["inputs"]["steps"] = 21
        with self.assertRaisesRegex(ValueError, "approved hash"):
            self.advance()
        profile["template"] = original
        preflight = self.textures.preflight
        def change(*args):
            result = preflight(*args)
            profile["outputs"]["roughness"] = ["6", 1]
            return result
        with patch.object(self.textures, "preflight", side_effect=change), self.assertRaisesRegex(ValueError, "profile changed during"):
            self.advance()
        self.assertFalse(self.posts())

    def test_preflight_blocked_review_and_unavailable_never_submit(self):
        self.plan()
        for status in ("blocked", "needs_review", "unavailable"):
            with patch.object(self.textures, "preflight", return_value={"status": status}):
                self.assertEqual(self.advance()["action"], "preflight_blocked")
        self.assertFalse(self.posts())
        self.assertEqual(self.collections.status("garden")["items"][0]["state"], "planned")

    def test_failed_cancelled_unknown_and_running_jobs_do_not_launch_next(self):
        self.plan()
        self.advance()
        for state in ("failed", "cancelled", "unknown", "running"):
            next(iter(self.peer.jobs.values()))["state"] = state
            result = self.advance()
            self.assertEqual(result["action"], "wait_or_inspect")
            self.assertEqual(result["status"]["status"], state)
        self.assertEqual(len(self.posts()), 1)

    def test_pending_cancellation_uses_existing_owned_request_without_global_interrupt(self):
        self.plan()
        item = self.advance()["item"]
        self.textures.cancel(item["request_id"])
        self.assertEqual(self.advance()["status"]["status"], "unknown")
        self.assertFalse(any(call[1] == "/interrupt" for call in self.peer.calls))
        self.assertEqual(len(self.posts()), 1)

    def test_source_drift_during_collection_retains_outputs_without_candidate(self):
        self.plan()
        self.advance()
        self.succeed()
        collect = self.textures.collect
        def change(request_id):
            result = collect(request_id)
            (self.game / "Content/Rock.uasset").write_bytes(b"changed during download")
            return result
        with patch.object(self.textures, "collect", side_effect=change), self.assertRaises(ValueError):
            self.collect()
        self.assertFalse(list(self.project.bindings.glob("*.candidate.json")))
        self.assertFalse((self.collections._folder("garden") / "index.json").exists())

    def test_corrupt_candidate_and_material_are_not_overwritten_or_extended(self):
        self.plan()
        self.advance()
        self.succeed()
        candidate = self.collect()["candidate"]
        path = Path(candidate["candidate_manifest"])
        original = path.read_bytes()
        path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "candidate integrity"):
            self.advance()
        self.assertEqual(path.read_text(), "{}")
        path.write_bytes(original)
        Path(candidate["texture"]["material_manifest"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.advance()
        self.assertEqual(len(self.posts()), 1)

    def test_plan_intent_and_index_tampering_detected(self):
        planned = self.plan()
        plan_path = Path(planned["plan_file"])
        raw = plan_path.read_bytes()
        record = json.loads(raw)
        record["plan"]["specification"]["style"] = "changed"
        plan_path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "plan integrity"):
            self.advance()
        plan_path.write_bytes(raw)
        self.advance()
        intent = self.collections._folder("garden") / "item-rock-wet.intent.json"
        raw = intent.read_bytes()
        intent.write_text("{}")
        with self.assertRaisesRegex(ValueError, "intent mismatch"):
            self.advance()
        intent.write_bytes(raw)
        self.succeed()
        self.collect()
        self.advance()
        self.succeed()
        index = Path(self.collect()["index_file"])
        index.write_text("{}")
        with self.assertRaisesRegex(ValueError, "index integrity"):
            self.collect()
        self.assertEqual(index.read_text(), "{}")

    def test_foreign_request_before_plan_and_after_plan_cannot_be_adopted(self):
        request = requests_for(self.spec)[0]["request"]
        plain = {k: v for k, v in request.items() if k not in {"target", "surface"}}
        self.textures.submit(**plain)
        with self.assertRaisesRegex(ValueError, "already owned"):
            self.plan()
        self.spec["collection_id"] = "second"
        self.plan()
        request = requests_for(self.spec)[0]["request"]
        self.project.texture_submit(**request)
        with self.assertRaisesRegex(ValueError, "owned submission intent"):
            self.collections.advance("second")

    def test_invalid_specs_paths_lfs_and_budgets_make_no_jobs(self):
        invalid = [{**self.spec, "seed": True}, {**self.spec, "style": ""}, {**self.spec, "extra": 1},
                   {**self.spec, "items": []}, {**self.spec, "items": self.spec["items"]*9},
                   {**self.spec, "collection_id": "Garden"}, {**self.spec, "collection_id": "../escape"}]
        for spec in invalid:
            with self.assertRaises(ValueError):
                self.collections.plan(spec)
        for target in ("../outside.uasset", "Content/missing.uasset"):
            spec = copy.deepcopy(self.spec)
            spec["items"][1]["target"] = target
            with self.assertRaises((ValueError, OSError)):
                self.collections.plan(spec)
        target = self.game / "Content/Wall.uasset"
        original = target.read_bytes()
        target.write_bytes(LFS_HEADER + b"\noid sha256:" + b"a"*64)
        with self.assertRaisesRegex(ValueError, "Git LFS"):
            self.plan()
        target.write_bytes(original)
        for constant in ("MAX_SOURCE_BYTES", "MAX_REQUESTS", "MAX_COLLECTIONS"):
            with patch("cryptonyan_asset_studio.texture_collections." + constant, 0), self.assertRaises(ValueError):
                self.plan()
        self.assertFalse(self.peer.calls)
        self.assertFalse(list(self.textures.requests.iterdir()))

    def test_duplicate_items_and_changed_spec_cannot_reuse_identity(self):
        spec = copy.deepcopy(self.spec)
        spec["items"][1]["id"] = spec["items"][0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.collections.plan(spec)
        self.plan()
        with self.assertRaisesRegex(ValueError, "different specification"):
            self.collections.plan({**self.spec, "seed": 43})
        self.assertFalse(self.peer.calls)

    def test_windows_reserved_names_are_safe_prefixed_identifiers(self):
        self.spec["collection_id"] = "con"
        self.spec["items"][0]["id"] = "con"
        self.spec["items"][1]["id"] = "nul"
        self.plan()
        self.collections.advance("con")
        self.succeed()
        self.collections.collect("con")
        self.collections.advance("con")
        self.assertTrue((self.collections._folder("con") / "item-con.intent.json").is_file())
        self.assertTrue((self.collections._folder("con") / "item-nul.intent.json").is_file())
        self.assertEqual(len(self.posts()), 2)

    def test_wrong_project_descriptor_and_symlink_collection_refused(self):
        self.plan()
        (self.game / "Game.uproject").write_text('{"FileVersion":3,"EngineAssociation":"changed"}')
        with self.assertRaisesRegex(ValueError, "changed descriptor"):
            self.advance()
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.collections.root / "collection-escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Host cannot create symlinks")
        with self.assertRaises(ValueError):
            self.collections.status("escape")
        self.assertFalse(list(outside.iterdir()))

    def test_actual_cli_plan_status_and_forbidden_workspace_without_network(self):
        self.textures.lock.close()
        specification = self.root / "collection.json"
        specification.write_text(json.dumps(self.spec))
        args = [sys.executable, "-m", "cryptonyan_asset_studio.texture_collections", "--project", str(self.game),
                "--catalog", str(self.root / "profiles.json"), "--workspace", str(self.root / "jobs")]
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        for command in (["plan", str(specification)], ["status", "garden"], ["list"]):
            result = subprocess.run(args + command, capture_output=True, text=True, timeout=20, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
        args[-1] = str(self.game / "ForbiddenJobs")
        result = subprocess.run(args + ["list"], capture_output=True, text=True, timeout=20, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.game / "ForbiddenJobs").exists())

    def test_real_stdio_http_collection_and_cli_restart(self):
        peer = self.peer
        peer.auto_success = True
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
                raise
            self.skipTest("Local sandbox forbids sockets; collection MCP/HTTP test is mandatory in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:" + str(http.server_port)
        self.save_catalog()
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}]
        for name, arguments in (("project_collection_plan", {"specification": self.spec}),
                                 ("project_collection_status", {"collection_id": "garden"}),
                                 ("project_collection_advance", {"collection_id": "garden"}),
                                 ("project_collection_collect", {"collection_id": "garden"}),
                                 ("project_collection_advance", {"collection_id": "garden"}),
                                 ("project_collection_collect", {"collection_id": "garden"}),
                                 ("project_collections", {})):
            messages.append({"jsonrpc": "2.0", "id": len(messages)+1, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments}})
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        try:
            result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root / "cli"),
                                     "--asset-root", str(self.game / "Content"), "--game-project", str(self.game),
                                     "--comfy-profiles", str(self.root / "profiles.json"), "serve"],
                                    input="".join(json.dumps(m)+"\n" for m in messages), capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(responses), len(messages))
            for response in responses[1:]:
                self.assertFalse(response["result"]["isError"], response)
            final = json.loads(responses[-2]["result"]["content"][0]["text"])
            self.assertTrue(Path(final["index_file"]).is_file())
            count = len(peer.calls)
            result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio.texture_collections", "--project", str(self.game),
                                     "--catalog", str(self.root / "profiles.json"), "--workspace", str(self.root / "cli/textures"),
                                     "collect", "garden"], capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(peer.calls), count)
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=5)
        self.assertEqual(len(self.posts()), 2)


if __name__ == "__main__":
    unittest.main()
