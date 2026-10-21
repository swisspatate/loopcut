# SPDX-License-Identifier: GPL-3.0-or-later
"""World composition, procedural maps, engine protocol doubles and real Blender cases."""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.procedural_level_builder import build_layout, analyze_layout
from cryptonyan_asset_studio.world_assembly import plan_world, normalize_world
from cryptonyan_asset_studio.biome_materials import generate_material, sample_pattern
from cryptonyan_asset_studio.materials import load_material, png_info
from cryptonyan_asset_studio.runner_kit import build_bundle
from cryptonyan_asset_studio.runner_motion import position_at
from cryptonyan_asset_studio.unreal_world import run_world_review, expected_location, sample_runtime
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.theme_batch import build_batch
from cryptonyan_asset_studio.publication import load_package
from test_cryptonyan_publisher import FakeUnreal, FakeMesh, FakeTask

PALETTES = {"ice": {"color_linear": [.08, .5, .8], "roughness": .3},
            "lava": {"color_linear": [.8, .1, .02], "roughness": .8}}
RECIPE = {"schema": "cryptonyan.world-recipe/1", "seed": 42, "biomes": PALETTES,
          "zones": [{"kit": "short", "biome": "ice", "decorations": 4},
                    {"kit": "long", "biome": "lava", "decorations": 6}]}
BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


class WorldFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.recipe = copy.deepcopy(RECIPE)
        for name, length in (("short", 12), ("long", 16)):
            folder = self.inputs / name
            folder.mkdir()
            layout = build_layout({"schema": "cryptonyan.runner-recipe/2", "rows": 3,
                                   "side_lane_probability": 1, "platform": {"length_m": length},
                                   "motion": {"probability": 1}})
            write_json(folder / "layout.json", layout)
            write_json(folder / "analysis.json", analyze_layout(layout))

        def catalog(folder):
            return {"fixture": folder.name}

        def import_plan(manifest):
            name = manifest.parent.parent.name
            layout = json.loads((self.inputs / name / "layout.json").read_text())
            length, width, thickness = layout["module"]["size_m"]
            return {"automatic_apply_supported": True, "source": str(manifest.parent / "SM_RunnerPlatform.glb"),
                    "destination": "/Game/CryptoNyan/Review/P_" + name, "asset_name": "SM_RunnerPlatform",
                    "asset": {"triangles": 12, "bounds_blender_m": [[0, -width/2, -thickness], [length, width/2, 0]], "material_count": 1}}
        for name, effect in (("validate_bundle", catalog), ("plan_import", import_plan)):
            mock = patch("cryptonyan_asset_studio.world_assembly." + name, side_effect=effect)
            mock.start()
            self.addCleanup(mock.stop)


class AssemblyTests(WorldFixture):
    def test_connect_variable_lengths_at_matching_sockets(self):
        plan = plan_world(self.recipe, self.inputs)
        self.assertEqual(len(plan["modules"]), 2)
        self.assertEqual(len(plan["actors"]), 28)
        self.assertEqual(plan["zones"][0]["exit_cm"], plan["zones"][1]["entry_cm"])
        boundary = plan["zones"][1]["entry_cm"][0]
        second = next(a for a in plan["actors"] if a["id"] == "Z01_R00_L1")
        self.assertEqual(second["origin_cm"], [boundary, 0, 0])
        self.assertTrue(plan["static_centre_route_passed"])
        self.assertFalse(plan["engine_validated"])
        self.assertFalse(plan["dynamics_validated"])
        self.assertEqual(plan["connections"][0]["opposed_normals"], [[1, 0, 0], [-1, 0, 0]])

    def test_seeded_decorations_protect_corridor(self):
        plan = plan_world(self.recipe, self.inputs)
        self.assertEqual(plan, plan_world(self.recipe, self.inputs))
        decor = [a for a in plan["actors"] if a["kind"] == "decoration"]
        self.assertTrue(all(not a["collision"] and a["amplitude_cm"] == 0 for a in decor))
        self.assertTrue(all(abs(a["origin_cm"][1]) - 12.5 >= 550 for a in decor))
        other = plan_world({**self.recipe, "seed": 43}, self.inputs)
        self.assertNotEqual(decor, [a for a in other["actors"] if a["kind"] == "decoration"])
        self.assertEqual([a for a in plan["actors"] if a["kind"] == "platform"],
                         [a for a in other["actors"] if a["kind"] == "platform"])

    def test_repeated_kit_reuses_module_binding(self):
        self.recipe["zones"][1]["kit"] = "short"
        plan = plan_world(self.recipe, self.inputs)
        self.assertEqual(len(plan["modules"]), 1)
        self.assertEqual(len({a["id"] for a in plan["actors"]}), len(plan["actors"]))

    def test_incompatible_width_or_movement_rejected(self):
        path = self.inputs / "long/layout.json"
        original = json.loads(path.read_text())
        for key in ("width", "speed"):
            data = copy.deepcopy(original)
            if key == "width":
                data["module"]["size_m"][1] = 4
            else:
                data["recipe"]["movement"]["speed_m_s"] = 9
            write_json(path, data)
            with self.assertRaises(ValueError):
                plan_world(self.recipe, self.inputs)

    def test_centre_exit_is_required_not_just_any_goal(self):
        path = self.inputs / "short/analysis.json"
        report = json.loads(path.read_text())
        report["reachable_goals"] = ["R02_L0"]
        write_json(path, report)
        with self.assertRaises(ValueError):
            plan_world(self.recipe, self.inputs)

    def test_bad_schema_palette_and_paths(self):
        for field, value in (("seed", True), ("zones", []), ("schema", "wrong"), ("biomes", {"bad/id": PALETTES["ice"]})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan_world({**self.recipe, field: value}, self.inputs)
        for path in ("../escape", "/escape", "C:/escape", "a\\b"):
            recipe = copy.deepcopy(self.recipe)
            recipe["zones"][0]["kit"] = path
            with self.assertRaises(ValueError):
                plan_world(recipe, self.inputs)
        with self.assertRaises(ValueError):
            normalize_world({**self.recipe, "biomes": {"ice": {"color_linear": [2, 0, 0], "roughness": .5}}})

    def test_actor_budget(self):
        for name in ("short", "long"):
            layout = build_layout({"rows": 32, "side_lane_probability": 1})
            write_json(self.inputs / name / "layout.json", layout)
            write_json(self.inputs / name / "analysis.json", analyze_layout(layout))
        self.recipe["zones"] *= 4
        with self.assertRaises(ValueError):
            plan_world(self.recipe, self.inputs)


class BiomeMaterialTests(unittest.TestCase):
    def test_field_and_derivatives_tile_in_both_directions(self):
        for seed in (0, 42, 2**32-1):
            for u, v in ((0, 0), (.37, .91), (-.2, 1.4)):
                h, du, dv = sample_pattern(u, v, seed)
                for shifted in (sample_pattern(u+1, v, seed), sample_pattern(u, v+1, seed)):
                    for a, b in zip((h, du, dv), shifted):
                        self.assertAlmostEqual(a, b, places=10)
                epsilon = 1e-6
                self.assertAlmostEqual(du, (sample_pattern(u+epsilon, v, seed)[0]-sample_pattern(u-epsilon, v, seed)[0])/(2*epsilon), places=7)
                self.assertAlmostEqual(dv, (sample_pattern(u, v+epsilon, seed)[0]-sample_pattern(u, v-epsilon, seed)[0])/(2*epsilon), places=7)

    def test_valid_bundle_determinism_variation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = generate_material(PALETTES["ice"], root / "a", seed=42, size=32)
            b = generate_material(PALETTES["ice"], root / "b", seed=42, size=32)
            c = generate_material(PALETTES["ice"], root / "c", seed=43, size=32)
            self.assertEqual(a, b)
            self.assertNotEqual(a, c)
            self.assertEqual(a, load_material(root / "a/material.json"))
            self.assertEqual(set(a["channels"]), {"base_color", "normal", "roughness"})
            for item in a["channels"].values():
                self.assertEqual(png_info((root / "a" / item["file"]).read_bytes()), {"width": 32, "height": 32})
            with self.assertRaises(FileExistsError):
                generate_material(PALETTES["ice"], root / "a", size=32)
            for size in (True, 31, 33, 1024):
                with self.assertRaises(ValueError):
                    generate_material(PALETTES["ice"], root / "bad", size=size)


class FakePlatform:
    def __init__(self, owner, number):
        self.owner, self.number = owner, number
        self.properties = {}
    def get_path_name(self):
        return self.owner.map + f".PersistentLevel.Actor{self.number}"
    def get_class(self):
        return SimpleNamespace(get_name=lambda: "CryptoNyanPlatform")
    def set_actor_label(self, name):
        self.label = name
    def set_editor_property(self, key, value):
        self.properties[key] = value
    def get_editor_property(self, key):
        return self.properties[key]
    def get_motion_elapsed_seconds(self):
        return 0.0
    def set_actor_scale3d(self, value):
        self.scale = value
    def get_actor_scale3d(self):
        return self.scale
    def get_actor_location(self):
        return self.location
    def configure_platform(self, mesh, material, origin, collision, amplitude, period, phase):
        self.args = (mesh, material, origin, collision, amplitude, period, phase)
        q = phase/period
        wave = 1-4*abs(q-.25) if q < .75 else 4*q-4
        self.location = SimpleNamespace(x=origin.x, y=origin.y, z=origin.z+amplitude*wave)
        if self.owner.bad_transform:
            self.location.z += 1
        return not self.owner.bad_config


class FakeWorldUnreal(FakeUnreal):
    EditorActorSubsystem = type("EditorActorSubsystem", (), {})
    UnrealEditorSubsystem = type("UnrealEditorSubsystem", (), {})
    CryptoNyanPlatform = FakePlatform
    Material = object
    MaterialFactoryNew = object
    MaterialExpressionConstant3Vector = object
    MaterialExpressionConstant = object
    MaterialProperty = SimpleNamespace(MP_BASE_COLOR="color", MP_ROUGHNESS="roughness")
    Name = str

    @staticmethod
    def Vector(x, y, z):
        return SimpleNamespace(x=x, y=y, z=z)
    @staticmethod
    def LinearColor(r, g, b, a):
        return (r, g, b, a)

    def __init__(self, plan):
        super().__init__()
        self.map = "/Game/CryptoNyan/ReviewMaps/Test"
        self.actors, self.materials, self.meshes = [], [], {}
        self.bad_transform = self.bad_config = self.bad_material = False
        self.collisions = 0
        for module in plan["modules"].values():
            spec = module["import"]
            mesh = FakeMesh()
            lo, hi = spec["asset"]["bounds_blender_m"]
            mesh.bounds = SimpleNamespace(min=self.Vector(100*lo[0], -100*hi[1], 100*lo[2]),
                                          max=self.Vector(100*hi[0], -100*lo[1], 100*hi[2]))
            mesh.triangles = 12
            self.meshes[spec["destination"] + "/" + spec["asset_name"]] = mesh
        self.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(create_asset=self.create_material))
        self.MaterialEditingLibrary = SimpleNamespace(create_material_expression=lambda *args: FakeTask(),
            connect_material_property=lambda *args: not self.bad_material, recompile_material=lambda m: None)
        self.game_world = object()
        self.GameplayStatics = SimpleNamespace(get_all_actors_of_class=lambda world, cls: self.actors)

    def create_material(self, name, destination, cls, factory):
        material = FakeTask()
        self.materials.append(material)
        self.paths.append(destination + "/" + name)
        return material
    def get_editor_subsystem(self, cls):
        if cls is self.EditorActorSubsystem:
            return SimpleNamespace(get_all_level_actors=lambda: self.actors, spawn_actor_from_class=self.spawn)
        if cls is self.UnrealEditorSubsystem:
            return SimpleNamespace(get_editor_world=lambda: SimpleNamespace(get_path_name=lambda: self.map + "." + self.map.rsplit("/", 1)[1]),
                                   get_game_world=lambda: self.game_world)
        return super().get_editor_subsystem(cls)
    def load_asset(self, path):
        return self.meshes.get(path)
    def spawn(self, cls, location):
        actor = FakePlatform(self, len(self.actors))
        self.actors.append(actor)
        return actor


class UnrealWorldTests(WorldFixture):
    def setUp(self):
        super().setUp()
        self.plan = plan_world(self.recipe, self.inputs)
        self.unreal = FakeWorldUnreal(self.plan)
        self.report = self.root / "review.json"

    def apply(self, **kwargs):
        return run_world_review(self.recipe, self.inputs, self.report, apply=True,
                                unreal_module=self.unreal, target_level=kwargs.get("target", self.unreal.map))

    def test_plan_without_importing_unreal_or_mutations(self):
        result = run_world_review(self.recipe, self.inputs, self.report)
        self.assertEqual(result["status"], "planned")
        self.assertFalse(self.unreal.reserved)
        with self.assertRaises(FileExistsError):
            self.apply()

    def test_successful_protocol_keeps_level_unsaved_and_engine_unvalidated(self):
        result = self.apply()
        self.assertEqual(result["status"], "placed_review_required")
        self.assertEqual(len(result["owned_actors"]), 28)
        self.assertEqual(len(result["saved_materials"]), 2)
        self.assertFalse(result["level_saved"])
        self.assertFalse(result["engine_validated"])
        for actor, item in zip(self.unreal.actors, self.plan["actors"]):
            self.assertEqual(actor.args[3], item["collision"])
            self.assertEqual(actor.properties["tags"], ["cryptonyan:" + self.plan["world_id"], "cryptonyan-item:" + item["id"]])

    def test_runtime_sample_reports_pose_errors_and_missing_actors(self):
        self.apply()
        report = sample_runtime(self.plan, unreal_module=self.unreal)
        self.assertTrue(report["sampled_pose_passed"])
        self.assertFalse(report["controller_validated"])
        self.unreal.actors[0].location.z += 3
        self.assertFalse(sample_runtime(self.plan, unreal_module=self.unreal)["sampled_pose_passed"])
        self.unreal.actors[0].location.z -= 3
        self.unreal.actors.pop()
        self.assertTrue(sample_runtime(self.plan, unreal_module=self.unreal)["missing"])

    def test_runtime_sample_requires_pie_and_intact_plan(self):
        self.unreal.game_world = None
        with self.assertRaises(ValueError):
            sample_runtime(self.plan, unreal_module=self.unreal)
        self.plan["actors"][0]["origin_cm"][0] += 1
        with self.assertRaises(ValueError):
            sample_runtime(self.plan, unreal_module=self.unreal)

    def test_wrong_map_or_occupied_map_blocks_before_mutation(self):
        result = self.apply(target="/Game/Production/Main")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(self.unreal.reserved)
        self.report.unlink()
        self.unreal.actors.append(FakePlatform(self.unreal, 0))
        self.assertIn("review_map_not_empty", self.apply()["error"])
        self.assertFalse(self.unreal.reserved)

    def test_unsupported_engine_missing_plugin_or_bad_mesh(self):
        for failure in ("version", "plugin", "mesh"):
            self.unreal = FakeWorldUnreal(self.plan)
            if failure == "version":
                self.unreal.version = "5.7.0"
            elif failure == "plugin":
                # An engine module without the plugin class, not a None-valued symbol.
                self.unreal = SimpleNamespace(**{k: getattr(self.unreal, k) for k in dir(self.unreal)
                                                if not k.startswith("__") and k != "CryptoNyanPlatform"})
            else:
                next(iter(self.unreal.meshes.values())).triangles = 11
            result = self.apply()
            self.assertEqual(result["status"], "failed")
            self.assertFalse(self.unreal.reserved)
            self.report.unlink()

    def test_existing_destination_rejected(self):
        self.unreal.existing = True
        self.assertEqual(self.apply()["error"], "review_destination_exists")
        self.assertFalse(self.unreal.reserved)

    def test_partial_failure_records_owned_objects_without_saving_level(self):
        for field, stage in (("bad_material", "creating_materials"), ("bad_config", "placing"),
                             ("bad_transform", "placing"), ("fail_save", "saving_materials")):
            self.unreal = FakeWorldUnreal(self.plan)
            setattr(self.unreal, field, True)
            result = self.apply()
            self.assertEqual(result["status"], "failed", field)
            self.assertEqual(result["failed_stage"], stage, field)
            self.assertFalse(result["level_saved"])
            self.assertEqual(json.loads(self.report.read_text()), result)
            self.report.unlink()

    def test_receipt_cannot_be_written_into_inputs(self):
        with self.assertRaises(ValueError):
            run_world_review(self.recipe, self.inputs, self.inputs / "receipt.json")


@unittest.skipUnless(shutil.which("g++"), "C++ compiler unavailable; engine-free motion test skipped")
class NativeMotionTests(unittest.TestCase):
    def test_compiled_cpp_matches_portable_motion_at_phases_and_subframes(self):
        header = ROOT / "integrations/unreal/CryptoNyanRuntime/Source/CryptoNyanRuntime/Public"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "motion.cpp"
            source.write_text('#include "CryptoNyanMotion.h"\n#include <iostream>\n#include <iomanip>\n'
                              'int main(){double t,p,s; while(std::cin>>t>>p>>s) '
                              'std::cout<<std::setprecision(17)<<CryptoNyanMotion::Triangle(t,p,s)<<"\\n";}\n')
            executable = root / ("motion.exe" if os.name == "nt" else "motion")
            subprocess.run([shutil.which("g++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(header),
                            str(source), "-o", str(executable)], check=True, capture_output=True, timeout=30)
            samples = [(t, p, phase) for p in (.8, 4., 20.) for phase in (0., .13, .7)
                       for t in (-2., 0., .37, p/4, p*.75, p, 100.)]
            run = subprocess.run([str(executable)], input="".join(f"{t} {p} {s}\n" for t,p,s in samples),
                                 capture_output=True, text=True, check=True, timeout=10)
            for (t, p, s), actual in zip(samples, run.stdout.splitlines(), strict=True):
                item = {"origin_m": [0, 0, 0], "motion": {"fps": 30, "amplitude_m": 1,
                        "period_frames": p*30, "phase_frames": s*30}}
                self.assertAlmostEqual(float(actual), position_at(item, t)[2], places=11)


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class AssemblyBlenderTests(unittest.TestCase):
    def test_real_modules_assemble_and_procedural_materials_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, length in (("short", 12), ("long", 16)):
                build_bundle({"rows": 3, "platform": {"length_m": length}}, root / name, blender=BLENDER)
            before = {name: digest(root / name / "modules.blend") for name in ("short", "long")}
            plan = plan_world(RECIPE, root)
            self.assertTrue(plan["static_centre_route_passed"])
            self.assertEqual(len(plan["connections"]), 1)
            moved = root / "relocated"
            moved.mkdir()
            for name in ("short", "long"):
                shutil.copytree(root / name, moved / name)
            self.assertEqual(plan, plan_world(RECIPE, moved))
            recipe = {"schema": "cryptonyan.theme-recipe/1", "assets": [
                {"id": "platform", "source": "short/modules.blend", "object": "RunnerPlatform"}], "themes": []}
            for name, values in PALETTES.items():
                generate_material(values, root / name, size=32)
                recipe["themes"].append({"id": name, "materials": {"platform": name + "/material.json"}})
            receipt = build_batch(recipe, root, root / "variants", blender=BLENDER)
            self.assertTrue(receipt["passed"])
            for job in receipt["jobs"]:
                package = load_package(root / "variants" / job["id"] / "manifest.json")
                self.assertEqual({t["role"] for t in package["textures"]}, {"base_color", "normal", "metallic_roughness"})
            self.assertEqual(before, {name: digest(root / name / "modules.blend") for name in before})
            path = root / "short/preview.blend"
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaises(ValueError):
                plan_world(RECIPE, root)


if __name__ == "__main__":
    unittest.main()
