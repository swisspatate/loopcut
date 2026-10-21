# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry diagnostics, immutable build inputs and a real mixed-period Blender scene."""
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
from cryptonyan_asset_studio.procedural_level_builder import _hash
from cryptonyan_asset_studio.world_assembly import plan_world
from cryptonyan_asset_studio.world_geometry import analyze_world, actor_bounds
from cryptonyan_asset_studio.world_preview import build_preview, validate_preview, preview_window, preview_placement, main
from cryptonyan_asset_studio.runner_kit import build_bundle
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.executors import WorkerFailure, BudgetExpired
from test_cryptonyan_assembly import WorldFixture, RECIPE

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


def reseal(plan):
    plan["world_id"] = _hash({k: v for k, v in plan.items() if k != "world_id"})
    return plan


class GeometryTests(WorldFixture):
    def setUp(self):
        super().setUp()
        self.plan = plan_world(self.recipe, self.inputs)

    def test_flush_zones_and_touching_lanes_are_not_overlaps(self):
        before = copy.deepcopy(self.plan)
        report = analyze_world(self.plan)
        self.assertTrue(report["geometry_passed"])
        self.assertEqual(report["counts"]["error"], 0)
        self.assertFalse(report["engine_validated"])
        self.assertFalse(report["controller_validated"])
        self.assertEqual(before, self.plan)

    def test_static_overlap_has_pair_and_penetration(self):
        a, b = self.plan["actors"][:2]
        a["origin_cm"] = list(b["origin_cm"])
        report = analyze_world(reseal(self.plan))
        collision = next(f for f in report["findings"] if f["code"] == "static_overlap")
        self.assertEqual(collision["actors"], [a["id"], b["id"]])
        self.assertTrue(all(x > 0 for x in collision["penetration_cm"]))
        self.assertFalse(report["geometry_passed"])

    def test_swept_box_overlap_is_only_a_potential_collision(self):
        moving = next(a for a in self.plan["actors"] if a["amplitude_cm"])
        static = next(a for a in self.plan["actors"] if a["id"] == "Z00_R01_L1")
        moving["origin_cm"] = [*static["origin_cm"][:2], 60]
        moving["amplitude_cm"] = 100
        report = analyze_world(reseal(self.plan))
        self.assertTrue(report["geometry_passed"])
        hit = next(f for f in report["findings"] if f["code"] == "potential_motion_overlap")
        self.assertTrue(hit["swept"])
        self.assertEqual(hit["severity"], "warning")
        self.assertFalse(report["dynamics_validated"])

    def test_decoration_overlap_is_visual_warning(self):
        a, b = [a for a in self.plan["actors"] if a["kind"] == "decoration"][:2]
        b["origin_cm"] = list(a["origin_cm"])
        b["scale"] = list(a["scale"])
        report = analyze_world(reseal(self.plan))
        self.assertTrue(report["geometry_passed"])
        self.assertTrue(any(f["code"] == "visual_overlap" for f in report["findings"]))

    def test_connector_corruption_is_reported(self):
        for key, value in (("position_cm", [0, 0, 0]), ("width_cm", 2),
                           ("opposed_normals", [[1, 0, 0], [1, 0, 0]]), ("to_zone", "Z00")):
            plan = copy.deepcopy(self.plan)
            plan["connections"][0][key] = value
            self.assertIn("connection_mismatch", [f["code"] for f in analyze_world(reseal(plan))["findings"]])
        self.plan["connections"] = []
        self.assertFalse(analyze_world(reseal(self.plan))["geometry_passed"])

    def test_socket_requires_real_static_centre_geometry(self):
        actor = next(a for a in self.plan["actors"] if a["id"] == "Z01_R00_L1")
        actor["period_seconds"] = 4
        for key, value in (("origin_cm", [0, 0, 0]), ("scale", [1, .5, 1]), ("amplitude_cm", 10)):
            saved = actor[key]
            actor[key] = value
            report = analyze_world(reseal(self.plan))
            self.assertIn("socket_geometry_mismatch", [f["code"] for f in report["findings"]])
            actor[key] = saved

    def test_plan_tampering_bad_numbers_and_duplicate_ids_rejected(self):
        self.plan["actors"][0]["origin_cm"][0] += 1
        with self.assertRaises(ValueError):
            analyze_world(self.plan)
        reseal(self.plan)
        for field, value in (("scale", [0, 1, 1]), ("origin_cm", [True, 0, 0]),
                             ("period_seconds", 0), ("collision", 1), ("biome", "unknown")):
            plan = copy.deepcopy(self.plan)
            plan["actors"][0][field] = value
            with self.assertRaises(ValueError):
                analyze_world(reseal(plan))
        self.plan["actors"].append(copy.deepcopy(self.plan["actors"][0]))
        with self.assertRaises(ValueError):
            analyze_world(reseal(self.plan))

    def test_findings_are_bounded_without_losing_error_counts(self):
        for item in self.plan["actors"]:
            item["origin_cm"] = [0, 0, 0]
        with patch("cryptonyan_asset_studio.world_geometry.MAX_FINDINGS", 2):
            report = analyze_world(reseal(self.plan))
        self.assertEqual(len(report["findings"]), 2)
        self.assertTrue(report["findings_truncated"])
        self.assertGreater(report["counts"]["error"], 2)

    def test_coordinate_conversion_and_shared_preview_window(self):
        item = self.plan["actors"][0]
        item["origin_cm"] = [100, -200, 300]
        self.assertEqual(preview_placement(item)["origin_m"], [1, 2, 3])
        self.assertEqual(actor_bounds(self.plan, item)[0][:2], [100, -350])
        moving = [a for a in self.plan["actors"] if a["amplitude_cm"]]
        moving[0]["period_seconds"] = 80/30
        moving[1]["period_seconds"] = 140/30
        window = preview_window(self.plan)
        self.assertEqual(window["frame_end"], 281)
        self.assertFalse(window["whole_world_loop"])


class PreviewBuildTests(WorldFixture):
    def test_plan_cli_new_output_and_no_overwrite(self):
        recipe = self.root / "recipe.json"
        write_json(recipe, self.recipe)
        destination = self.root / "preview"
        args = ["plan", str(recipe), "--source", str(self.inputs), "--destination", str(destination)]
        with patch("sys.stdout", io.StringIO()):
            self.assertEqual(main(args), 0)
            with self.assertRaises(FileExistsError):
                main(args)
        self.assertTrue(json.loads((destination / "geometry.json").read_text())["geometry_passed"])
        self.assertFalse((destination / "preview.json").exists())

    def test_preflight_failure_does_not_launch_blender(self):
        plan = plan_world(self.recipe, self.inputs)
        plan["actors"][0]["origin_cm"] = list(plan["actors"][1]["origin_cm"])
        with patch("cryptonyan_asset_studio.world_preview.plan_world", return_value=reseal(plan)), \
                patch("cryptonyan_asset_studio.world_preview.run_process") as worker:
            result = build_preview(self.recipe, self.inputs, self.root / "bad", blender=sys.executable)
        worker.assert_not_called()
        self.assertFalse(result["built"])
        self.assertFalse(result["geometry_passed"])

    def test_invalid_destination_timeout_and_executable_leave_no_output(self):
        with self.assertRaises(ValueError):
            build_preview(self.recipe, self.inputs, self.inputs / "bad")
        for timeout in (True, 0, 3601, float("nan")):
            with self.assertRaises(ValueError):
                build_preview(self.recipe, self.inputs, self.root / "bad", timeout_seconds=timeout)
        with self.assertRaises(FileNotFoundError):
            build_preview(self.recipe, self.inputs, self.root / "bad", blender=self.root / "missing")
        self.assertFalse((self.root / "bad").exists())

    def test_failure_and_timeout_do_not_certify_partial_build(self):
        for name in ("short", "long"):
            (self.inputs / name / "modules.blend").write_bytes(b"fixture")
        for index, error in enumerate((WorkerFailure(code="invalid_asset"), BudgetExpired())):
            destination = self.root / str(index)
            with patch("cryptonyan_asset_studio.world_preview.run_process", side_effect=error), self.assertRaises(type(error)):
                build_preview(self.recipe, self.inputs, destination, blender=sys.executable)
            self.assertFalse((destination / "preview.json").exists())
            self.assertFalse(list(destination.glob(".world-*")))

    def test_snapshot_race_is_rejected_before_worker(self):
        for name in ("short", "long"):
            (self.inputs / name / "modules.blend").write_bytes(b"fixture")
        original = shutil.copyfile
        def changed(source, target):
            original(source, target)
            Path(target).write_bytes(b"changed")
        with patch("cryptonyan_asset_studio.world_preview.shutil.copyfile", side_effect=changed), \
                patch("cryptonyan_asset_studio.world_preview.run_process") as worker, self.assertRaises(ValueError):
            build_preview(self.recipe, self.inputs, self.root / "race", blender=sys.executable)
        worker.assert_not_called()


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER")
class PreviewBlenderTests(unittest.TestCase):
    def test_real_mixed_period_world_shared_meshes_materials_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            for name, period in (("short", 80), ("long", 140)):
                build_bundle({"schema": "cryptonyan.runner-recipe/2", "rows": 3, "side_lane_probability": 1,
                              "motion": {"probability": 1, "period_frames": period}}, inputs / name, blender=BLENDER)
            before = {p.relative_to(inputs): digest(p) for p in inputs.rglob("*") if p.is_file()}
            recipe = copy.deepcopy(RECIPE)
            # Same mesh, different biome as well as a second mesh with another period.
            recipe["zones"].append({"kit": "short", "biome": "lava", "decorations": 2})
            destination = root / "preview"
            result = build_preview(recipe, inputs, destination, blender=BLENDER)
            self.assertTrue(result["built"])
            catalog = validate_preview(destination, source_root=inputs)
            self.assertEqual(catalog["window"]["frame_end"], 281)
            self.assertFalse(catalog["window"]["whole_world_loop"])
            run = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_preview_fixture.py"),
                "--", str(destination)], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertIn("CRYPTONYAN_WORLD_PREVIEW_PASSED", run.stdout)
            self.assertEqual(before, {p.relative_to(inputs): digest(p) for p in inputs.rglob("*") if p.is_file()})
            with self.assertRaises(FileExistsError):
                build_preview(recipe, inputs, destination, blender=BLENDER)
            for name in ("world-preview.blend", "geometry.json", "world-plan.json"):
                path = destination / name
                original = path.read_bytes()
                path.write_bytes(original+b"tampered")
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    validate_preview(destination)
                path.write_bytes(original)
            altered = copy.deepcopy(catalog)
            altered["sources"]["M00"]["sha256"] = "0"*64
            write_json(destination / "preview.json", altered)
            with self.assertRaises(ValueError):
                validate_preview(destination, source_root=inputs)
            write_json(destination / "preview.json", catalog)
            shutil.rmtree(inputs)
            self.assertEqual(catalog, validate_preview(destination))


if __name__ == "__main__":
    unittest.main()
