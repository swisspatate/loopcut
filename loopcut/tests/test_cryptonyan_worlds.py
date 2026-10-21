# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-height runner, deterministic lifts and asset/theme integration checks."""
import copy
import csv
import io
import json
import math
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
from cryptonyan_asset_studio.procedural_level_builder import build_layout, analyze_layout, _transition, points_csv, scan_seeds
from cryptonyan_asset_studio.runner_motion import position_at, motion_tracks
from cryptonyan_asset_studio.runner_kit import build_bundle, validate_bundle
from cryptonyan_asset_studio.materials import pack_material
from cryptonyan_asset_studio.theme_batch import plan_batch, build_batch, validate_batch, main
from cryptonyan_asset_studio.executors import WorkerFailure, BudgetExpired
from cryptonyan_asset_studio.storage import digest
from cryptonyan_asset_studio.publication import load_package
from test_cryptonyan_materials import png

V2 = {"schema": "cryptonyan.runner-recipe/2", "rows": 5, "side_lane_probability": 1,
      "gap_choices_m": [1], "motion": {"probability": 0}}
BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


class WorldModelTests(unittest.TestCase):
    def test_heights_entry_exit_and_static_branch_rejoin(self):
        layout = build_layout(V2)
        self.assertEqual(layout["schema"], "cryptonyan.runner-layout/2")
        for p in layout["placements"]:
            expected = 0 if p["lane"] == 0 or p["row"] in (0, 4) else 0.6 * p["lane"]
            self.assertEqual(p["origin_m"][2], expected)
        report = analyze_layout(layout)
        self.assertTrue(report["model_passed"])
        edges = {(e["from"], e["to"]) for e in report["accepted_edges"]}
        self.assertIn(("R00_L1", "R01_L2"), edges)
        self.assertIn(("R03_L2", "R04_L1"), edges)

    def test_unequal_height_ballistic_landing_and_leading_face(self):
        layout = build_layout(V2)
        positions = {p["id"]: p for p in layout["placements"]}
        movement = layout["recipe"]["movement"]
        safe = movement["capsule_radius_m"] + movement["landing_margin_m"]
        found = set()
        for edge in analyze_layout(layout)["accepted_edges"]:
            if edge["kind"] != "jump":
                continue
            source, target = positions[edge["from"]], positions[edge["to"]]
            dz = target["origin_m"][2] - source["origin_m"][2]
            t, v, g = edge["flight_seconds"], movement["jump_speed_m_s"], movement["gravity_m_s2"]
            self.assertAlmostEqual(v*t - 0.5*g*t*t, dz)
            self.assertLess(v-g*t, 0)
            if dz:
                found.add(math.copysign(1, dz))
            if dz > 0:
                for launch in edge["launch_interval_x_m"]:
                    entry_t = (target["origin_m"][0] - safe - launch) / movement["speed_m_s"]
                    self.assertGreaterEqual(v*entry_t - .5*g*entry_t**2 + 1e-10, dz)
        self.assertEqual(found, {-1, 1})

    def test_too_high_branch_rejected_and_flat_route_preserved(self):
        layout = build_layout({**V2, "side_heights_m": [-5, 5]})
        report = analyze_layout(layout)
        self.assertTrue(report["model_passed"])
        self.assertIn("R01_L2", report["unreachable"])

    def test_motion_never_certified_as_static(self):
        layout = build_layout({**V2, "motion": {"probability": 1}})
        report = analyze_layout(layout)
        self.assertEqual(len(report["dynamic_platforms"]), 6)
        self.assertTrue(report["model_passed"])
        self.assertFalse(report["dynamics_validated"])
        self.assertFalse(report["engine_validated"])
        self.assertTrue(all(e["reason"] == "dynamic_branch_requires_engine_validation"
                            for e in report["rejected_edges"] if e["to"] in report["dynamic_platforms"]))
        self.assertTrue(all(e["from"] not in report["dynamic_platforms"] and e["to"] not in report["dynamic_platforms"]
                            for e in report["accepted_edges"]))
        self.assertTrue(all("_L1" in e["to"] for e in report["witness"][:-1]))

    def test_triangle_phase_extrema_periodicity_and_subframes(self):
        p = {"origin_m": [4, 3, 2], "motion": {"fps": 30, "period_frames": 120, "phase_frames": 0, "amplitude_m": .5}}
        self.assertEqual([position_at(p, t)[2] for t in (0, 1, 2, 3, 4)], [2, 2.5, 2, 1.5, 2])
        self.assertEqual(position_at(p, .5), [4, 3, 2.25])
        for t in (-2.1, 0, .37, 3.9, 72.8):
            self.assertAlmostEqual(position_at(p, t)[2], position_at(p, t + 4)[2])
        p["motion"]["phase_frames"] = 30
        self.assertEqual(position_at(p, 0)[2], 2.5)
        for bad in (True, float("nan"), float("inf"), 1e10):
            with self.assertRaises(ValueError):
                position_at(p, bad)

    def test_motion_export_axis_units_seed_and_period(self):
        recipe = {**V2, "motion": {"probability": 1, "period_frames": 80}}
        layout = build_layout(recipe)
        self.assertEqual(layout, build_layout(recipe))
        tracks = motion_tracks(layout)
        self.assertEqual(len(tracks["tracks"]), 6)
        first = tracks["tracks"][0]
        self.assertEqual(first["origin_unreal_cm"], [1300, 300, -60])
        self.assertEqual(first["amplitude_cm"], 50)
        self.assertEqual(first["period_seconds"], 80/30)
        self.assertNotEqual(tracks["tracks"], motion_tracks(build_layout({**recipe, "seed": 43}))["tracks"])
        rows = list(csv.DictReader(io.StringIO(points_csv(layout))))
        self.assertEqual(float(rows[3]["z_cm"]), -60)

    def test_invalid_v2_parameters(self):
        for extra in ({"side_heights_m": [1]}, {"side_heights_m": [True, 2]}, {"side_heights_m": [0, 6]},
                      {"motion": {"period_frames": 121}}, {"motion": {"period_frames": True}},
                      {"motion": {"probability": 2}}, {"motion": {"axis": "x"}},
                      {"motion": {"amplitude_m": float("nan")}}, {"extra": 1}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                build_layout({**V2, **extra})

    def test_v2_scan_keeps_static_fallback_and_detects_impossible_gaps(self):
        self.assertTrue(scan_seeds({**V2, "motion": {"probability": 1}}, count=32)["all_model_passed"])
        self.assertEqual(scan_seeds({**V2, "gap_choices_m": [20]}, count=4)["failure_seeds"], [0, 1, 2, 3])


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets.blend").write_bytes(b"portable planning fixture, not a Blender file")
        for name, color in (("ice", (40, 180, 255)), ("lava", (255, 60, 10))):
            (self.root / "color.png").write_bytes(png(color))
            pack_material(self.root, {"base_color": "color.png"}, self.root / name)
        self.recipe = {"schema": "cryptonyan.theme-recipe/1",
                       "assets": [{"id": name.lower(), "source": "assets.blend", "object": name} for name in ("BlockA", "BlockB")],
                       "themes": [{"id": theme, "materials": {"blocka": theme + "/material.json", "blockb": theme + "/material.json"}}
                                  for theme in ("ice", "lava")]}

    def test_explicit_cross_product_and_unique_input_binding(self):
        plan = plan_batch(self.recipe, self.root)
        self.assertEqual([j["id"] for j in plan["jobs"]], ["J000", "J001", "J002", "J003"])
        self.assertEqual(len(plan["inputs"]), 5)
        self.assertEqual(len(plan["materials"]), 2)
        self.assertEqual(plan, plan_batch(self.recipe, self.root))
        (self.root / "assets.blend").write_bytes(b"changed")
        self.assertNotEqual(plan["plan_id"], plan_batch(self.recipe, self.root)["plan_id"])

    def test_per_asset_materials_need_not_be_shared(self):
        self.recipe["themes"][0]["materials"]["blockb"] = "lava/material.json"
        plan = plan_batch(self.recipe, self.root)
        self.assertEqual([j["material"] for j in plan["jobs"][:2]], ["ice/material.json", "lava/material.json"])

    def test_incomplete_assignments_and_duplicate_ids_rejected(self):
        original = copy.deepcopy(self.recipe)
        for mode in ("missing", "extra", "duplicate", "bad_id", "unknown"):
            self.recipe = copy.deepcopy(original)
            if mode == "missing":
                del self.recipe["themes"][0]["materials"]["blocka"]
            elif mode == "extra":
                self.recipe["themes"][0]["materials"]["cat"] = "ice/material.json"
            elif mode == "duplicate":
                self.recipe["assets"][1]["id"] = "blocka"
            elif mode == "bad_id":
                self.recipe["themes"][0]["id"] = "../bad"
            else:
                self.recipe["unknown"] = 1
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                plan_batch(self.recipe, self.root)

    def test_path_escape_and_tampered_texture_rejected(self):
        for value in ("../assets.blend", "/assets.blend", "C:/assets.blend", "folder\\assets.blend"):
            recipe = copy.deepcopy(self.recipe)
            recipe["assets"][0]["source"] = value
            with self.assertRaises(ValueError):
                plan_batch(recipe, self.root)
        (self.root / "ice/base_color.png").write_bytes(png((1, 2, 3)))
        with self.assertRaises(ValueError):
            plan_batch(self.recipe, self.root)

    def test_output_budget_rejected_before_sources(self):
        self.recipe["assets"] = [{"id": f"asset{i}", "source": "assets.blend", "object": "BlockA"} for i in range(16)]
        self.recipe["themes"] *= 3
        for i, theme in enumerate(copy.deepcopy(self.recipe["themes"])):
            self.recipe["themes"][i] = {**theme, "id": f"theme{i}"}
        with self.assertRaises(ValueError):
            plan_batch(self.recipe, self.root)

    def test_plan_cli_no_overwrite(self):
        (self.root / "recipe.json").write_text(json.dumps(self.recipe))
        args = ["plan", str(self.root / "recipe.json"), "--source", str(self.root), "--destination", str(self.root / "plan.json")]
        with patch("sys.stdout", io.StringIO()):
            self.assertEqual(main(args), 0)
            with self.assertRaises(FileExistsError):
                main(args)

    def test_worker_failure_and_timeout_keep_honest_receipt(self):
        for index, failure in enumerate((WorkerFailure(code="publish_guard"), BudgetExpired())):
            destination = self.root / f"failed{index}"
            with patch("cryptonyan_asset_studio.theme_batch.run_process", side_effect=failure), self.assertRaises(type(failure)):
                build_batch(self.recipe, self.root, destination, blender=sys.executable)
            receipt = json.loads((destination / "batch.json").read_text())
            self.assertFalse(receipt["passed"])
            self.assertEqual([j["status"] for j in receipt["jobs"]], ["failed", "pending", "pending", "pending"])
            self.assertFalse(list(destination.glob(".themes-*")))
            with self.assertRaises(ValueError):
                validate_batch(destination)

    def test_snapshot_mutation_detected_before_launch(self):
        original = shutil.copyfile
        def changed(source, target):
            original(source, target)
            if Path(target).suffix == ".blend":
                Path(target).write_bytes(b"race")
        with patch("cryptonyan_asset_studio.theme_batch.shutil.copyfile", side_effect=changed), \
                patch("cryptonyan_asset_studio.theme_batch.run_process") as worker, self.assertRaises(ValueError):
            build_batch(self.recipe, self.root, self.root / "race", blender=sys.executable)
        worker.assert_not_called()
        self.assertFalse(json.loads((self.root / "race/batch.json").read_text())["passed"])


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class WorldBlenderTests(unittest.TestCase):
    setUp = ThemeTests.setUp

    def run_fixture(self, mode, path):
        run = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                              "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_fixture.py"),
                              "--", mode, str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("CRYPTONYAN_BLENDER_ASSERTIONS_PASSED", run.stdout)

    def test_real_layered_animated_preview_and_track_integrity(self):
        root = self.root / "world"
        result = build_bundle({**V2, "motion": {"probability": 1, "period_frames": 80}}, root, blender=BLENDER)
        self.assertTrue(result["built"])
        self.assertEqual(len(validate_bundle(root)["files"]), 10)
        self.run_fixture("verify_runner", root)
        tracks = json.loads((root / "motion-tracks.json").read_text())
        tracks["tracks"][0]["amplitude_cm"] += 1
        (root / "motion-tracks.json").write_text(json.dumps(tracks))
        with self.assertRaises(ValueError):
            validate_bundle(root)

    def test_real_two_assets_two_themes_publication_and_untouched_sources(self):
        self.run_fixture("create_theme_assets", self.root / "assets.blend")
        before = digest(self.root / "assets.blend")
        root = self.root / "variants"
        result = build_batch(self.recipe, self.root, root, blender=BLENDER)
        self.assertTrue(result["passed"])
        self.assertEqual(digest(self.root / "assets.blend"), before)
        self.run_fixture("verify_theme_batch", root)
        color_hashes = []
        for status in result["jobs"]:
            package = load_package(root / status["id"] / "manifest.json")
            self.assertEqual(package["schema"], "cryptonyan.publication/2")
            self.assertEqual(package["asset"]["triangles"], 12)
            color_hashes.append(package["textures"][0]["sha256"])
        self.assertEqual(color_hashes[0], color_hashes[1])
        self.assertNotEqual(color_hashes[0], color_hashes[2])
        with self.assertRaises(FileExistsError):
            build_batch(self.recipe, self.root, root, blender=BLENDER)
        path = root / "J000/asset.blend"
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaises(ValueError):
            validate_batch(root)

    def test_real_missing_target_fails_and_preserves_source(self):
        self.run_fixture("create_theme_assets", self.root / "assets.blend")
        before = digest(self.root / "assets.blend")
        self.recipe["assets"][0]["object"] = "Absent"
        with self.assertRaises(WorkerFailure):
            build_batch(self.recipe, self.root, self.root / "missing", blender=BLENDER)
        self.assertEqual(digest(self.root / "assets.blend"), before)
        receipt = json.loads((self.root / "missing/batch.json").read_text())
        self.assertEqual(receipt["jobs"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
