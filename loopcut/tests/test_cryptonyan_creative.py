# SPDX-License-Identifier: GPL-3.0-or-later
"""Creative recipe integrity, actual Blender assets and engine-free gameplay rules."""
import copy
import io
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.creative_kit import recipe, plan, terrain_height, sprite_atlas, build, validate_bundle, validate_cat_glb, ELEMENTS, CLIPS, main
from cryptonyan_asset_studio.materials import png_info
from cryptonyan_asset_studio.biome_materials import generate_material
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.unreal_creative import review

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


class CreativeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_plan_deterministic_roundtrip_and_no_shared_presets(self):
        source = {"seed": 72, "biome": "ice"}
        original = copy.deepcopy(source)
        a = plan(source)
        self.assertEqual(a, plan(json.loads(json.dumps(a["recipe"]))))
        self.assertEqual(source, original)
        a["elements"]["fire"][0] = .01
        self.assertEqual(plan(source)["elements"]["fire"][0], 1)
        self.assertNotEqual(plan(source)["kit_id"], plan({**source, "seed": 73})["kit_id"])

    def test_parameter_budgets_and_unknown_fields(self):
        for data in ({"seed": True}, {"seed": -1}, {"floors": 5}, {"bays": 7}, {"terrain_grid": 1025},
                     {"terrain_size_m": float("nan")}, {"mountain_height_m": 65}, {"lighting": []},
                     {"weather": "storm"}, {"schema": "bad"}, {"execute": "script"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                plan(data)
        maximum = plan({"bays":6, "floors":4, "terrain_grid":129})
        self.assertLess(len(maximum["actors"]), 300)
        self.assertFalse(maximum["navigation_validated"])

    def test_terrain_bounds_central_plaza_and_seed_variants(self):
        spec = recipe({})
        heights = [terrain_height(x,y,spec) for x in range(-32,33) for y in range(-32,33)]
        self.assertGreater(max(heights), 3)
        self.assertTrue(all(0 <= h <= spec["mountain_height_m"] for h in heights))
        self.assertEqual(terrain_height(4,4,spec), 0)
        self.assertNotEqual(terrain_height(22,22,spec), terrain_height(22,22,recipe({"seed":41})))

    def test_stairs_rise_sockets_module_bounds_and_unique_actors(self):
        data = plan({})
        stairs = data["modules"]["stairs"]
        self.assertAlmostEqual(max(b["center"][2]+b["size"][2]/2 for b in stairs), 3)
        self.assertEqual(data["sockets"]["stairs"]["exit_m"], [3,0,3])
        self.assertEqual(len({a["id"] for a in data["actors"]}), len(data["actors"]))
        for module in data["modules"].values():
            self.assertTrue(all(all(v>0 for v in b["size"]) for b in module))

    def test_six_distinct_valid_rgba_flipbooks(self):
        images = [sprite_atlas(c) for c in ELEMENTS.values()]
        self.assertEqual(len(set(images)), 6)
        for image in images:
            self.assertEqual(png_info(image), {"width":128,"height":128})
            self.assertEqual(image[25], 6)  # RGBA, transparent burst background.

    def test_plan_cli_no_worker_and_no_overwrite(self):
        write_json(self.root / "recipe.json", {})
        args = ["plan", str(self.root / "recipe.json"), "--destination", str(self.root / "out")]
        with patch("sys.stdout", io.StringIO()), patch("cryptonyan_asset_studio.creative_kit.run_process") as worker:
            main(args)
            worker.assert_not_called()
            with self.assertRaises(FileExistsError):
                main(args)
        self.assertFalse((self.root / "out/creative.json").exists())

    def test_worker_failure_never_publishes_success(self):
        with patch("cryptonyan_asset_studio.creative_kit.BlenderExecutor"), patch(
                "cryptonyan_asset_studio.creative_kit.run_process", side_effect=WorkerFailure("blender_error")):
            with self.assertRaises(WorkerFailure):
                build({}, self.root / "bad", blender="unused")
        self.assertFalse((self.root / "bad/creative.json").exists())

    def test_bad_timeout_and_source_material_preflight(self):
        for timeout in (True, 0, float("inf"), 3601):
            with self.assertRaises(ValueError):
                build({}, self.root / "bad", timeout_seconds=timeout)
        with self.assertRaises(FileNotFoundError):
            build({}, self.root / "bad", material=self.root / "missing.json")
        self.assertFalse((self.root / "bad").exists())

    def test_shared_material_pixel_budget_before_creating_output(self):
        generate_material({"color_linear":[.2,.5,.7],"roughness":.65}, self.root / "source", seed=42, size=32)
        with patch("cryptonyan_asset_studio.creative_kit.MAX_TEXTURE_PIXELS", 1), self.assertRaises(ValueError):
            build({}, self.root / "bad", material=self.root / "source/material.json")
        self.assertFalse((self.root / "bad").exists())

    def test_unreal_dry_run_and_map_refusal_are_non_destructive(self):
        result = review(self.root / "review.json")
        self.assertEqual(result["status"], "planned")
        self.assertFalse(result["engine_validated"])
        with self.assertRaises(FileExistsError):
            review(self.root / "review.json")
        failed = review(self.root / "bad.json", apply=True, target_level="/Game/Production")
        self.assertEqual(failed["error"], "require_explicit_empty_review_map")
        self.assertFalse(failed["owned_actors"])


@unittest.skipUnless(shutil.which("g++"), "C++ compiler unavailable")
class ElementRuleTests(unittest.TestCase):
    def test_compiled_rules_order_properties_budgets_and_particle_limits(self):
        header = ROOT / "integrations/unreal/CryptoNyanRuntime/Source/CryptoNyanRuntime/Public"
        source = r'''
#include "CryptoNyanElements.h"
#include <cassert>
#include <limits>
using namespace CryptoNyanElements;
int main() {
 Traits t{true,true,false,true}; State s;
 assert(!React(s,t,Element::Ice).Frozen);
 s=React(s,t,Element::Water); assert(s.Wet);
 s=React(s,t,Element::Ice); assert(s.Frozen);
 s=React(s,t,Element::Fire); assert(!s.Frozen && s.Wet && !s.Burned);
 s=React(s,t,Element::Fire); assert(!s.Wet && !s.Burned);
 s=React(s,t,Element::Fire); assert(s.Burned);
 assert(!React(s,t,Element::Earth).Raised);
 s={}; assert(!React(s,t,Element::Electric).Charged);
 s=React(s,t,Element::Water); assert(React(s,t,Element::Electric).Charged);
 assert(React(State{},t,Element::Earth).Raised); assert(React(State{},t,Element::Wind).Gust);
 assert(!React(State{},Traits{},Element::Earth).Raised);
 assert(CanSpend(2,1,10,10,.5)); assert(!CanSpend(.9,1,100,10,.5));
 assert(!CanSpend(2,1,9,10,.5)); assert(!CanSpend(2,1,100,-1,.5));
 assert(!CanSpend(std::numeric_limits<double>::quiet_NaN(),0,100,10,.5));
 assert(Particle(0,24,0,1).Scale>0); assert(Particle(0,24,1,1).Scale==0);
 assert(Particle(24,24,0,1).Scale==0); assert(Particle(0,129,0,1).Scale==0);
 for (int i=0;i<24;++i) {auto p=Particle(i,24,.5,1); assert(std::isfinite(p.X)&&std::isfinite(p.Y)&&p.Scale>0);}
}
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rules.cpp").write_text(source)
            exe = root / ("rules.exe" if os.name == "nt" else "rules")
            subprocess.run([shutil.which("g++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(header),
                            str(root / "rules.cpp"), "-o", str(exe)], check=True, capture_output=True, timeout=30)
            subprocess.run([str(exe)], check=True, capture_output=True, timeout=10)


class UnrealCreativeTests(unittest.TestCase):
    """Scripted editor API tests; full UHT/plugin/editor validation remains local."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.level = "/Game/CryptoNyan/ReviewMaps/Elements"
        self.world = Mock()
        self.world.get_path_name.return_value = self.level+".Elements"
        self.editor = Mock()
        self.editor.get_all_level_actors.return_value = []
        self.actors = []
        def spawn(*args):
            actor = Mock()
            actor.get_path_name.return_value = self.level+".Actor"+str(len(self.actors))
            self.actors.append(actor)
            return actor
        self.editor.spawn_actor_from_class.side_effect = spawn
        self.assets = Mock()
        self.assets.does_directory_exist.return_value = False
        self.assets.list_assets.return_value = []
        self.assets.make_directory.return_value = True
        self.assets.save_loaded_asset.return_value = True
        self.editing = Mock()
        self.editing.connect_material_property.return_value = True
        self.u = SimpleNamespace(EditorActorSubsystem=object(), UnrealEditorSubsystem=object(),
            CryptoNyanElementSurface=object(), CryptoNyanAtmosphere=object(), CryptoNyanPowerComponent=object(),
            CryptoNyanPowerMenu=object(), CryptoNyanWeather=SimpleNamespace(SNOW="snow"),
            MaterialExpressionVectorParameter=object(), Material=object(), MaterialFactoryNew=Mock(), PlayerStart=object(),
            MaterialProperty=SimpleNamespace(MP_BASE_COLOR="base",MP_EMISSIVE_COLOR="emissive"),
            Name=str, LinearColor=lambda *v:v, Vector=lambda *v:v,
            MaterialEditingLibrary=self.editing, EditorAssetLibrary=self.assets, AssetToolsHelpers=Mock())
        self.u.get_editor_subsystem=lambda cls: self.editor if cls is self.u.EditorActorSubsystem else SimpleNamespace(get_editor_world=lambda:self.world)
        self.probe = patch("cryptonyan_asset_studio.unreal_creative.probe", return_value={"missing_apis":[],"target_version_matches":True})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def run_review(self):
        return review(self.root / "receipt.json", apply=True,target_level=self.level,unreal_module=self.u)

    def test_places_owned_examples_material_and_weather_without_saving_map(self):
        result = self.run_review()
        self.assertEqual(result["status"],"placed_review_required")
        self.assertEqual(len(result["owned_actors"]),8)
        self.assertEqual(result["owned_assets"],result["saved_assets"])
        self.assertFalse(result["level_saved"])
        self.assertFalse(result["engine_validated"])
        self.actors[1].set_editor_property.assert_any_call("liquid",True)
        self.actors[-1].configure_atmosphere.assert_called_once_with(5000,.01,"snow")
        self.assertEqual(json.loads((self.root / "receipt.json").read_text()),result)

    def test_wrong_map_existing_content_or_nonempty_map_refuse_before_mutation(self):
        for case in ("wrong_map","content","actors"):
            self.world.get_path_name.return_value = "/Game/Production.Production" if case=="wrong_map" else self.level+".Elements"
            self.assets.does_directory_exist.return_value = case=="content"
            actor = Mock(); actor.get_class.return_value.get_name.return_value = "PlayerStart"
            self.editor.get_all_level_actors.return_value = [actor] if case=="actors" else []
            result = self.run_review()
            self.assertEqual(result["status"],"failed")
            self.assets.make_directory.assert_not_called()
            self.editor.spawn_actor_from_class.assert_not_called()
            (self.root / "receipt.json").unlink()

    def test_missing_plugin_api_refuses_before_content_creation(self):
        del self.u.CryptoNyanPowerMenu
        self.assertEqual(self.run_review()["error"],"require_UE_5_8_and_compiled_creative_plugin")
        self.assets.make_directory.assert_not_called()

    def test_partial_failure_records_owned_assets_and_actors(self):
        original = self.editor.spawn_actor_from_class.side_effect
        self.editor.spawn_actor_from_class.side_effect = lambda *a: original(*a) if len(self.actors)<2 else None
        result = self.run_review()
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["failed_stage"],"placing")
        self.assertEqual(len(result["owned_actors"]),2)
        self.assertEqual(len(result["owned_assets"]),1)
        self.assertFalse(result["saved_assets"])


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class CreativeBlenderTests(unittest.TestCase):
    def test_real_generated_assets_ik_animations_pbr_and_portable_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            material = generate_material({"color_linear":[.2,.5,.7],"roughness":.65}, root / "source", seed=42, size=32)
            source_hashes = {p.name:digest(p) for p in (root / "source").iterdir()}
            result = build({"terrain_grid":33,"weather":"snow","liquid":"water"}, root / "kit", blender=BLENDER,
                           material=root / "source/material.json", timeout_seconds=180)
            self.assertTrue(result["built"])
            self.assertEqual(source_hashes,{p.name:digest(p) for p in (root / "source").iterdir()})
            shutil.rmtree(root / "source")
            shutil.move(root / "kit", root / "relocated")
            bundle = root / "relocated"
            validate_bundle(bundle)
            data = (bundle / "cat.glb").read_bytes()
            length = struct.unpack_from("<I",data,12)[0]
            gltf = json.loads(data[20:20+length])
            self.assertEqual({a["name"] for a in gltf["animations"]}, {"CN_"+name for name in CLIPS})
            self.assertEqual(len(gltf["skins"]),1)
            self.assertTrue(all("uri" not in b for b in gltf["buffers"]))
            # A structurally valid export with a dropped/renamed action is not a complete cat kit.
            gltf["animations"][0]["name"] = "missing_clip"
            altered = json.dumps(gltf).encode()
            altered += b" "*((-len(altered))%4)
            rest = data[20+length:]
            malformed = root / "incomplete.glb"
            malformed.write_bytes(struct.pack("<4sII",b"glTF",2,20+len(altered)+len(rest))+
                                  struct.pack("<I4s",len(altered),b"JSON")+altered+rest)
            with self.assertRaisesRegex(ValueError,"all six clips"):
                validate_cat_glb(malformed)
            check = subprocess.run([str(BLENDER),"--background","--factory-startup","--disable-autoexec","--threads","1",
                                    "--python-exit-code","1","--python",str(ROOT / "loopcut/harness/cryptonyan_creative_fixture.py"),
                                    "--",str(bundle)], capture_output=True,text=True,timeout=90)
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)
            self.assertIn("CRYPTONYAN_CREATIVE_PASSED",check.stdout)
            self.assertEqual((bundle / "height.raw").stat().st_size,33*33*2)
            (bundle / "fx/fire.png").write_bytes(b"corrupted")
            with self.assertRaises(ValueError): validate_bundle(bundle)
            with self.assertRaises(FileExistsError): build({}, bundle, blender=BLENDER)


if __name__ == "__main__":
    unittest.main()
