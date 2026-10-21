# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict protocol tests; an Unreal installation remains necessary for engine acceptance."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.animation_doctor import audit_trace, relative
from cryptonyan_asset_studio.unreal_animation import capture, normalized_pose, specification
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.unreal_review import ReviewError

ANIM, SKELETON = "/Game/Run.Run", "/Game/Skeleton.Skeleton"


def spec(**changes):
    return {"animation": ANIM, "sample_count": 3, "settings": {"root": "Origin", "bones": ["Paw"],
            "loop": True, "motion": "root_motion", "contact_space": "unknown",
            "contacts": [{"bone": "Paw", "start_s": 0, "end_s": 1}]}, **changes}


def transform(p=(0, 0, 0), q=(0, 0, 0, 1), scale=(1, 1, 1)):
    return NS(translation=NS(**dict(zip("xyz", p))), rotation=NS(**dict(zip("xyzw", q))),
              scale3d=NS(**dict(zip("xyz", scale))))


class Obj:
    def __init__(self, path, kind, **props):
        self.path, self.kind, self.props = path, kind, props

    def get_path_name(self):
        return self.path

    def get_class(self):
        return NS(get_name=lambda: self.kind)

    def get_editor_property(self, key):
        return self.props[key]


class Editor:
    def __init__(self, project):
        self.project, self.dirty, self.times, self.options = project, [], [], []
        self.SystemLibrary = NS(get_engine_version=lambda: "5.8.3")
        self.Paths = NS(project_dir=lambda: str(project))
        self.EditorLoadingAndSavingUtils = NS(get_dirty_content_packages=lambda: self.dirty)
        self.AdditiveAnimationType = NS(AAT_NONE="none")
        self.AnimDataEvalType = NS(RAW="raw")
        self.AnimPoseSpaces = NS(WORLD="component")
        self.AnimPoseEvaluationOptions = self.evaluation_options
        self.AnimPoseExtensions = NS(get_anim_pose_at_time=self.pose, is_valid=lambda p: True,
            get_bone_names=lambda p: ["Origin", "Paw"], get_bone_pose=self.bone)
        self.skeleton = Obj(SKELETON, "Skeleton")
        self.animation = Obj(ANIM, "AnimSequence", skeleton=self.skeleton, sequence_length=1,
                             rate_scale=2, additive_anim_type="none", parent_asset=None)
        self.assets = {ANIM: self.animation, SKELETON: self.skeleton}

    def load_asset(self, path):
        return self.assets.get(path)

    def evaluation_options(self, *, evaluation_type, should_retarget, extract_root_motion,
                           incorporate_root_motion_into_pose, retrieve_additive_as_full_pose, evaluate_curves):
        assert (evaluation_type, should_retarget, extract_root_motion, incorporate_root_motion_into_pose,
                retrieve_additive_as_full_pose, evaluate_curves) == ("raw", False, False, True, False, False)
        self.options.append("explicit_raw_options")
        return self.options[-1]

    def pose(self, seq, t, options):
        assert seq is self.animation and options == "explicit_raw_options"
        self.times.append(t)
        return t

    def bone(self, pose, name, space):
        assert space == "component"
        # Root rotates 90 degrees around Z, moving 1m; paw's local X remains 1m.
        yaw = pose * math.pi/2
        p = (100*pose, 20, 10)
        if name == "Paw":
            p = (p[0]+100*math.cos(yaw), p[1]+100*math.sin(yaw), p[2])
        return transform(p, (0, 0, math.sin(yaw/2), math.cos(yaw/2)))


class UnrealAnimationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.project = self.folder / "game"
        (self.project / "Content").mkdir(parents=True)
        write_json(self.project / "Game.uproject", {"FileVersion": 3, "EngineAssociation": "5.8"})
        for name in ("Run.uasset", "Run.uexp", "Skeleton.uasset"):
            (self.project / "Content" / name).write_bytes(b"saved asset bytes")
        self.u, self.output = Editor(self.project), self.folder / "capture"

    def capture(self, request=None):
        return capture(request or spec(), self.output, unreal_module=self.u)

    def test_component_sampling_units_rotation_source_hashes_and_no_contact_certification(self):
        before = {p.name: digest(p) for p in self.project.rglob("*") if p.is_file()}
        config = spec()
        original = copy.deepcopy(config)
        report = self.capture(config)
        self.assertEqual(config, original)
        self.assertEqual(self.u.times, [0, .5, 1])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["root"]["net_displacement_m"], [1, 0, 0])
        self.assertAlmostEqual(report["bones"]["Paw"]["loop_position_m"], 0)
        self.assertFalse(report["coverage"]["unreal_runtime"])
        self.assertEqual(report["bones"]["Origin"]["space"], "component")
        self.assertEqual(report["contacts"][0]["status"], "not_assessed_unknown_world_motion")
        data = json.loads((self.output / "trace.json").read_text())
        last = data["samples"][-1]["poses"]
        self.assertEqual(last["Origin"]["position"], [1, -.2, .1])
        local = relative(last["Paw"], last["Origin"])
        for actual, expected in zip(local["position"], [1, 0, 0]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(data["provenance"]["source"]["rate_scale"], 2)
        self.assertFalse(data["provenance"]["rate_scale_applied"])
        self.assertEqual(len(data["provenance"]["source"]["files"]), 2)
        events = json.loads((self.output / "events.json").read_text())
        self.assertEqual(events["audit_identity"], report["identity"])
        self.assertTrue(all(not e["approved"] for e in events["events"]))
        self.assertEqual(before, {p.name: digest(p) for p in self.project.rglob("*") if p.is_file()})
        self.assertFalse(json.loads((self.output / "capture.json").read_text())["assets_saved"])
        settings = {**config["settings"], "contact_space": "world"}
        with self.assertRaisesRegex(ValueError, "Component-space"):
            audit_trace(data, settings)

    def test_reflection_handles_all_quaternion_axes_and_sign(self):
        q = [.5, .5, .5, .5]
        result = normalized_pose(transform((100, 200, 300), q))
        self.assertEqual(result["position"], [1, -2, 3])
        self.assertEqual(result["rotation"], [.5, -.5, .5, -.5])
        neg = normalized_pose(transform(q=[-v for v in q]))
        self.assertEqual(neg["rotation"], [-v for v in result["rotation"]])

    def test_scaled_reflected_singular_nonfinite_and_invalid_rotation_rejected(self):
        for t in (transform(scale=(1, 2, 1)), transform(scale=(-1, 1, 1)), transform(scale=(0, 1, 1)),
                  transform(p=(float("nan"), 0, 0)), transform(q=(0, 0, 0, 0))):
            with self.subTest(transform=t), self.assertRaises(ValueError):
                normalized_pose(t)

    def test_world_contact_claim_rejected_before_loading_editor(self):
        request = spec()
        request["settings"]["contact_space"] = "world"
        with self.assertRaisesRegex(ValueError, "trajectory"):
            capture(request, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_bone_does_not_silently_sample_identity(self):
        self.u.AnimPoseExtensions.get_bone_names = lambda p: ["Origin"]
        with self.assertRaisesRegex(ValueError, "Mapped bones"):
            self.capture()
        self.assertFalse((self.output / "audit.json").exists())
        self.assertEqual(json.loads((self.output / "capture.json").read_text())["status"], "failed")

    def test_pose_validity_and_changing_bone_sets_are_checked(self):
        self.u.AnimPoseExtensions.is_valid = lambda p: False
        with self.assertRaisesRegex(ValueError, "invalid animation"):
            self.capture()
        self.output = self.folder / "changed_names"
        self.u.AnimPoseExtensions.is_valid = lambda p: True
        self.u.AnimPoseExtensions.get_bone_names = lambda p: ["Origin", "Paw"] + (["Extra"] if p else [])
        with self.assertRaisesRegex(ValueError, "mapping changed"):
            self.capture()

    def test_source_and_skeleton_sidecar_drift_discard_capture(self):
        for filename in ("Run.uasset", "Run.uexp", "Skeleton.uasset", "Skeleton.ubulk"):
            self.output = self.folder / filename.replace(".", "_")
            self.u = Editor(self.project)
            original = self.u.bone
            def changed(pose, name, space):
                (self.project / "Content" / filename).write_bytes(b"changed " + str(pose).encode())
                return original(pose, name, space)
            self.u.AnimPoseExtensions.get_bone_pose = changed
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "changed during capture"):
                self.capture()
            self.assertFalse((self.output / "trace.json").exists())

    def test_dirty_content_before_and_during_capture_rejected(self):
        self.u.dirty.append("unsaved")
        with self.assertRaisesRegex(ValueError, "Save or discard"):
            self.capture()
        self.output = self.folder / "dirty_later"
        self.u.dirty.clear()
        original = self.u.bone
        def dirty(pose, name, space):
            self.u.dirty.append("changed")
            return original(pose, name, space)
        self.u.AnimPoseExtensions.get_bone_pose = dirty
        with self.assertRaisesRegex(ValueError, "Save or discard"):
            self.capture()
        self.assertFalse((self.output / "audit.json").exists())

    def test_additive_inherited_and_wrong_asset_classes_rejected(self):
        for change in ({"additive_anim_type": "local"}, {"parent_asset": object()}, {"skeleton": None}):
            self.u = Editor(self.project)
            self.output = self.folder / next(iter(change))
            self.u.animation.props.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.capture()
        self.output = self.folder / "wrong_class"
        self.u.animation.kind = "AnimMontage"
        with self.assertRaisesRegex(ValueError, "AnimSequence"):
            self.capture()

    def test_version_project_outputs_and_existing_directory_guards(self):
        self.output = self.project / "capture"
        with self.assertRaises(ReviewError):
            self.capture()
        self.assertFalse(self.output.exists())
        self.output = self.folder / "capture"
        self.output.mkdir()
        (self.output / "keep").write_text("untouched")
        with self.assertRaises(FileExistsError):
            self.capture()
        self.assertEqual((self.output / "keep").read_text(), "untouched")
        self.u.SystemLibrary.get_engine_version = lambda: "5.7.0"
        with self.assertRaises(ReviewError):
            self.capture()

    def test_specification_bounds_and_primary_object_path(self):
        for change in ({"sample_count": True}, {"sample_count": 1}, {"sample_count": 2002},
                       {"animation": "/Game/Run.Other"}, {"unknown": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                specification(spec(**change))

    def test_duration_and_bone_budgets(self):
        for value in (0, 601, float("nan")):
            self.output = self.folder / str(value)
            self.u.animation.props["sequence_length"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.capture()
        self.u.animation.props["sequence_length"] = 1
        self.output = self.folder / "bones"
        self.u.AnimPoseExtensions.get_bone_names = lambda p: iter(str(i) for i in range(513))
        with self.assertRaises(ReviewError):
            self.capture()


if __name__ == "__main__":
    unittest.main()
