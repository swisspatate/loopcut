# SPDX-License-Identifier: GPL-3.0-or-later
"""Collections with independent, pinned ComfyUI image selections per game asset."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import test_cryptonyan_reference_preparations as fixtures
from cryptonyan_asset_studio.comfy_profiles import load_catalog
from cryptonyan_asset_studio.comfyui_adapter import workflow_digest
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.mcp_stdio import COLLECTION_SCHEMA, MCPServer, tool_list
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.texture_collections import TextureCollections, requests_for, validate_spec
from test_cryptonyan_materials import png

ROOT = Path(__file__).resolve().parents[2]


class ReferenceCollectionTests(unittest.TestCase):
    save = fixtures.PreparationTests.save
    open = fixtures.PreparationTests.open

    def setUp(self):
        fixtures.PreparationTests.setUp(self)
        self.second_source = self.assets/"wall.png"; self.second_source.write_bytes(png(rgb=(20, 40, 80)))
        for identity, source in (("body-ref", self.source), ("wall-ref", self.second_source)):
            self.service.reference_prepare("rock", identity, {"reference": "asset:"+source.name})
        self.info["LoadImage"]["input"]["required"]["image"][0] = [p.name for p in self.inputs.iterdir()]
        self.game = self.root/"game"; (self.game/"Content").mkdir(parents=True)
        write_json(self.game/"Game.uproject", dict(FileVersion=3, EngineAssociation="5.8"))
        for name in ("Body", "Wall"): (self.game/"Content"/(name+".uasset")).write_bytes((name+" opaque package").encode())
        self.project = GameProject(self.game, self.service); self.collections = TextureCollections(self.project)
        self.spec = dict(schema="cryptonyan.texture-collection/1", collection_id="biome", profile="rock",
                         style="Stylized jade biome", seed=42, items=[
            dict(id="body", target="Content/Body.uasset", surface="Coat", description="silk cloth", preparation_id="body-ref"),
            dict(id="wall", target="Content/Wall.uasset", surface="Stone", description="mossy bricks", preparation_id="wall-ref")])

    def plan(self): return self.collections.plan(self.spec)
    def advance(self): return self.collections.advance("biome")
    def collect(self): return self.collections.collect("biome")
    def posts(self): return [c for c in self.peer.calls if c[0] == "POST"]
    def prep_folder(self, identity="body-ref"): return self.service.root/"reference-preparations"/identity

    def complete(self):
        self.plan(); self.advance(); self.collect(); self.advance(); return self.collect()

    def test_plan_is_offline_immutable_pins_both_preparations_and_preserves_game(self):
        before = {p.relative_to(self.game).as_posix(): digest(p) for p in self.game.rglob("*") if p.is_file()}
        result = self.plan(); plan = result["plan"]
        self.assertEqual(set(plan["reference_preparations"]), {"body-ref", "wall-ref"})
        self.assertEqual(plan["items"][0]["request"]["reference_preparation"], "body-ref")
        self.assertNotEqual(plan["reference_preparations"]["body-ref"]["references"], plan["reference_preparations"]["wall-ref"]["references"])
        self.assertFalse(result["submission_performed"]); self.assertEqual(self.peer.calls, [])
        self.assertEqual(self.plan(), result)
        self.assertEqual(before, {p.relative_to(self.game).as_posix(): digest(p) for p in self.game.rglob("*") if p.is_file()})
        self.assertEqual(len(list(self.inputs.iterdir())), 2)

    def test_sequential_requests_use_each_actual_reference_and_index_provenance(self):
        self.plan(); first = self.advance(); self.assertEqual(first["action"], "submitted")
        self.assertEqual(first["item"]["reference_preparation"], "body-ref")
        self.assertEqual(self.advance()["action"], "collect"); self.assertEqual(len(self.posts()), 1)
        self.assertIsNone(self.collect()["index_file"]); self.advance(); result = self.collect()
        index = json.loads(Path(result["index_file"]).read_text(encoding="utf-8"))
        self.assertEqual(len(self.posts()), 2)
        self.assertEqual([e["reference_preparation"] for e in index["items"]], ["body-ref", "wall-ref"])
        plan = self.plan()["plan"]
        for entry, post in zip(index["items"], self.posts()):
            pin = plan["reference_preparations"][entry["reference_preparation"]]
            self.assertEqual(post[2]["prompt"]["20"]["inputs"]["image"], pin["references"][0]["file"])
            self.assertEqual(entry["reference_preparation_sha256"], workflow_digest(pin))
            review = self.project.texture_inspect(entry["request_id"])
            self.assertEqual(review["reference_preparation"]["preparation_id"], entry["reference_preparation"])
            self.assertTrue(review["target_freshness_validated"])
        self.assertFalse(index["reference_source_freshness_validated"]); self.assertFalse(index["applied_to_game"])

    def test_shared_preparation_is_pinned_once_and_request_seeds_remain_stable(self):
        self.spec["items"][1]["preparation_id"] = "body-ref"; plan = self.plan()["plan"]
        self.assertEqual(list(plan["reference_preparations"]), ["body-ref"])
        reordered = {**self.spec, "items": list(reversed(self.spec["items"]))}
        self.assertEqual(requests_for(reordered), list(reversed(requests_for(self.spec))))
        self.complete(); self.assertEqual(len(self.posts()), 2)
        self.assertEqual(self.posts()[0][2]["prompt"]["20"], self.posts()[1][2]["prompt"]["20"])

    def test_missing_invalid_and_unknown_preparation_ids_fail_without_plan_or_http(self):
        for value in (None, True, "", "../escape", "x"*65, "missing"):
            spec = copy.deepcopy(self.spec); spec["items"][0]["preparation_id"] = value
            with self.subTest(value=value), self.assertRaises((ValueError, OSError)): self.collections.plan(spec)
        spec = copy.deepcopy(self.spec); spec["items"][1].pop("preparation_id")
        with self.assertRaisesRegex(ValueError, "needs preparation_id"): self.collections.plan(spec)
        spec = copy.deepcopy(self.spec); spec["items"][0]["references"] = {"reference": "asset:image.png"}
        with self.assertRaises(ValueError): validate_spec(spec)
        self.assertFalse(self.collections.root.exists()); self.assertEqual(self.peer.calls, [])

    def test_ordinary_and_fixed_profiles_forbid_preparation_ids(self):
        profile = self.service.profiles["rock"]; profile.pop("reference_slots")
        with self.assertRaisesRegex(ValueError, "other profiles forbid"): self.plan()
        _, profiles = load_catalog(self.prep_folder()/"profile/profiles.json")
        self.service.profiles["rock"] = profiles["rock"]
        with self.assertRaisesRegex(ValueError, "other profiles forbid"): self.plan()
        self.assertFalse(self.collections.root.exists()); self.assertEqual(self.peer.calls, [])

    def test_preparation_for_another_approved_profile_is_refused(self):
        original = self.service.profiles["rock"]
        self.service.profiles["other"] = {**copy.deepcopy(original), "id": "other"}
        self.service.reference_prepare("other", "foreign-ref", {"reference": "asset:image.png"})
        self.spec["items"][0]["preparation_id"] = "foreign-ref"
        with self.assertRaisesRegex(ValueError, "another profile"): self.plan()
        self.assertFalse(self.collections.root.exists()); self.assertEqual(self.peer.calls, [])

    def test_changed_source_or_staged_input_blocks_plan_and_new_submission(self):
        original = self.source.read_bytes(); self.source.write_bytes(png(width=3))
        with self.assertRaisesRegex(ValueError, "source changed"): self.plan()
        self.assertFalse(self.collections.root.exists()); self.source.write_bytes(original)
        self.plan(); self.source.write_bytes(png(width=3))
        with self.assertRaisesRegex(ValueError, "source changed"): self.advance()
        self.source.write_bytes(original)
        staged = self.inputs/("cn_"+digest(self.source)+".png"); staged.write_bytes(png(width=3))
        with self.assertRaises(ValueError): self.advance()
        self.assertEqual(self.peer.calls, []); self.assertEqual(list(self.service.requests.iterdir()), [])

    def test_drift_during_metadata_get_is_rejected_before_intent_or_post(self):
        self.plan(); original = self.service.transport
        def change(*args, **kwargs):
            result = original(*args, **kwargs); self.source.write_bytes(png(width=3)); return result
        self.service.transport = change
        with self.assertRaisesRegex(ValueError, "source changed"): self.advance()
        self.assertEqual(self.posts(), []); self.assertEqual(list(self.project.bindings.iterdir()), [])
        self.assertEqual(list(self.collections._folder("biome").glob("*.intent.json")), [])

    def test_changed_preparation_pin_during_preflight_is_rejected_before_post(self):
        self.plan(); method = self.service.reference_preflight
        def change(*args):
            result = method(*args); path = self.prep_folder()/"prepared.json"
            record = json.loads(path.read_text(encoding="utf-8")); record["sources"][0]["width"] = 999
            write_json(path, record); return result
        with patch.object(self.service, "reference_preflight", side_effect=change), self.assertRaises(ValueError): self.advance()
        self.assertEqual(self.posts(), [])

    def test_changed_preparation_after_project_handoff_is_rejected_by_final_submit_guard(self):
        self.plan(); submit = self.project.texture_submit
        def change(**kwargs):
            pin = kwargs["expected_reference"]
            # A different, still-valid selection must not replace the selection pinned by this lot.
            replacement = self.service.root/"reference-preparations/replacement"
            self.service.reference_prepare("rock", "replacement", {"reference": "asset:wall.png"})
            replacement_request = json.loads((replacement/"request.json").read_text(encoding="utf-8"))
            replacement_record = json.loads((replacement/"prepared.json").read_text(encoding="utf-8"))
            replacement_request["request"]["preparation_id"] = pin["preparation_id"]
            replacement_record["preparation_id"] = pin["preparation_id"]
            replacement_record["request_sha256"] = workflow_digest(replacement_request["request"])
            shutil.rmtree(self.prep_folder()); shutil.copytree(replacement, self.prep_folder())
            write_json(self.prep_folder()/"request.json", replacement_request)
            write_json(self.prep_folder()/"prepared.json", replacement_record)
            return submit(**kwargs)
        with patch.object(self.project, "texture_submit", side_effect=change), self.assertRaisesRegex(ValueError, "changed before submission"): self.advance()
        self.assertEqual(self.posts(), []); self.assertEqual(list(self.service.requests.iterdir()), [])

    def test_changed_future_reference_does_not_prevent_recovering_prior_candidate(self):
        self.plan(); self.advance(); self.second_source.write_bytes(png(width=3))
        self.assertIsNone(self.collect()["index_file"])
        with self.assertRaisesRegex(ValueError, "source changed"): self.advance()
        self.assertEqual(len(self.posts()), 1)

    def test_profile_change_blocks_new_requests_but_not_submitted_collection(self):
        self.plan(); self.advance(); self.service.profiles["rock"]["models"] = []
        self.collect()
        with self.assertRaisesRegex(ValueError, "profile or endpoint changed"): self.advance()
        self.assertEqual(len(self.posts()), 1)

    def test_lost_post_response_reconnect_and_missing_references_never_resubmit(self):
        self.plan(); self.peer.fail_submit = True; first = self.advance()
        self.assertEqual(first["result"]["submission"], "uncertain")
        self.service.lock.close(); self.service = self.open(); self.project = GameProject(self.game, self.service)
        self.collections = TextureCollections(self.project); self.source.unlink(); shutil.rmtree(self.prep_folder())
        self.assertEqual(self.advance()["action"], "collect"); self.collect()
        self.assertEqual(len(self.posts()), 1)

    def test_fully_collected_index_and_review_survive_all_original_references_and_profiles_removal(self):
        path = self.complete()["index_file"]; calls = len(self.peer.calls)
        shutil.rmtree(self.service.root/"reference-preparations"); shutil.rmtree(self.inputs)
        self.source.unlink(); self.second_source.unlink(); self.service.lock.close()
        self.catalog["profiles"] = []; self.save(); self.service = self.open()
        self.project = GameProject(self.game, self.service); self.collections = TextureCollections(self.project)
        self.assertEqual(self.plan()["plan"]["specification"], self.spec)
        self.assertEqual(self.collect()["index_file"], path); self.assertEqual(self.advance()["action"], "complete")
        for item in self.collections.status("biome")["items"]:
            self.assertEqual(item["state"], "collected"); self.assertTrue(self.project.texture_inspect(item["request_id"])["collection_verified"])
        self.assertEqual(len(self.peer.calls), calls); self.assertEqual(len(self.posts()), 2)

    def test_plan_recovery_does_not_claim_freshness_or_use_missing_preparations(self):
        result = self.plan(); shutil.rmtree(self.prep_folder()); self.source.unlink()
        self.assertEqual(self.plan(), result); self.assertEqual(self.collections.status("biome")["items"][0]["state"], "planned")
        with self.assertRaises(ValueError): self.advance()
        self.assertEqual(self.peer.calls, [])

    def test_partial_intent_and_binding_resumes_only_same_pinned_request(self):
        self.plan()
        with patch.object(self.service, "submit", side_effect=RuntimeError("stop after binding")):
            with self.assertRaises(RuntimeError): self.advance()
        self.assertEqual(self.collections.status("biome")["items"][0]["state"], "prepared")
        self.advance(); self.advance(); self.assertEqual(len(self.posts()), 1)

    def test_tampered_texture_provenance_or_index_mapping_is_refused_without_overwrite(self):
        result = self.complete(); index = Path(result["index_file"])
        record = json.loads(index.read_text(encoding="utf-8")); record["items"][0]["reference_preparation"] = "wall-ref"
        write_json(index, record)
        with self.assertRaisesRegex(ValueError, "index integrity"): self.collect()
        self.assertEqual(json.loads(index.read_text(encoding="utf-8")), record)
        first = requests_for(self.spec)[0]["request"]["request_id"]
        path = self.service._folder(first)/"request.json"; texture = json.loads(path.read_text(encoding="utf-8"))
        texture["reference_preparation"]["sources"][0]["handle"] = "asset:wall.png"; write_json(path, texture)
        with self.assertRaisesRegex(ValueError, "texture receipt mismatch"): self.collections.status("biome")
        self.assertEqual(len(self.posts()), 2)

    def test_rehashed_plan_reference_mapping_must_still_match_derived_request_ids(self):
        self.plan(); path = self.collections._folder("biome")/"plan.json"; record = json.loads(path.read_text(encoding="utf-8"))
        record["plan"]["reference_preparations"].pop("body-ref"); record["sha256"] = workflow_digest(record["plan"])
        write_json(path, record)
        with self.assertRaisesRegex(ValueError, "mapping changed"): self.advance()
        self.assertEqual(self.peer.calls, [])

    def test_missing_preparation_root_configuration_is_reported_before_sending(self):
        self.plan(); self.service.asset_root = None
        with self.assertRaisesRegex(ValueError, "not configured"): self.advance()
        self.assertEqual(self.peer.calls, [])

    def test_mcp_schema_exposes_optional_preparation_id_and_reuses_existing_tools(self):
        item_schema = COLLECTION_SCHEMA["properties"]["items"]["items"]
        self.assertIn("preparation_id", item_schema["properties"]); self.assertNotIn("preparation_id", item_schema["required"])
        self.assertEqual(len(tool_list(True, True, True, True)), 52)
        server = MCPServer(None, textures=self.service, project=self.project)
        server.handle(dict(jsonrpc="2.0", id=0, method="initialize"))
        for name, arguments in (("project_collection_plan", dict(specification=self.spec)),
                                ("project_collection_advance", dict(collection_id="biome")),
                                ("project_collection_collect", dict(collection_id="biome"))):
            response = server.handle(dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name=name, arguments=arguments)))
            self.assertFalse(response["result"]["isError"], response)

    def test_cli_recovery_and_reference_roots_match_mcp_workspace(self):
        self.service.lock.close(); spec = self.root/"collection.json"; write_json(spec, self.spec)
        args = [sys.executable, "-m", "cryptonyan_asset_studio.texture_collections", "--project", str(self.game),
                "--catalog", str(self.root/"profiles.json"), "--workspace", str(self.work/"textures")]
        env = {**os.environ, "PYTHONPATH": str(ROOT/"scripts/addons_core")}
        missing = subprocess.run(args+["plan", str(spec)], capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(missing.returncode, 2); self.assertFalse(self.collections.root.exists())
        args += ["--studio-workspace", str(self.work), "--asset-root", str(self.assets)]
        planned = subprocess.run(args+["plan", str(spec)], capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertIn("body-ref", json.loads(planned.stdout)["plan"]["reference_preparations"])
        result = subprocess.run(args+["status", "biome"], capture_output=True, text=True,
            env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["items"][0]["reference_preparation"], "body-ref")
        self.assertEqual(self.peer.calls, [])

    def test_reference_preflight_blocked_review_or_unavailable_never_creates_intent(self):
        self.plan()
        for status in ("blocked", "needs_review", "unavailable"):
            with patch.object(self.service, "reference_preflight", return_value={"status": status}):
                self.assertEqual(self.advance()["action"], "preflight_blocked")
        self.assertEqual(self.posts(), []); self.assertEqual(list(self.project.bindings.iterdir()), [])
        self.assertEqual(self.collections.status("biome")["items"][0]["state"], "planned")

    def test_target_changed_during_reference_preflight_prevents_submission(self):
        self.plan(); method = self.service.reference_preflight
        def change(*args):
            result = method(*args); (self.game/"Content/Wall.uasset").write_bytes(b"edited game asset"); return result
        with patch.object(self.service, "reference_preflight", side_effect=change), self.assertRaisesRegex(ValueError, "source changed"): self.advance()
        self.assertEqual(self.posts(), []); self.assertEqual(list(self.project.bindings.iterdir()), [])

    def test_actual_stdio_http_prepares_two_references_then_generates_collects_and_displays_collection(self):
        peer = self.peer
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
            self.skipTest("Sockets forbidden locally; real reference collection MCP/HTTP is mandatory in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:"+str(http.server_port); self.save()
        messages = [dict(jsonrpc="2.0", id=0, method="initialize")]
        calls = [("texture_reference_prepare", dict(profile="rock", preparation_id=identity, references={"reference": "asset:"+source.name}))
                 for identity, source in (("body-ref", self.source), ("wall-ref", self.second_source))]
        calls.append(("project_collection_plan", dict(specification=self.spec)))
        for item in requests_for(self.spec):
            calls += [("project_collection_advance", dict(collection_id="biome")), ("project_collection_collect", dict(collection_id="biome")),
                      ("project_texture_inspect", dict(request_id=item["request"]["request_id"])),
                      ("project_texture_image", dict(request_id=item["request"]["request_id"], channel="base_color"))]
        for name, arguments in calls:
            messages.append(dict(jsonrpc="2.0", id=len(messages), method="tools/call", params=dict(name=name, arguments=arguments)))
        try:
            result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root/"cli"),
                "--asset-root", str(self.assets), "--game-project", str(self.game), "--comfy-profiles", str(self.root/"profiles.json"), "serve"],
                input="".join(json.dumps(m)+"\n" for m in messages), capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": str(ROOT/"scripts/addons_core")}, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]; self.assertEqual(len(responses), len(messages))
            for response in responses[1:]: self.assertFalse(response["result"]["isError"], response)
            image_responses = [r for r in responses[1:] if r["result"]["content"][0]["type"] == "image"]
            self.assertEqual(len(image_responses), 2); self.assertEqual(len(self.posts()), 2)
            index = self.root/"cli/textures/collections/collection-biome/index.json"
            self.assertEqual([x["reference_preparation"] for x in json.loads(index.read_text(encoding="utf-8"))["items"]], ["body-ref", "wall-ref"])
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=5)


if __name__ == "__main__": unittest.main()
