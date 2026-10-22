# SPDX-License-Identifier: GPL-3.0-or-later
"""Approved image slots, durable preparation, project guards and actual MCP/HTTP."""
import base64
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts/addons_core"))
import test_cryptonyan_comfy_preflight as preflight_fixtures
import test_cryptonyan_texture_collections as collection_fixtures
from cryptonyan_asset_studio.comfy_profiles import TextureService, load_catalog
from cryptonyan_asset_studio.comfyui_adapter import workflow_digest
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.reference_preparations import ReferencePreparations
from cryptonyan_asset_studio.storage import digest, write_json
from test_cryptonyan_materials import png


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.assets = self.root/"assets"; self.assets.mkdir()
        self.work = self.root/"work"; self.work.mkdir()
        self.inputs = self.root/"comfy-input"; self.inputs.mkdir()
        self.source = self.assets/"image.png"; self.source.write_bytes(png())
        self.profile, self.info = preflight_fixtures.fixtures()
        self.workflow = self.profile.pop("template")
        self.workflow["20"] = {"class_type": "LoadImage", "inputs": {"image": "operator.png"}}
        self.workflow["21"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["20", 0], "vae": ["1", 2]}}
        self.workflow["4"]["inputs"]["latent_image"] = ["21", 0]
        self.profile["reference_slots"] = [dict(role="reference", binding=["20", "image"])]
        self.catalog = dict(schema="cryptonyan.comfy-profiles/1", endpoint="http://127.0.0.1:8188",
                            input_root=str(self.inputs), profiles=[self.profile])
        self.info["LoadImage"] = {"input": {"required": {"image": [["cn_"+digest(self.source)+".png"]]}}, "output": ["IMAGE", "MASK"]}
        self.info["VAEEncode"] = {"input": {"required": {"pixels": ["IMAGE"], "vae": ["VAE"]}}, "output": ["LATENT"]}
        self.peer = collection_fixtures.MultiPeer(self.info); self.peer.auto_success = True
        self.refs = {"reference": "asset:image.png"}
        self.save(); self.service = self.open()

    def save(self):
        self.profile["workflow_sha256"] = workflow_digest(self.workflow)
        write_json(self.root/"workflow.json", self.workflow)
        write_json(self.root/"profiles.json", self.catalog)

    def open(self, **kwargs):
        service = TextureService(self.root/"profiles.json", self.work/"textures", transport=self.peer,
                                 handle_root=self.work, asset_root=self.assets, **kwargs)
        self.addCleanup(service.lock.close)
        return service

    def prepare(self, preparation_id="coat"):
        return self.service.reference_prepare("rock", preparation_id, self.refs)

    def submit(self, request_id="one"):
        return self.service.reference_submit("coat", "blue cloth", 42, request_id)

    def posts(self):
        return [c for c in self.peer.calls if c[0] == "POST"]

    def folder(self):
        return self.work/"textures/reference-preparations/coat"

    def project(self):
        game = self.root/"game"; (game/"Content").mkdir(parents=True)
        write_json(game/"Game.uproject", dict(FileVersion=3, EngineAssociation="5.8"))
        target = game/"Content/Body.uasset"; target.write_bytes(b"opaque fixture mesh")
        return GameProject(game, self.service), target

    def test_slot_catalog_and_plain_calls_require_preparation_before_http(self):
        self.assertEqual(self.service.catalog()["profiles"][0]["reference_slots"], self.profile["reference_slots"])
        for call in (lambda: self.service.preflight("rock", "cloth", 1),
                     lambda: self.service.submit("rock", "cloth", 1, "plain")):
            with self.assertRaisesRegex(ValueError, "Prepare declared"): call()
        self.assertEqual(self.peer.calls, []); self.assertEqual(list(self.service.requests.iterdir()), [])

    def test_closed_slots_reject_duplicates_wrong_nodes_overlaps_and_fixed_inputs(self):
        original = copy.deepcopy(self.profile["reference_slots"])
        cases = [None, {}, original*2, [dict(role="normal", binding=["20", "image"])],
                 [dict(role="reference", binding=["2", "text"])], [dict(role="reference", binding=["20", "other"])],
                 [dict(role="reference", binding=["20", "image"], path="arbitrary")], original*4,
                 [dict(role="reference", binding=["20", "image"]), dict(role="uv", binding=["20", "image"])]]
        for slots in cases:
            self.profile["reference_slots"] = slots; self.save()
            with self.subTest(slots=slots), self.assertRaises(ValueError): load_catalog(self.root/"profiles.json")
        self.profile["reference_slots"] = original; self.profile["reference_inputs"] = [dict(ignored=True)]; self.save()
        with self.assertRaises(ValueError): load_catalog(self.root/"profiles.json")
        self.profile.pop("reference_inputs"); self.profile["prompt_inputs"].append(["20", "image"]); self.save()
        with self.assertRaises(ValueError): load_catalog(self.root/"profiles.json")
        self.assertEqual(list(self.inputs.iterdir()), [])

    def test_missing_absolute_input_root_and_symlink_are_rejected(self):
        for root in (None, "relative", str(self.root/"missing")):
            self.catalog["input_root"] = root; self.save()
            with self.subTest(root=root), self.assertRaises(ValueError): load_catalog(self.root/"profiles.json")

    def test_preparation_preserves_graph_models_and_copies_exact_bytes_without_http(self):
        before = self.source.read_bytes(); result = self.prepare()
        self.assertFalse(result["source_freshness_validated"]); self.assertEqual(self.peer.calls, [])
        self.assertEqual(self.source.read_bytes(), before)
        ref = result["references"][0]; self.assertEqual((self.inputs/ref["file"]).read_bytes(), before)
        self.assertEqual((ref["role"], ref["binding"], ref["sha256"]), ("reference", ["20", "image"], digest(self.source)))
        selected, record = ReferencePreparations(self.service).selected("coat")
        expected = copy.deepcopy(self.workflow); expected["20"]["inputs"]["image"] = ref["file"]
        self.assertEqual(selected["template"], expected); self.assertEqual(selected["models"], self.profile["models"])
        self.assertEqual(record["template_sha256"], self.profile["workflow_sha256"])
        self.assertEqual(self.service.profiles["rock"]["template"], self.workflow)

    def test_input_root_spelling_is_normalized_for_derived_profile_comparison(self):
        # Trailing separators and Windows forward-slash paths are valid catalog paths.
        self.service.profiles["rock"]["input_root"] = self.inputs.as_posix()+"/"
        self.prepare(); self.assertEqual(self.submit()["submission"], "accepted")

    def test_all_roles_from_asset_and_work_share_content_hashed_file(self):
        self.service.lock.close()
        for node in ("22", "23"): self.workflow[node] = copy.deepcopy(self.workflow["20"])
        self.profile["reference_slots"] += [dict(role="uv", binding=["22", "image"]), dict(role="mask", binding=["23", "image"])]
        (self.work/"mask.png").write_bytes(self.source.read_bytes()); self.save(); self.service = self.open()
        self.refs.update(uv="asset:image.png", mask="work:mask.png"); result = self.prepare()
        self.assertEqual(len(result["references"]), 3); self.assertEqual(len(list(self.inputs.iterdir())), 1)
        self.assertEqual(self.submit()["submission"], "accepted")
        self.assertEqual(self.posts()[0][2]["prompt"]["23"]["inputs"]["image"], result["references"][0]["file"])

    def test_invalid_handles_roles_and_pngs_fail_before_any_staging(self):
        for refs in ({}, {"mask": "asset:image.png"}, {"reference": "https://invalid/image.png"},
                     {"reference": "asset:../image.png"}, {"reference": "asset:/image.png"},
                     {"reference": "work:C:\\image.png"}, {"reference": []}, {"reference": "asset:missing.png"}):
            with self.subTest(refs=refs), self.assertRaises((ValueError, OSError)):
                self.service.reference_prepare("rock", "invalid", refs)
        self.source.write_bytes(b"not png")
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.folder().exists()); self.assertEqual(list(self.inputs.iterdir()), [])

    def test_source_and_preparation_symlinks_are_refused(self):
        link = self.assets/"link.png"
        try: link.symlink_to(self.source)
        except OSError: self.skipTest("Symlinks unavailable for this Windows account")
        self.refs["reference"] = "asset:link.png"
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.folder().exists())
        self.refs["reference"] = "asset:image.png"; self.prepare()
        target = self.root/"elsewhere"; self.folder().rename(target); self.folder().symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError): self.prepare()

    def test_asset_game_and_receipt_directories_are_protected_from_staging(self):
        project, _ = self.project()
        for root in (self.assets, self.assets/"child", project.root, project.root/"Content", self.service.root,
                     self.service.root/"child", self.root):
            root.mkdir(exist_ok=True); self.service.profiles["rock"]["input_root"] = str(root)
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, "separate"): self.prepare()
        self.assertFalse(self.folder().exists()); self.assertEqual(self.peer.calls, [])

    def test_preparation_id_reuses_snapshot_without_http_even_after_source_removal(self):
        first = self.prepare(); self.source.unlink(); calls = len(self.peer.calls)
        self.assertEqual(self.prepare(), first); self.assertEqual(len(self.peer.calls), calls)
        self.refs["reference"] = "work:other.png"
        with self.assertRaisesRegex(ValueError, "different parameters"): self.prepare()

    def test_incomplete_preparation_and_existing_input_collision_never_auto_retry(self):
        filename = "cn_"+digest(self.source)+".png"; path = self.inputs/filename
        path.write_bytes(png(width=3)); before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "different bytes"): self.prepare()
        self.assertEqual(path.read_bytes(), before); path.unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"): self.prepare()
        self.assertFalse(path.exists()); self.assertEqual(self.peer.calls, [])

    def test_source_changed_during_preparation_leaves_incomplete_id(self):
        from cryptonyan_asset_studio import reference_preparations
        original = reference_preparations.prepare_profile
        def changed(*args):
            result = original(*args); self.source.write_bytes(png(width=3)); return result
        with patch.object(reference_preparations, "prepare_profile", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during"): self.prepare()
        with self.assertRaisesRegex(ValueError, "incomplete"): self.prepare()
        self.assertEqual(self.posts(), [])

    def test_source_staged_input_or_profile_changes_block_new_preflight_and_submit(self):
        self.prepare(); source = self.source.read_bytes(); staged = next(self.inputs.iterdir())
        for path in (self.source, staged):
            path.write_bytes(png(width=3))
            for call in (lambda: self.service.reference_preflight("coat", "cloth", 42), lambda: self.submit()):
                with self.subTest(path=path), self.assertRaises(ValueError): call()
            path.write_bytes(source)
        self.service.profiles["rock"]["models"][0]["sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "approved profile"): self.submit()
        self.assertEqual(self.peer.calls, []); self.assertFalse(self.service._folder("one").exists())

    def test_readonly_preflight_refetches_metadata_and_rechecks_sources_after_get(self):
        self.prepare(); result = self.service.reference_preflight("coat", "cloth", 42)
        self.assertEqual(result["status"], "compatible", result); self.assertTrue(result["source_freshness_validated"])
        self.assertEqual(self.posts(), [])
        def changing_peer(*args, **kwargs):
            result = self.peer(*args, **kwargs); self.source.write_bytes(png(width=3)); return result
        self.service.transport = changing_peer
        with self.assertRaisesRegex(ValueError, "source changed"): self.service.reference_preflight("coat", "cloth", 42)
        self.assertEqual(len(self.peer.calls), 2); self.assertEqual(self.posts(), [])

    def test_replay_and_uncertain_post_need_no_sources_preparation_or_current_profile(self):
        self.prepare(); self.peer.fail_submit = True; first = self.submit(); self.assertTrue(first["manual_inspection_required"])
        self.source.unlink(); shutil.rmtree(self.folder()); self.service.profiles.clear()
        again = self.submit(); self.assertEqual(again["request_id"], first["request_id"]); self.assertEqual(len(self.posts()), 1)
        with self.assertRaises(ValueError): self.service.reference_submit("coat", "different", 42, "one")
        with self.assertRaises(ValueError): self.service.reference_submit("other", "blue cloth", 42, "one")
        with self.assertRaises(ValueError): self.service.submit("rock", "blue cloth", 42, "one")
        self.assertEqual(len(self.posts()), 1)

    def test_collect_and_review_pin_provenance_and_survive_reference_removal(self):
        self.prepare(); first = self.submit(); self.assertEqual(first["reference_preparation"], "coat")
        self.service.collect("one"); self.source.unlink(); shutil.rmtree(self.folder()); shutil.rmtree(self.inputs)
        self.service.profiles.clear(); calls = len(self.peer.calls)
        review = self.service.inspect("one")
        self.assertEqual(review["reference_preparation"]["sources"][0]["handle"], "asset:image.png")
        self.assertEqual(review["reference_preparation"]["template_sha256"], self.profile["workflow_sha256"])
        self.assertFalse(review["reference_source_freshness_validated"])
        self.assertTrue(base64.b64decode(self.service.image("one", "base_color")["data"]).startswith(b"\x89PNG"))
        self.assertTrue(self.service.collect("one")["files"]); self.assertEqual(calls, len(self.peer.calls))
        path = self.service._folder("one")/"request.json"; record = json.loads(path.read_text(encoding="utf-8"))
        record["reference_preparation"]["preparation_id"] = "different"; write_json(path, record)
        with self.assertRaisesRegex(ValueError, "preparation provenance"): self.service.inspect("one")

    def test_prepared_workflow_tamper_rejected_before_network(self):
        self.prepare(); path = self.folder()/"profile/workflow.json"; value = json.loads(path.read_text(encoding="utf-8"))
        value["1"]["inputs"]["ckpt_name"] = "unapproved.safetensors"; write_json(path, value)
        with self.assertRaisesRegex(ValueError, "integrity"): self.submit()
        self.assertEqual(self.peer.calls, [])

    def test_project_bound_request_collect_review_and_target_freshness(self):
        project, target = self.project(); before = target.read_bytes(); self.prepare()
        first = project.texture_reference_submit("bound", "Content/Body.uasset", "Coat", "coat", "blue cloth", 42)
        self.assertFalse(first["applied_to_game"]); project.texture_collect("bound")
        review = project.texture_inspect("bound"); self.assertTrue(review["target_freshness_validated"])
        self.assertEqual(review["reference_preparation"]["preparation_id"], "coat")
        self.assertEqual(target.read_bytes(), before); self.source.unlink(); shutil.rmtree(self.folder())
        self.assertEqual(project.texture_reference_submit("bound", "Content/Body.uasset", "Coat", "coat", "blue cloth", 42), {**first, "collected": True})
        target.write_bytes(b"modified game mesh"); calls = len(self.peer.calls)
        for call in (lambda: project.texture_inspect("bound"), lambda: project.texture_image("bound", "base_color"),
                     lambda: project.texture_reference_submit("bound", "Content/Body.uasset", "Coat", "coat", "blue cloth", 42)):
            with self.assertRaisesRegex(ValueError, "Target changed"): call()
        self.assertEqual(calls, len(self.peer.calls)); self.assertEqual(len(self.posts()), 1)

    def test_project_cannot_claim_unbound_request_or_changed_source(self):
        project, target = self.project(); self.prepare(); self.submit()
        with self.assertRaisesRegex(ValueError, "unbound"): project.texture_reference_submit("one", "Content/Body.uasset", "Coat", "coat", "blue cloth", 42)
        target.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:fixture")
        with self.assertRaisesRegex(ValueError, "LFS"): project.texture_reference_submit("two", "Content/Body.uasset", "Coat", "coat", "blue cloth", 42)
        self.assertEqual(len(self.posts()), 1)

    def test_capacity_budget_and_missing_source_roots_do_not_stage(self):
        with patch("cryptonyan_asset_studio.reference_preparations.MAX_PREPARATIONS", 0):
            with self.assertRaisesRegex(ValueError, "capacity"): self.prepare()
        self.service.asset_root = None
        with self.assertRaisesRegex(ValueError, "not configured"): self.prepare()
        self.assertFalse(self.folder().exists()); self.assertEqual(list(self.inputs.iterdir()), [])

    def test_oversized_source_and_aggregate_batch_are_refused_before_writes(self):
        with self.source.open("ab") as stream: stream.truncate(32*1024*1024+1)
        with self.assertRaisesRegex(ValueError, "byte budget"): self.prepare()
        self.source.write_bytes(png()); self.service.lock.close()
        for role, node in (("uv", "22"), ("mask", "23")):
            self.workflow[node] = copy.deepcopy(self.workflow["20"])
            self.profile["reference_slots"].append(dict(role=role, binding=[node, "image"]))
            self.refs[role] = "asset:image.png"
        self.save(); self.service = self.open()
        # Exercise the aggregate bound without constructing three 22 MiB PNGs.
        with patch("cryptonyan_asset_studio.reference_preparations.read_png",
                   return_value=(b"x"*(22*1024*1024), dict(width=4096, height=4096))):
            with self.assertRaisesRegex(ValueError, "64 MiB"): self.prepare()
        self.assertFalse(self.folder().exists()); self.assertEqual(list(self.inputs.iterdir()), [])

    def test_rehashed_derived_catalog_cannot_change_unapproved_graph_fields(self):
        self.prepare(); folder = self.folder(); path = folder/"profile/workflow.json"
        workflow = json.loads(path.read_text(encoding="utf-8")); workflow["4"]["inputs"]["steps"] = 999
        write_json(path, workflow)
        catalog_path = folder/"profile/profiles.json"; catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["profiles"][0]["workflow_sha256"] = workflow_digest(workflow); write_json(catalog_path, catalog)
        receipt = json.loads((folder/"prepared.json").read_text(encoding="utf-8"))
        receipt["files"] = {p: digest(folder/p) for p in receipt["files"]}; write_json(folder/"prepared.json", receipt)
        with self.assertRaisesRegex(ValueError, "graph or provenance"): self.submit()
        self.assertEqual(self.peer.calls, [])

    def test_reconnect_changed_profile_blocks_new_work_but_not_saved_request_replay(self):
        self.prepare(); first = self.submit(); self.service.lock.close()
        self.profile["models"][0]["sha256"] = "b"*64; self.save(); self.service = self.open()
        self.assertEqual(self.submit(), first)
        with self.assertRaisesRegex(ValueError, "approved profile"): self.submit("new")
        self.assertEqual(len(self.posts()), 1)

    def test_collections_require_per_item_preparation_before_writing_a_plan(self):
        project, _ = self.project()
        spec = dict(schema="cryptonyan.texture-collection/1", collection_id="skins", profile="rock", style="cloth", seed=7,
                    items=[dict(id="blue", target="Content/Body.uasset", surface="Coat", description="blue stripes")])
        with self.assertRaisesRegex(ValueError, "needs preparation_id"): project.collection_plan(spec)
        self.assertFalse((self.service.root/"collections").exists()); self.assertEqual(self.peer.calls, [])

    def test_mcp_dispatch_closed_arguments_native_image_and_configured_tool_counts(self):
        project, _ = self.project(); server = MCPServer(None, textures=self.service, project=project)
        server.handle(dict(jsonrpc="2.0", id=0, method="initialize"))
        def call(name, arguments):
            result = server.handle(dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name=name, arguments=arguments)))
            self.assertFalse(result["result"]["isError"], result)
            return result["result"]["content"][0]
        call("texture_reference_prepare", dict(profile="rock", preparation_id="coat", references=self.refs))
        call("texture_reference_preflight", dict(preparation_id="coat", prompt="blue cloth", seed=42))
        call("project_texture_reference_submit", dict(request_id="bound", target="Content/Body.uasset", surface="Coat", preparation_id="coat", prompt="blue cloth", seed=42))
        call("project_texture_collect", dict(request_id="bound")); call("project_texture_inspect", dict(request_id="bound"))
        self.assertEqual(call("project_texture_image", dict(request_id="bound", channel="base_color"))["type"], "image")
        result = server.handle(dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name="texture_reference_prepare", arguments=dict(profile="rock", preparation_id="coat", references=self.refs, binding=["20", "image"]))))
        self.assertEqual(result["error"]["code"], -32602)
        self.assertEqual(len(tool_list()), 8); self.assertEqual(len(tool_list(textures=True)), 20)
        self.assertEqual(len(tool_list(textures=True, project=True)), 33); self.assertEqual(len(tool_list(True, True, True, True)), 52)

    def test_actual_stdio_http_prepare_preflight_project_submit_collect_and_image(self):
        project, _ = self.project(); peer = self.peer
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self): self.respond()
            def do_POST(self): self.respond(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            def respond(self, payload=None):
                data = peer(self.command, self.path, payload)
                self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *args): pass
        try: http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            if os.environ.get("CI"): raise
            self.skipTest("Local sockets forbidden; actual reference MCP/HTTP acceptance is mandatory in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:"+str(http.server_port); self.save()
        messages = [dict(jsonrpc="2.0", id=0, method="initialize")]
        for name, arguments in (("texture_reference_prepare", dict(profile="rock", preparation_id="coat", references=self.refs)),
                                ("texture_reference_preflight", dict(preparation_id="coat", prompt="blue cloth", seed=42)),
                                ("project_texture_reference_submit", dict(request_id="bound", target="Content/Body.uasset", surface="Coat", preparation_id="coat", prompt="blue cloth", seed=42)),
                                ("project_texture_collect", dict(request_id="bound")), ("project_texture_inspect", dict(request_id="bound")),
                                ("project_texture_image", dict(request_id="bound", channel="base_color"))):
            messages.append(dict(jsonrpc="2.0", id=len(messages), method="tools/call", params=dict(name=name, arguments=arguments)))
        try:
            result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root/"cli"),
                "--asset-root", str(self.assets), "--game-project", str(project.root), "--comfy-profiles", str(self.root/"profiles.json"), "serve"],
                input="".join(json.dumps(m)+"\n" for m in messages), capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": str(ROOT/"scripts/addons_core")}, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]; self.assertEqual(len(responses), len(messages))
            for response in responses[1:]: self.assertFalse(response["result"]["isError"], response)
            review = json.loads(responses[-2]["result"]["content"][0]["text"])
            self.assertTrue(review["target_freshness_validated"]); self.assertEqual(review["reference_preparation"]["preparation_id"], "coat")
            self.assertEqual(responses[-1]["result"]["content"][0]["type"], "image")
            self.assertEqual(len(self.posts()), 1)
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=5)


if __name__ == "__main__": unittest.main()
