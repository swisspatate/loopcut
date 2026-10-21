# SPDX-License-Identifier: GPL-3.0-or-later
"""PBR appearance plans, bounded snapshots and real portable textured worlds."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.world_assembly import plan_world
from cryptonyan_asset_studio.world_materials import plan_materials, validate_appearance, material_for
from cryptonyan_asset_studio.world_preview import build_preview, validate_preview, main
from cryptonyan_asset_studio.materials import pack_material
from cryptonyan_asset_studio.biome_materials import generate_material
from cryptonyan_asset_studio.runner_kit import build_bundle
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.executors import WorkerFailure
from test_cryptonyan_assembly import WorldFixture, RECIPE, PALETTES
from test_cryptonyan_materials import png

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")
BINDINGS = {"schema": "cryptonyan.world-materials/1", "bindings": [
    {"biome": "ice", "kit": "short", "material": "ice/material.json"},
    {"biome": "lava", "kit": "long", "material": "lava/material.json"}]}


class WorldMaterialTests(WorldFixture):
    def setUp(self):
        super().setUp()
        self.world = plan_world(self.recipe, self.inputs)
        self.bindings = copy.deepcopy(BINDINGS)
        for name, color in (("ice", (10, 120, 220)), ("lava", (200, 30, 5))):
            (self.inputs / (name+".png")).write_bytes(png(color))
            pack_material(self.inputs, {"base_color": name+".png"}, self.inputs / name)

    def test_complete_assignments_and_shared_material_deduplication(self):
        self.bindings["bindings"][1]["material"] = "ice/material.json"
        plan = plan_materials(self.bindings, self.inputs, self.world)
        self.assertEqual(len(plan["materials"]), 1)
        self.assertEqual(plan["texture_pixels"], 4)
        self.assertEqual(len(plan["inputs"]), 2)
        for actor in self.world["actors"]:
            self.assertEqual(material_for(plan, self.world, actor), "ice/material.json")
        self.assertFalse(plan["engine_validated"])

    def test_identity_order_independence_relocation_and_input_immutability(self):
        original = copy.deepcopy(self.bindings)
        expected = plan_materials(self.bindings, self.inputs, self.world)
        self.assertEqual(original, self.bindings)
        self.bindings["bindings"].reverse()
        moved = self.root / "moved"
        shutil.copytree(self.inputs, moved)
        self.assertEqual(expected, plan_materials(self.bindings, moved, self.world))

    def test_new_texture_changes_appearance_not_world_id(self):
        before = plan_materials(self.bindings, self.inputs, self.world)
        (self.inputs / "other.png").write_bytes(png((1, 2, 3)))
        pack_material(self.inputs, {"base_color": "other.png"}, self.inputs / "other")
        self.bindings["bindings"][0]["material"] = "other/material.json"
        after = plan_materials(self.bindings, self.inputs, self.world)
        self.assertNotEqual(before["appearance_id"], after["appearance_id"])
        self.assertEqual(before["world_id"], after["world_id"])

    def test_missing_duplicate_extra_pairs_and_bad_types_rejected(self):
        cases = [[], self.bindings["bindings"][:1], self.bindings["bindings"]*2,
                 [*self.bindings["bindings"], {"biome": "ice", "kit": "long", "material": "ice/material.json"}]]
        for bindings in cases:
            with self.assertRaises(ValueError):
                plan_materials({**self.bindings, "bindings": bindings}, self.inputs, self.world)
        for field, value in (("biome", []), ("kit", "missing"), ("material", True)):
            recipe = copy.deepcopy(self.bindings)
            recipe["bindings"][0][field] = value
            with self.assertRaises(ValueError):
                plan_materials(recipe, self.inputs, self.world)

    def test_paths_and_symlinks_rejected(self):
        for relative in ("../ice/material.json", "/escape", "C:/escape", "ice\\material.json", "ice//material.json"):
            recipe = copy.deepcopy(self.bindings)
            recipe["bindings"][0]["material"] = relative
            with self.assertRaises(ValueError):
                plan_materials(recipe, self.inputs, self.world)
        link = self.inputs / "linked"
        try:
            link.symlink_to(self.inputs / "ice", target_is_directory=True)
        except OSError:
            return  # Windows agents may lack symlink creation privileges.
        self.bindings["bindings"][0]["material"] = "linked/material.json"
        with self.assertRaises(ValueError):
            plan_materials(self.bindings, self.inputs, self.world)

    def test_byte_and_decoded_pixel_limits_before_output(self):
        for field, limit in (("MAX_TEXTURE_BYTES", 1), ("MAX_TEXTURE_PIXELS", 7)):
            with patch("cryptonyan_asset_studio.world_materials."+field, limit), self.assertRaises(ValueError):
                build_preview(self.recipe, self.inputs, self.root / "bad", materials=self.bindings)
            self.assertFalse((self.root / "bad").exists())

    def test_corrupt_texture_and_wrong_color_space_rejected(self):
        path = self.inputs / "ice/base_color.png"
        original = path.read_bytes()
        path.write_bytes(original+b"bad")
        with self.assertRaises(ValueError):
            plan_materials(self.bindings, self.inputs, self.world)
        path.write_bytes(original)
        manifest = self.inputs / "ice/material.json"
        data = json.loads(manifest.read_text())
        data["channels"]["base_color"]["color_space"] = "Non-Color"
        write_json(manifest, data)
        with self.assertRaises(ValueError):
            plan_materials(self.bindings, self.inputs, self.world)

    def test_appearance_tamper_and_world_binding_rejected(self):
        plan = plan_materials(self.bindings, self.inputs, self.world)
        self.assertEqual(plan, validate_appearance(plan, self.inputs, self.world))
        for field, value in (("appearance_id", "0"*64), ("world_id", "0"*64), ("texture_pixels", 1), ("engine_validated", True)):
            with self.assertRaises(ValueError):
                validate_appearance({**plan, field: value}, self.inputs, self.world)

    def test_plan_cli_without_blender_and_no_overwrite(self):
        write_json(self.root / "world.json", self.recipe)
        write_json(self.root / "materials.json", self.bindings)
        args = ["plan", str(self.root / "world.json"), "--source", str(self.inputs), "--destination", str(self.root / "preview"),
                "--materials", str(self.root / "materials.json")]
        with patch("sys.stdout", io.StringIO()), patch("cryptonyan_asset_studio.world_preview.run_process") as worker:
            self.assertEqual(main(args), 0)
            with self.assertRaises(FileExistsError):
                main(args)
        worker.assert_not_called()
        self.assertTrue((self.root / "preview/appearance.json").is_file())
        self.assertFalse((self.root / "preview/textures").exists())

    def test_snapshot_mutation_blocks_worker(self):
        original = shutil.copyfile
        def changed(source, target):
            original(source, target)
            if Path(target).suffix == ".png":
                Path(target).write_bytes(b"changed")
        with patch("cryptonyan_asset_studio.world_preview.shutil.copyfile", side_effect=changed), \
                patch("cryptonyan_asset_studio.world_preview.run_process") as worker, self.assertRaises(ValueError):
            build_preview(self.recipe, self.inputs, self.root / "bad", materials=self.bindings, blender=sys.executable)
        worker.assert_not_called()
        self.assertFalse((self.root / "bad/preview.json").exists())

    def test_worker_failure_keeps_snapshots_without_success_catalog(self):
        for name in ("short", "long"):
            (self.inputs / name / "modules.blend").write_bytes(b"fixture")
        with patch("cryptonyan_asset_studio.world_preview.run_process", side_effect=WorkerFailure(code="invalid_asset")), \
                self.assertRaises(WorkerFailure):
            build_preview(self.recipe, self.inputs, self.root / "failed", materials=self.bindings, blender=sys.executable)
        self.assertTrue((self.root / "failed/textures/ice/base_color.png").is_file())
        self.assertFalse((self.root / "failed/preview.json").exists())

    def test_source_texture_change_during_worker_rejects_publication(self):
        for name in ("short", "long"):
            (self.inputs / name / "modules.blend").write_bytes(b"fixture")
        def changed(command, context):
            (self.inputs / "ice/base_color.png").write_bytes(png((1, 2, 3)))
            (self.root / "changed/world-preview.blend").write_bytes(b"scripted worker output")
        with patch("cryptonyan_asset_studio.world_preview.run_process", side_effect=changed), self.assertRaises(ValueError):
            build_preview(self.recipe, self.inputs, self.root / "changed", materials=self.bindings, blender=sys.executable)
        self.assertFalse((self.root / "changed/preview.json").exists())


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class TexturedWorldBlenderTests(unittest.TestCase):
    def test_real_shared_meshes_distinct_packed_pbr_materials_and_portability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            for name, length in (("short", 12), ("long", 16)):
                build_bundle({"schema": "cryptonyan.runner-recipe/2", "rows": 3, "platform": {"length_m": length},
                              "side_lane_probability": 1, "motion": {"probability": 1}}, inputs / name, blender=BLENDER)
            for name, palette in PALETTES.items():
                generate_material(palette, inputs / name, size=32)
            generate_material(PALETTES["ice"], inputs / "ice_alt", seed=123, size=32)
            recipe, bindings = copy.deepcopy(RECIPE), copy.deepcopy(BINDINGS)
            recipe["zones"] += [{"kit": "short", "biome": "lava", "decorations": 1},
                                {"kit": "long", "biome": "ice", "decorations": 1}]
            bindings["bindings"] += [{"biome": "lava", "kit": "short", "material": "lava/material.json"},
                                     {"biome": "ice", "kit": "long", "material": "ice_alt/material.json"}]
            before = {p.relative_to(inputs): digest(p) for p in inputs.rglob("*") if p.is_file()}
            output = root / "world"
            result = build_preview(recipe, inputs, output, materials=bindings, blender=BLENDER)
            self.assertTrue(result["built"])
            catalog = validate_preview(output, source_root=inputs)
            self.assertEqual(catalog["schema"], "cryptonyan.world-preview/2")
            self.assertEqual(catalog["appearance_id"], result["appearance_id"])
            self.assertEqual(before, {p.relative_to(inputs): digest(p) for p in inputs.rglob("*") if p.is_file()})
            # Prove portability by removing originals and relocating the whole output.
            shutil.rmtree(inputs)
            relocated = root / "relocated"
            output.rename(relocated)
            self.assertEqual(catalog, validate_preview(relocated))
            run = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_world_pbr_fixture.py"),
                "--", str(relocated)], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertIn("CRYPTONYAN_WORLD_PBR_PASSED", run.stdout)
            for relative in ("textures/ice/base_color.png", "appearance.json", "world-preview.blend"):
                path = relocated / relative
                original = path.read_bytes()
                path.write_bytes(original+b"changed")
                with self.assertRaises(ValueError):
                    validate_preview(relocated)
                path.write_bytes(original)

    def test_real_non_greyscale_roughness_fails_without_saving_world(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            build_bundle({"rows": 3}, inputs / "short", blender=BLENDER)
            (inputs / "color.png").write_bytes(png((255, 0, 0)))
            pack_material(inputs, {"base_color": "color.png", "roughness": "color.png"}, inputs / "bad")
            recipe = copy.deepcopy(RECIPE)
            recipe["zones"] = recipe["zones"][:1]
            bindings = {"schema": BINDINGS["schema"], "bindings": [{"biome": "ice", "kit": "short", "material": "bad/material.json"}]}
            before = digest(inputs / "short/modules.blend")
            with self.assertRaises(WorkerFailure):
                build_preview(recipe, inputs, root / "bad_world", materials=bindings, blender=BLENDER)
            self.assertFalse((root / "bad_world/preview.json").exists())
            self.assertFalse((root / "bad_world/world-preview.blend").exists())
            self.assertEqual(before, digest(inputs / "short/modules.blend"))


if __name__ == "__main__":
    unittest.main()
