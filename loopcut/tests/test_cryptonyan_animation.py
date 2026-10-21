# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.animation_doctor import audit_trace, capture_blender, main, parse_capture, parse_settings
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.storage import digest

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


def settings(**changes):
    return {"root": "Origin", "bones": ["FootCustom"], "loop": True, "motion": "in_place",
            "contact_space": "unknown", "contacts": [], **changes}


def pose(x=0, q=None):
    return {"position": [x, 0, 0], "rotation": q or [1, 0, 0, 0]}


def trace():
    return {"schema": "cryptonyan.animation-trace/1", "clip": "Existing_Run",
            "samples": [{"time_s": t, "poses": {"Origin": pose(), "FootCustom": pose(1)}} for t in (0, .5, 1)]}


def codes(report):
    return {f["code"] for f in report["findings"]}


def capture_spec():
    return {"armature": "ExistingRig", "action": "Run", "start_frame": 1, "end_frame": 11,
            "step_frames": 1, "settings": settings(loop=False, motion="root_motion", contact_space="world",
                contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 1}])}


class AnimationTests(unittest.TestCase):
    def test_static_report_is_repeatable_and_does_not_mutate_input(self):
        source, config = trace(), settings()
        before = copy.deepcopy((source, config))
        result = audit_trace(source, config)
        self.assertEqual(result, audit_trace(source, config))
        self.assertEqual((source, config), before)
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["coverage"]["unreal_runtime"])

    def test_root_motion_is_removed_from_loop_pose_and_quaternion_sign_is_invariant(self):
        source = trace()
        source["samples"][-1]["poses"] = {"Origin": pose(3, [0, 0, 0, 1]),
                                           "FootCustom": pose(2, [0, 0, 0, -1])}
        report = audit_trace(source, settings(motion="root_motion"))
        self.assertNotIn("loop_position", codes(report))
        self.assertNotIn("loop_rotation", codes(report))
        self.assertEqual(report["root"]["net_displacement_m"], [3, 0, 0])

    def test_root_excursion_detects_out_and_back_not_only_endpoints(self):
        source = trace()
        source["samples"][1]["poses"]["Origin"] = pose(.2)
        report = audit_trace(source, settings())
        self.assertIn("root_drift", codes(report))
        self.assertEqual(report["root"]["travel_m"], .4)
        self.assertEqual(report["root"]["net_displacement_m"], [0, 0, 0])

    def test_loop_position_and_rotation_report_measured_thresholds(self):
        source = trace()
        source["samples"][-1]["poses"]["FootCustom"] = pose(1.1, [math.sqrt(.5), 0, 0, math.sqrt(.5)])
        report = audit_trace(source, settings())
        self.assertEqual(codes(report), {"loop_position", "loop_rotation"})
        self.assertAlmostEqual(report["bones"]["FootCustom"]["loop_rotation_deg"], 90)

    def test_nonloop_clip_does_not_report_pose_seam(self):
        source = trace()
        source["samples"][-1]["poses"]["FootCustom"] = pose(2)
        self.assertEqual(codes(audit_trace(source, settings(loop=False))), set())

    def test_speeds_and_nonuniform_interval_acceleration(self):
        source = trace()
        source["samples"][1]["time_s"] = .25
        source["samples"][1]["poses"]["FootCustom"] = pose(2)
        source["samples"][2]["poses"]["FootCustom"] = pose(5)
        report = audit_trace(source, settings(loop=False, thresholds={"speed_m_s": 3}))
        self.assertIn("speed_spike", codes(report))
        self.assertAlmostEqual(report["bones"]["FootCustom"]["max_acceleration_m_s2"], 0)
        self.assertEqual(report["bones"]["FootCustom"]["max_speed_m_s"], 4)

    def test_acceleration_and_angular_spikes(self):
        source = trace()
        source["samples"][1]["poses"]["FootCustom"] = pose(2, [0, 0, 0, 1])
        result = audit_trace(source, settings(thresholds={"acceleration_m_s2": 2, "angular_speed_deg_s": 300}))
        self.assertIn("acceleration_spike", codes(result))
        self.assertIn("angular_spike", codes(result))

    def test_contact_sliding_and_event_are_explicit_and_unapproved(self):
        source = trace()
        source["samples"][1]["poses"]["FootCustom"] = pose(1.2)
        config = settings(contact_space="world", contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 1}])
        report = audit_trace(source, config)
        self.assertIn("contact_sliding", codes(report))
        self.assertAlmostEqual(report["contacts"][0]["max_speed_m_s"], .4)
        event = report["effect_candidates"]["events"][0]
        self.assertFalse(event["approved"])
        self.assertEqual(event["origin"], "declared_contact_window")
        self.assertFalse(report["effect_candidates"]["applied_to_engine"])

    def test_unknown_world_trajectory_never_claims_no_sliding(self):
        config = settings(contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 1}])
        report = audit_trace(trace(), config)
        self.assertEqual(report["contacts"][0]["status"], "not_assessed_unknown_world_motion")
        self.assertIsNone(report["contacts"][0]["max_speed_m_s"])

    def test_unsampled_contact_boundaries_are_not_certified(self):
        config = settings(contact_space="world", contacts=[{"bone": "FootCustom", "start_s": .1, "end_s": 1}])
        self.assertEqual(audit_trace(trace(), config)["contacts"][0]["status"], "not_assessed_insufficient_samples")

    def test_stationary_declared_contact_is_within_threshold(self):
        config = settings(contact_space="world", contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 1}])
        self.assertEqual(audit_trace(trace(), config)["contacts"][0]["status"], "within_threshold")

    def test_invalid_times_quaternions_pose_coverage_and_numbers_are_rejected(self):
        for mutate in (
            lambda t: t["samples"][0].update(time_s=1),
            lambda t: t["samples"][1].update(time_s=0),
            lambda t: t["samples"][1].update(time_s=float("nan")),
            lambda t: t["samples"][1].update(time_s=10**1000),
            lambda t: t["samples"][1]["poses"]["Origin"].update(rotation=[0, 0, 0, 0]),
            lambda t: t["samples"][1]["poses"]["Origin"].update(position=[True, 0, 0]),
            lambda t: t["samples"][1]["poses"].pop("FootCustom"),
            lambda t: t.update(samples=t["samples"] * 1000),
        ):
            source = trace()
            mutate(source)
            with self.assertRaises(ValueError):
                audit_trace(source, settings())

    def test_settings_reject_typo_duplicate_root_and_overlapping_contacts(self):
        contact = {"bone": "FootCustom", "start_s": 0, "end_s": 1}
        for config in (settings(bones=["Origin"]), settings(bones=["FootCustom"]*2), settings(loop="true"),
                       settings(thresholds={"typo": 1}), settings(contacts=[contact, contact]),
                       settings(contacts=[{**contact, "bone": "Missing"}]), settings(typo=True)):
            with self.assertRaises(ValueError):
                parse_settings(config)

    def test_contact_beyond_clip_rejected(self):
        with self.assertRaises(ValueError):
            audit_trace(trace(), settings(contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 2}]))

    def test_two_samples_explicitly_exclude_acceleration(self):
        source = trace()
        del source["samples"][1]
        report = audit_trace(source, settings())
        self.assertFalse(report["coverage"]["acceleration"])
        self.assertIsNone(report["bones"]["Origin"]["max_acceleration_m_s2"])

    def test_identity_changes_with_source_or_settings(self):
        source = trace()
        baseline = audit_trace(source, settings())["identity"]
        self.assertNotEqual(baseline, audit_trace(source, settings(loop=False))["identity"])
        source["provenance"] = {"source_sha256": "changed"}
        self.assertNotEqual(baseline, audit_trace(source, settings())["identity"])

    def test_capture_window_and_budgets(self):
        for changes in ({"step_frames": 0}, {"end_frame": 1}, {"end_frame": 5000},
                        {"step_frames": 3}, {"start_frame": True}, {"action_slot": ""}):
            with self.assertRaises(ValueError):
                parse_capture({**capture_spec(), **changes})

    def test_cli_warning_exit_and_no_overwrite_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = trace()
            source["samples"][-1]["poses"]["FootCustom"] = pose(2)
            (folder / "trace.json").write_text(json.dumps(source), encoding="utf-8")
            (folder / "settings.json").write_text(json.dumps(settings()), encoding="utf-8")
            args = ["audit", str(folder / "trace.json"), str(folder / "settings.json"), "--output", str(folder / "result")]
            self.assertEqual(main(args), 1)
            self.assertTrue((folder / "result/audit.json").is_file())
            (folder / "trace.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                main([*args[:-1], str(folder / "invalid")])
            self.assertFalse((folder / "invalid").exists())

    def test_cli_writes_report_events_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "trace.json").write_text(json.dumps(trace()), encoding="utf-8")
            (folder / "settings.json").write_text(json.dumps(settings()), encoding="utf-8")
            command = [sys.executable, "-m", "cryptonyan_asset_studio.animation_doctor", "audit",
                       str(folder / "trace.json"), str(folder / "settings.json"), "--output", str(folder / "result")]
            env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "no_findings_within_scope")
            audit = json.loads((folder / "result/audit.json").read_text())
            events = json.loads((folder / "result/events.json").read_text())
            self.assertEqual(events["audit_identity"], audit["identity"])
            before = (folder / "result/audit.json").read_bytes()
            result = subprocess.run(command, env=env, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((folder / "result/audit.json").read_bytes(), before)


@unittest.skipUnless(BLENDER, "Blender unavailable; set LOOPCUT_BLENDER for actual evaluated-rig tests")
class BlenderAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.source = cls.folder / "existing.blend"
        result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                                 "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_animation_fixture.py"),
                                 "--", str(cls.source)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def test_actual_action_constraints_units_report_and_original_preservation(self):
        before = digest(self.source)
        report = capture_blender(self.source, capture_spec(), self.folder / "good", BLENDER)
        self.assertEqual(digest(self.source), before)
        self.assertEqual(report["sample_count"], 11)
        self.assertAlmostEqual(report["root"]["net_displacement_m"][0], 1, places=5)
        self.assertAlmostEqual(report["contacts"][0]["max_speed_m_s"], .4, places=5)
        self.assertIn("contact_sliding", codes(report))
        sampled = json.loads((self.folder / "good/trace.json").read_text())
        self.assertEqual(sampled["provenance"]["source_sha256"], before)
        self.assertIn("COPY_LOCATION", sampled["rig"]["selected_bones"][1]["constraints"])
        self.assertAlmostEqual(sampled["samples"][-1]["poses"]["FootCustom"]["position"][0], .4, places=5)
        self.assertEqual(list((self.folder / "good").glob("*.blend")), [self.folder / "good/source.blend"])

    def test_missing_existing_bone_fails_without_report_or_source_write(self):
        spec = capture_spec()
        spec["settings"] = settings(bones=["Missing"])
        before = digest(self.source)
        with self.assertRaises(WorkerFailure) as error:
            capture_blender(self.source, spec, self.folder / "missing", BLENDER)
        self.assertEqual(error.exception.code, "animation_mapping")
        self.assertEqual(digest(self.source), before)
        self.assertFalse((self.folder / "missing/audit.json").exists())

    def test_wrong_action_range_is_rejected(self):
        spec = {**capture_spec(), "end_frame": 12}
        with self.assertRaises(WorkerFailure) as error:
            capture_blender(self.source, spec, self.folder / "range", BLENDER)
        self.assertEqual(error.exception.code, "animation_action")


if __name__ == "__main__":
    unittest.main()
