# SPDX-License-Identifier: GPL-3.0-or-later
"""Existing project -> MCP -> scripted Comfy HTTP -> bound material, without game writes."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.comfy_profiles import TextureService
from cryptonyan_asset_studio.comfyui_adapter import workflow_digest
from cryptonyan_asset_studio.game_project import GameProject, LFS_HEADER
from cryptonyan_asset_studio.materials import load_material
from cryptonyan_asset_studio.mcp_stdio import serve, tool_list
from cryptonyan_asset_studio.storage import digest
from test_cryptonyan_comfyui import Peer


class ProjectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "Game.uproject").write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
        self.target = "Content/Props/Lantern.uasset"
        self.write(self.target, b"opaque test package; not a real Unreal asset")
        self.write("SourceAssets/Lantern.blend", b"opaque fixture")
        self.write("Content/Maps/Garden.umap", b"map fixture")
        self.write("Content/Props/Missing.uasset", LFS_HEADER + b"\noid sha256:" + b"a" * 64 + b"\nsize 999\n")
        self.write("Saved/secret.png", b"excluded")
        self.write("Pipeline/comfy_profiles.json", json.dumps({"profiles": {"native-3d": {
            "workflow": "native", "purpose": "Shape generation", "secret": "never exposed"}}}).encode())
        workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}},
                    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "template"}},
                    "9": {"class_type": "SaveImage", "inputs": {}}}
        (self.root / "workflow.json").write_text(json.dumps(workflow))
        self.catalog = self.root / "profiles.json"
        self.catalog.write_text(json.dumps({"schema": "cryptonyan.comfy-profiles/1", "endpoint": "http://127.0.0.1:8188",
            "profiles": [{"id": "paper", "description": "Operator reviewed base color", "workflow": "workflow.json",
                          "workflow_sha256": workflow_digest(workflow), "prompt_inputs": [["6", "text"]],
                          "seed_inputs": [["3", "seed"]], "models": [], "outputs": {"base_color": ["9", 0]}}]}))
        self.peer = Peer()
        self.open()
        self.request = dict(request_id="lantern-01", target=self.target, surface="Lantern / Paper slot",
                            profile="paper", prompt="warm red lantern paper", seed=42)

    def write(self, name, data):
        p = self.game / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def open(self):
        self.textures = TextureService(self.catalog, self.root / "jobs", transport=self.peer)
        self.addCleanup(self.textures.lock.close)
        self.project = GameProject(self.game, self.textures)

    def snapshot(self):
        return {p.relative_to(self.game).as_posix(): digest(p) for p in self.game.rglob("*") if p.is_file()}

    def submit(self, **changes):
        return self.project.texture_submit(**{**self.request, **changes})

    def test_inventory_pagination_lfs_scope_and_unknown_semantics(self):
        first = self.project.inventory("", 0, 2)
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["next_offset"], 2)
        self.assertFalse(first["editor_inspected"])
        second = self.project.inventory("", 2, 2)
        self.assertIsNone(second["next_offset"])
        entries = first["assets"] + second["assets"]
        missing = next(x for x in entries if x["path"].endswith("Missing.uasset"))
        self.assertTrue(missing["git_lfs_pointer"])
        self.assertEqual(missing["unreal_package"], "/Game/Props/Missing")
        self.assertIsNone(missing["asset_class"])
        self.assertEqual(self.project.inventory("LANTERN")["matched"], 2)
        self.assertEqual(self.project.inventory("nothing")["assets"], [])

    def test_native_profiles_are_not_executable_or_leaked(self):
        profiles = self.project.profiles()
        self.assertEqual(profiles["texture_profiles"][0]["id"], "paper")
        self.assertFalse(profiles["native_project_profiles"][0]["executable_by_texture_bridge"])
        self.assertNotIn("secret", json.dumps(profiles))
        with self.assertRaisesRegex(ValueError, "executable texture"):
            self.submit(profile="native-3d")
        self.assertEqual(self.peer.calls, [])

    def test_mcp_submit_collect_preserves_project_and_material_provenance(self):
        before = self.snapshot()
        self.peer.state = "succeeded"
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "project_texture_submit", "arguments": self.request}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                        "name": "project_texture_collect", "arguments": {"request_id": "lantern-01"}}}]
        out = io.StringIO()
        serve(None, io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"), out, self.textures, self.project)
        responses = [json.loads(x) for x in out.getvalue().splitlines()]
        for response in responses[1:]:
            self.assertFalse(response["result"]["isError"], response)
        candidate = json.loads(responses[-1]["result"]["content"][0]["text"])
        self.assertEqual(candidate["target"]["sha256"], before[self.target])
        self.assertFalse(candidate["applied_to_game"])
        self.assertFalse(candidate["surface_verified"])
        self.assertTrue(Path(candidate["candidate_manifest"]).is_file())
        self.assertEqual(set(load_material(candidate["texture"]["material_manifest"])["channels"]), {"base_color"})
        receipt = json.loads(Path(candidate["texture"]["generation_receipt"]).read_text())
        self.assertEqual(receipt["seed"], 42)
        self.assertEqual(receipt["workflow"]["6"]["inputs"]["text"], self.request["prompt"])
        self.assertEqual(self.snapshot(), before)
        calls = len(self.peer.calls)
        self.assertEqual(self.project.texture_collect("lantern-01"), candidate)
        self.assertEqual(len(self.peer.calls), calls)

    def test_uncertain_submit_restart_and_changed_profile_never_enqueue_twice(self):
        self.peer.fail_submit = True
        self.assertEqual(self.submit()["submission"], "uncertain")
        self.textures.lock.close()
        catalog = json.loads(self.catalog.read_text())
        catalog["profiles"] = []
        self.catalog.write_text(json.dumps(catalog))
        self.open()
        self.assertEqual(self.submit()["submission"], "uncertain")
        self.assertEqual(len(self.peer.calls), 1)
        with self.assertRaisesRegex(ValueError, "different parameters"):
            self.submit(surface="Different slot")

    def test_bound_receipt_before_texture_submission_can_resume_safely(self):
        with patch.object(self.textures, "submit", side_effect=RuntimeError("simulated process interruption")):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assertFalse(self.peer.calls)
        self.assertTrue((self.project.bindings / "lantern-01.json").exists())
        self.submit()
        self.submit()
        self.assertEqual(len(self.peer.calls), 1)

    def test_changed_target_refused_before_collection_network_access(self):
        self.submit()
        self.write(self.target, b"changed asset")
        with self.assertRaisesRegex(ValueError, "Target changed"):
            self.project.texture_collect("lantern-01")
        with self.assertRaisesRegex(ValueError, "Target changed"):
            self.submit()
        self.assertEqual(len(self.peer.calls), 1)

    def test_source_changed_during_collect_does_not_publish_candidate(self):
        self.submit()
        self.peer.state = "succeeded"
        collect = self.textures.collect
        def change(request_id):
            result = collect(request_id)
            self.write(self.target, b"edited during collection")
            return result
        with patch.object(self.textures, "collect", side_effect=change):
            with self.assertRaisesRegex(ValueError, "Target changed"):
                self.project.texture_collect("lantern-01")
        self.assertFalse((self.project.bindings / "lantern-01.candidate.json").exists())

    def test_descriptor_drift_and_other_checkout_refused(self):
        self.submit()
        self.write("Game.uproject", b'{"FileVersion":3,"EngineAssociation":"changed"}')
        with self.assertRaisesRegex(ValueError, "different project"):
            self.project.texture_collect("lantern-01")
        self.assertEqual(len(self.peer.calls), 1)

    def test_unbound_request_cannot_be_claimed_by_asset(self):
        self.textures.submit(**{k: v for k, v in self.request.items() if k not in {"target", "surface"}})
        with self.assertRaisesRegex(ValueError, "unbound texture"):
            self.submit()
        self.assertFalse((self.project.bindings / "lantern-01.json").exists())

    def test_lfs_maps_paths_invalid_parameters_and_size_refused_before_post(self):
        for changes in ({"target": "Content/Props/Missing.uasset"}, {"target": "Content/Maps/Garden.umap"},
                        {"target": "../outside.blend"}, {"target": "C:\\bad.blend"}, {"target": "Saved/secret.png"},
                        {"surface": ""}, {"seed": True}, {"seed": -1}, {"prompt": ""}, {"request_id": "../bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.submit(**changes)
        with patch("cryptonyan_asset_studio.game_project.MAX_TARGET_BYTES", 1):
            with self.assertRaises(ValueError):
                self.submit()
        self.assertFalse(self.peer.calls)
        self.assertEqual(list(self.project.bindings.iterdir()), [])

    def test_symlinks_cannot_escape_inventory_or_target(self):
        outside = self.root / "private.blend"
        outside.write_bytes(b"private")
        link = self.game / "SourceAssets/link.blend"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Host cannot create symlinks")
        self.assertEqual(self.project.inventory()["total"], 4)
        with self.assertRaises(ValueError):
            self.submit(target="SourceAssets/link.blend")

    def test_inventory_budget_and_pagination_validation(self):
        with patch("cryptonyan_asset_studio.game_project.MAX_ENTRIES", 2):
            with self.assertRaisesRegex(ValueError, "scan budget"):
                self.project.inventory()
        for args in (("", True, 1), ("", 0, 201), ("", -1, 1), (None, 0, 1)):
            with self.assertRaises(ValueError):
                self.project.inventory(*args)

    def test_project_requires_one_descriptor_and_separate_workspace(self):
        with self.assertRaises(ValueError):
            GameProject(self.root)
        self.write("Second.uproject", b'{"FileVersion":3}')
        with self.assertRaises(ValueError):
            GameProject(self.game)
        (self.game / "Second.uproject").unlink()
        # Windows temp paths can use 8.3 names while project.resolve() expands them.
        # Both forms, and a lexical parent component, must be canonicalized first.
        for workspace in (self.game / "Jobs", self.game / "unused" / ".." / "Jobs", self.root):
            with self.subTest(workspace=str(workspace)), patch.object(self.textures, "root", workspace):
                with self.assertRaisesRegex(ValueError, "separate directories"):
                    GameProject(self.game, self.textures)
        self.assertFalse((self.game / "Jobs").exists())

    def test_optional_tools_and_actual_cli_stdio_wiring(self):
        self.assertEqual(len(tool_list()), 8)
        self.assertEqual(len(tool_list(project=True)), 10)
        self.assertEqual(len(tool_list(textures=True, project=True)), 35)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        command = [sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root / "cli-jobs"),
                   "--asset-root", str(self.game / "SourceAssets"), "--game-project", str(self.game), "serve"]
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "project_inventory", "arguments": {"query": "Lantern", "offset": 0, "limit": 10}}}]
        result = subprocess.run(command, input="\n".join(json.dumps(m) for m in messages) + "\n",
                                capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout.splitlines()[-1])["result"]
        self.assertFalse(response["isError"])
        self.assertEqual(json.loads(response["content"][0]["text"])["matched"], 2)
        command[command.index("--workspace") + 1] = str(self.game / "ForbiddenJobs")
        result = subprocess.run(command, input="", capture_output=True, text=True, env=env, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.game / "ForbiddenJobs").exists())


if __name__ == "__main__":
    unittest.main()
