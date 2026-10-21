# SPDX-License-Identifier: GPL-3.0-or-later
"""Real headless integration; explicit skips when no Blender is available."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "addons_core"))
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.executors import BlenderExecutor
from cryptonyan_asset_studio.storage import digest, safe_path

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER to enable headless tests")
class BlenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.scene = self.assets / "fixture.blend"
        self.run_blender("create", self.scene)

    def run_blender(self, mode, path):
        completed = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec",
            "--threads", "1", "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_fixture.py"),
            "--", mode, str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("CRYPTONYAN_BLENDER_ASSERTIONS_PASSED", completed.stdout)

    def test_direct_audit_guards_and_geometry_preservation(self):
        before = digest(self.scene)
        self.run_blender("verify", self.scene)
        self.assertEqual(digest(self.scene), before)

    def test_headless_bridge_dry_run_and_review_copy(self):
        before = digest(self.scene)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            dry = bridge.submit({"inputs": ["fixture.blend"]})
            final = bridge.wait(dry["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            self.assertEqual(len(final["artifacts"]), 1)
            self.assertTrue(bridge.result(dry["id"])["quality"]["reports"][0]["dry_run"])
            fixed = bridge.revise(dry["id"], {"inputs": ["fixture.blend"], "constraints": {"repair_copy": True}})
            final = bridge.wait(fixed["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            self.assertEqual(len(final["artifacts"]), 2)
            result = bridge.result(fixed["id"])
            self.assertFalse(result["quality"]["reports"][0]["dry_run"])
            repaired = next(a for a in final["artifacts"] if a["path"].endswith(".blend"))
            self.run_blender("verify_saved", safe_path(bridge.store.folder(fixed["id"]), repaired["path"]))
        self.assertEqual(digest(self.scene), before)

    def test_scripted_codex_dispatches_real_blender(self):
        # The app-server peer is scripted; the delegated Blender worker is real.
        from test_cryptonyan_codex import ScriptedCodex
        before = digest(self.scene)
        executor = ScriptedCodex("tool", self.root / "wire.jsonl", BlenderExecutor(BLENDER))
        with MissionBridge(self.root / "jobs", self.assets, executor) as bridge:
            task = bridge.submit({"inputs": ["fixture.blend"]})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            result = bridge.result(task["id"])
            self.assertEqual(result["quality"]["reports"][0]["source"], "blender")
            self.assertTrue(any(a["path"].endswith("codex-dispatch.json") for a in final["artifacts"]))
        self.assertEqual(digest(self.scene), before)

    def test_publish_static_mesh_and_plan_unreal(self):
        from cryptonyan_asset_studio.publication import load_package
        from cryptonyan_asset_studio.unreal_review import run_review_import
        before = digest(self.scene)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            task = bridge.submit({"type": "asset_publish", "inputs": ["fixture.blend"], "target_assets": ["Bad Name"]})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            result = bridge.result(task["id"])
            self.assertEqual(len(final["artifacts"]), 3)
            self.assertEqual(result["publication"]["asset"]["triangles"], 12)
            self.assertEqual(result["publication"]["asset"]["bounds_blender_m"], [[-2, -1, -1], [2, 1, 1]])
            self.assertEqual(result["publication"]["source"]["sha256"], before)
            manifest = bridge.store.folder(task["id"]) / "attempt-1" / "manifest.json"
            self.assertEqual(load_package(manifest), result["publication"])
            receipt = run_review_import(manifest, self.root / "plan.json")
            self.assertEqual(receipt["status"], "planned")
        self.assertEqual(digest(self.scene), before)

    def test_publish_guards_and_quality_gate(self):
        before = digest(self.scene)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            for name in ("Guarded", "Shaped", "CatRig"):
                with self.subTest(name=name):
                    task = bridge.submit({"type": "asset_publish", "inputs": ["fixture.blend"], "target_assets": [name]})
                    final = bridge.wait(task["id"], 60)
                    self.assertFalse((bridge.store.folder(task["id"]) / "attempt-1" / "manifest.json").exists())
                    self.assertTrue(final["state"] == "failed" or final["quality_passed"] is False)
            task = bridge.submit({"type": "asset_publish", "inputs": ["fixture.blend"], "target_assets": ["Bad Name"],
                                  "success_criteria": {"max_triangles": 1}})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            self.assertFalse(final["quality_passed"])
            self.assertEqual(len(final["artifacts"]), 1)
            self.assertNotIn("publication", bridge.result(task["id"]))
        self.assertEqual(digest(self.scene), before)

    def test_publish_asymmetric_geometry_material_and_codex_dispatch(self):
        from test_cryptonyan_codex import ScriptedCodex
        self.run_blender("create_publish", self.scene)
        before = digest(self.scene)
        executor = ScriptedCodex("tool", self.root / "wire.jsonl", BlenderExecutor(BLENDER))
        with MissionBridge(self.root / "jobs", self.assets, executor) as bridge:
            task = bridge.submit({"type": "asset_publish", "inputs": ["fixture.blend"], "target_assets": ["Platform"]})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            result = bridge.result(task["id"])
            self.assertEqual(result["publication"]["asset"]["triangles"], 4)
            asset = next(a for a in final["artifacts"] if a["path"].endswith(".glb"))
            self.run_blender("verify_export", safe_path(bridge.store.folder(task["id"]), asset["path"]))
        self.assertEqual(digest(self.scene), before)

    def test_publish_rejects_mirroring_and_procedural_material(self):
        self.run_blender("create_publish", self.scene)
        before = digest(self.scene)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            for name in ("Negative", "Procedural"):
                task = bridge.submit({"type": "asset_publish", "inputs": ["fixture.blend"], "target_assets": [name]})
                final = bridge.wait(task["id"], 60)
                self.assertEqual(final["state"], "failed", final)
                self.assertTrue(final["error"].startswith("publish_guard:"), final)
        self.assertEqual(digest(self.scene), before)

    def prepare_material(self):
        from test_cryptonyan_materials import png
        from cryptonyan_asset_studio.materials import pack_material
        roles = {"base_color": (80, 170, 30), "normal": (128, 128, 255),
                 "roughness": (160, 160, 160), "metallic": (40, 40, 40)}
        for role, color in roles.items():
            (self.root / (role + ".png")).write_bytes(png(color))
        pack_material(self.root, {role: role + ".png" for role in roles}, self.root / "pbr")
        output = self.assets / "textured.blend"
        command = [BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                   "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_material.py"),
                   "--", "--source", str(self.scene), "--bundle", str(self.root / "pbr/material.json"),
                   "--object", "Bad Name", "--output", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return output, command

    def test_pbr_copy_publish_embedded_textures_and_reimport(self):
        from cryptonyan_asset_studio.publication import load_package
        from cryptonyan_asset_studio.unreal_review import run_review_import
        before = digest(self.scene)
        textured, _ = self.prepare_material()
        self.assertEqual(digest(self.scene), before)
        textured_before = digest(textured)
        # Removing the original texture bundle proves publishing uses packed data.
        shutil.rmtree(self.root / "pbr")
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            task = bridge.submit({"type": "asset_publish", "inputs": [textured.name], "target_assets": ["Bad Name"]})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            manifest = bridge.store.folder(task["id"]) / "attempt-1/manifest.json"
            package = load_package(manifest)
            self.assertEqual(package["schema"], "cryptonyan.publication/2")
            self.assertEqual({t["role"] for t in package["textures"]}, {"base_color", "metallic_roughness", "normal"})
            self.assertEqual(len(final["artifacts"]), 3)
            self.run_blender("verify_pbr", manifest.parent / package["asset"]["file"])
            plan = run_review_import(manifest, self.root / "unreal-pbr-plan.json")
            self.assertFalse(plan["plan"]["automatic_apply_supported"])
            # The guard precedes even importing the unavailable Unreal module.
            receipt = run_review_import(manifest, self.root / "unreal-pbr-apply.json", apply=True)
            self.assertEqual(receipt["status"], "failed")
            self.assertTrue(receipt["error"].startswith("textured_apply_unvalidated:"))
            self.assertFalse(receipt["partial_review_folder"])
        self.assertEqual(digest(self.scene), before)
        self.assertEqual(digest(textured), textured_before)

    def test_material_copy_refuses_overwrite(self):
        textured, command = self.prepare_material()
        before = digest(textured)
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(digest(textured), before)

    def test_pbr_guards_reject_external_images_spaces_uvs_and_mapping(self):
        textured, _ = self.prepare_material()
        self.run_blender("create_pbr_guards", textured)
        before = digest(textured)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            for name in ("WrongColorSpace", "ExternalImage", "MultipleUVs", "MappedTexture", "ColoredScalar", "MutedNode"):
                with self.subTest(name=name):
                    task = bridge.submit({"type": "asset_publish", "inputs": [textured.name], "target_assets": [name]})
                    final = bridge.wait(task["id"], 60)
                    self.assertEqual(final["state"], "failed", final)
                    self.assertTrue(final["error"].startswith("publish_guard:"), final)
        self.assertEqual(digest(textured), before)


if __name__ == "__main__":
    unittest.main()
