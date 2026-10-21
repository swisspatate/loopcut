# SPDX-License-Identifier: GPL-3.0-or-later
"""Runner model tests plus explicitly optional real Blender kit integration."""
import copy
import csv
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
from cryptonyan_asset_studio.procedural_level_builder import (
    DEFAULT_RECIPE, normalize_recipe, build_layout, validate_layout, analyze_layout, points_csv, preview_svg, scan_seeds, _transition)
from cryptonyan_asset_studio.runner_kit import build_bundle, validate_bundle, main
from cryptonyan_asset_studio.storage import digest
from cryptonyan_asset_studio.publication import load_package


class RunnerTests(unittest.TestCase):
    def test_recipe_defaults_are_copied(self):
        value = normalize_recipe({})
        value["platform"]["width_m"] = 99
        self.assertEqual(DEFAULT_RECIPE["platform"]["width_m"], 3)
        self.assertEqual(normalize_recipe({}), DEFAULT_RECIPE)

    def test_invalid_parameters(self):
        for recipe in ({"rows": True}, {"rows": 33}, {"rows": 1}, {"seed": -1}, {"seed": 2**32},
                       {"schema": "unknown"}, {"unknown": 1}, {"platform": {"bad": 2}},
                       {"platform": {"width_m": float("nan")}}, {"movement": {"speed_m_s": 0}},
                       {"movement": {"capsule_radius_m": True}}, {"gap_choices_m": []},
                       {"gap_choices_m": [1, 1]}, {"gap_choices_m": [float("inf")]},
                       {"side_lane_probability": -0.1}):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                build_layout(recipe)

    def test_seed_determinism_and_variation(self):
        a = build_layout({"seed": 42})
        self.assertEqual(a, build_layout({"seed": 42}))
        self.assertNotEqual(a["placements"], build_layout({"seed": 43})["placements"])
        self.assertEqual(validate_layout(json.loads(json.dumps(a))), a)

    def test_fixed_layout_digest_across_python_versions(self):
        # A stable fixture catches changes to draw order, axes and serialization.
        self.assertEqual(build_layout({"seed": 42})["layout_id"], "a8cbb35c8c4d18645ac0e201a3816b33435590c4cf510f51142b4deb58cb40fc")

    def test_centre_lane_and_bounded_density(self):
        low = build_layout({"rows": 32, "side_lane_probability": 0})
        high = build_layout({"rows": 32, "side_lane_probability": 1})
        self.assertEqual(len(low["placements"]), 32)
        self.assertEqual(len(high["placements"]), 96)
        self.assertTrue(all(p["lane"] == 0 for p in low["placements"]))

    def test_positions_pivot_and_connection_points(self):
        layout = build_layout({"rows": 3, "gap_choices_m": [2], "side_lane_probability": 0})
        self.assertEqual([p["origin_m"][0] for p in layout["placements"]], [0, 14, 28])
        self.assertEqual(layout["module"]["entry_m"], [0, 0, 0])
        self.assertEqual(layout["module"]["exit_m"], [12, 0, 0])

    def test_tampered_positions_and_boolean_alias(self):
        for mutation in ("position", "row", "id", "unknown"):
            layout = build_layout({})
            if mutation == "position":
                layout["placements"][0]["origin_m"][0] = 5
            elif mutation == "row":
                layout["placements"][0]["row"] = False
            elif mutation == "id":
                layout["layout_id"] = "a" * 64
            else:
                layout["unexpected"] = 1
            with self.assertRaises(ValueError):
                analyze_layout(layout)

    def test_contiguous_route_needs_no_jumps(self):
        analysis = analyze_layout(build_layout({"gap_choices_m": [0], "side_lane_probability": 0}))
        self.assertTrue(analysis["model_passed"])
        self.assertEqual({e["kind"] for e in analysis["witness"]}, {"run"})
        self.assertFalse(analysis["engine_validated"])

    def test_ballistic_window_and_landing_bounds(self):
        layout = build_layout({"gap_choices_m": [2], "side_lane_probability": 0})
        analysis = analyze_layout(layout)
        self.assertTrue(analysis["model_passed"])
        speed = layout["recipe"]["movement"]["speed_m_s"]
        for edge in analysis["witness"]:
            self.assertEqual(edge["kind"], "jump")
            self.assertAlmostEqual(edge["flight_seconds"], 10/9.81)
            lo, hi = edge["launch_interval_x_m"]
            self.assertGreaterEqual((hi-lo)/speed + 1e-12, 0.1)
            self.assertAlmostEqual(edge["landing_x_m"], lo + speed * edge["flight_seconds"])

    def test_unreachable_gap_reports_failure_seed(self):
        analysis = analyze_layout(build_layout({"seed": 77, "gap_choices_m": [20], "side_lane_probability": 0}))
        self.assertFalse(analysis["model_passed"])
        self.assertEqual(analysis["first_blocked_row"], 1)
        self.assertEqual(analysis["failure_seeds"], [77])
        self.assertEqual(analysis["witness"], [])

    def test_capsule_clearance_rejects_narrow_platform(self):
        analysis = analyze_layout(build_layout({"platform": {"width_m": 1}, "movement": {"capsule_radius_m": 0.8}}))
        self.assertFalse(analysis["model_passed"])
        self.assertEqual(analysis["first_blocked_row"], 0)

    def test_lane_change_time_blocks_diagonal_edges(self):
        layout = build_layout({"side_lane_probability": 1, "movement": {"lane_change_seconds": 3}})
        analysis = analyze_layout(layout)
        self.assertTrue(analysis["model_passed"])
        lane = {p["id"]: p["lane"] for p in layout["placements"]}
        self.assertTrue(all(lane[e["from"]] == lane[e["to"]] for e in analysis["accepted_edges"]))

    def test_recovery_distance_prevents_false_pairwise_connectivity(self):
        recipe = normalize_recipe({"platform": {"length_m": 4}, "gap_choices_m": [1], "rows": 3,
                                   "side_lane_probability": 0, "movement": {"speed_m_s": 5,
                                   "jump_speed_m_s": 6, "gravity_m_s2": 10, "recovery_seconds": 0.1}})
        layout = build_layout(recipe)
        a, b, c = layout["placements"]
        # Each isolated pair permits a jump, but the first landing arrives too late
        # on B to launch a six-metre jump into C with the required launch window.
        self.assertIsNotNone(_transition(a, b, 0.5, recipe))
        self.assertIsNotNone(_transition(b, c, 5.5, recipe))
        analysis = analyze_layout(layout)
        self.assertFalse(analysis["model_passed"])
        self.assertEqual(analysis["first_blocked_row"], 2)

    def test_long_recovery_and_launch_window_can_block_route(self):
        analysis = analyze_layout(build_layout({"gap_choices_m": [2], "movement": {"recovery_seconds": 2}}))
        self.assertFalse(analysis["model_passed"])

    def test_csv_axis_units_and_generated_names(self):
        layout = build_layout({"rows": 2, "side_lane_probability": 1})
        rows = list(csv.DictReader(io.StringIO(points_csv(layout))))
        self.assertEqual(len(rows), 6)
        self.assertEqual(float(rows[0]["y_cm"]), 300)
        self.assertEqual(float(rows[0]["exit_x_cm"]), 1200)
        self.assertEqual(float(rows[0]["yaw_deg"]), 0)
        self.assertTrue(all(r["id"].startswith("R") and r["module"] == "RunnerPlatform" for r in rows))

    def test_multiple_seeds_have_consistent_witnesses(self):
        for seed in range(50):
            layout = build_layout({"seed": seed})
            report = analyze_layout(layout)
            self.assertTrue(report["model_passed"], seed)
            cursor, arrival = report["start"], 0.5
            placements = {p["id"]: p for p in layout["placements"]}
            for edge in report["witness"]:
                self.assertEqual(edge["from"], cursor)
                self.assertEqual(edge, _transition(placements[cursor], placements[edge["to"]], arrival, layout["recipe"]))
                cursor, arrival = edge["to"], edge["landing_x_m"]

    def test_plan_writes_diagnostics_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plan"
            result = build_bundle({}, root)
            self.assertFalse(result["built"])
            self.assertTrue(result["model_passed"])
            self.assertEqual(set(p.name for p in root.iterdir()), {"layout.json", "analysis.json", "pcg-points.csv", "preview.svg"})
            with self.assertRaises(FileExistsError):
                build_bundle({}, root)

    def test_failed_preflight_does_not_launch_blender(self):
        with tempfile.TemporaryDirectory() as temp, patch("cryptonyan_asset_studio.runner_kit.run_process") as process:
            result = build_bundle({"gap_choices_m": [20]}, Path(temp) / "failed", blender="missing")
            self.assertFalse(result["model_passed"])
            self.assertFalse(result["built"])
            process.assert_not_called()

    def test_cli_failing_plan_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "recipe.json").write_text(json.dumps({"gap_choices_m": [20]}))
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(main(["plan", str(root / "recipe.json"), "--destination", str(root / "out")]), 1)

    def test_seed_scan_retains_reproducible_failures(self):
        report = scan_seeds({"rows": 2, "gap_choices_m": [0, 20]}, count=32)
        self.assertTrue(report["failure_seeds"])
        self.assertLess(len(report["failure_seeds"]), 32)
        for seed in report["failure_seeds"]:
            self.assertFalse(analyze_layout(build_layout({**report["recipe"], "seed": seed}))["model_passed"])
        for first, count in ((0, 0), (0, 257), (2**32-1, 2), (True, 5)):
            with self.assertRaises(ValueError):
                scan_seeds({}, first_seed=first, count=count)

    def test_svg_is_well_formed_and_has_one_platform_per_placement(self):
        import xml.etree.ElementTree as ET
        layout = build_layout({})
        root = ET.fromstring(preview_svg(layout))
        self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}rect")), len(layout["placements"]) + 1)
        self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}line")), layout["recipe"]["rows"] - 1)
        self.assertNotIn("script", preview_svg(layout))

    def test_scan_cli_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "recipe.json").write_text("{}")
            args = ["scan", str(root / "recipe.json"), "--count", "4", "--report", str(root / "scan.json")]
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(main(args), 0)
            before = digest(root / "scan.json")
            with self.assertRaises(FileExistsError):
                main(args)
            self.assertEqual(digest(root / "scan.json"), before)


BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class RunnerBlenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_real_build_preview_glb_and_integrity(self):
        bundle = self.root / "kit"
        result = build_bundle({"rows": 4}, bundle, blender=BLENDER)
        self.assertTrue(result["built"])
        catalog = validate_bundle(bundle)
        self.assertEqual(len(catalog["files"]), 9)
        package = load_package(bundle / "publication/manifest.json")
        self.assertEqual(package["asset"]["triangles"], 12)
        before = digest(bundle / "modules.blend")
        run = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                              "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_fixture.py"),
                              "--", "verify_runner", str(bundle)], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("CRYPTONYAN_BLENDER_ASSERTIONS_PASSED", run.stdout)
        self.assertEqual(digest(bundle / "modules.blend"), before)
        for relative in ("pcg-points.csv", "preview.svg", "modules.blend", "publication/" + package["asset"]["file"]):
            path = bundle / relative
            data = path.read_bytes()
            path.write_bytes(data + (b"x" * (2 * 1024 * 1024) if relative == "preview.svg" else b"tampered"))
            with self.subTest(path=relative), self.assertRaises(ValueError):
                validate_bundle(bundle)
            path.write_bytes(data)

    def test_nondefault_module_dimensions_and_repeat_build(self):
        recipe = {"seed": 19, "rows": 3, "platform": {"width_m": 2.5, "length_m": 16, "thickness_m": 0.3}}
        a, b = self.root / "a", self.root / "b"
        build_bundle(recipe, a, blender=BLENDER)
        build_bundle(recipe, b, blender=BLENDER)
        self.assertEqual((a / "layout.json").read_bytes(), (b / "layout.json").read_bytes())
        self.assertEqual((a / "analysis.json").read_bytes(), (b / "analysis.json").read_bytes())
        self.assertEqual(validate_bundle(a)["module"], validate_bundle(b)["module"])
        before = digest(a / "modules.blend")
        with self.assertRaises(FileExistsError):
            build_bundle(recipe, a, blender=BLENDER)
        self.assertEqual(digest(a / "modules.blend"), before)


if __name__ == "__main__":
    unittest.main()
