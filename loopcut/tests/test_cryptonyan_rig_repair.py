# SPDX-License-Identifier: GPL-3.0-or-later
import copy
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
from cryptonyan_asset_studio.rig_doctor import audit_weights, capture_blender
from cryptonyan_asset_studio.rig_repair import execute, expected_snapshot, load_plan, make_plan, policy, propose, weights_match
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.executors import run_process as supervised_process
from cryptonyan_asset_studio.storage import digest, write_json

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")
SPEC = {"armature": "ExistingRig", "meshes": ["Body"]}
POLICY = {"max_influences": 1, "max_removed_fraction": .3}


def snapshot():
    return {"schema": "cryptonyan.rig-weights/1", "armature": "ExistingRig", "bones": [
        {"name": "Origin", "parent": None, "deform": True},
        {"name": "Leg", "parent": "Origin", "deform": True},
        {"name": "Helper", "parent": "Origin", "deform": False}], "meshes": [{
            "name": "Body", "groups": ["Origin", "Leg", "Helper", "Mask"],
            "weights": [[], [{"group": 0, "weight": .5}, {"group": 3, "weight": .6}],
                        [{"group": 0, "weight": .8}, {"group": 1, "weight": .2}, {"group": 2, "weight": 1}]],
            "capture": {"locked_groups": [], "mesh_users": 1, "library_override": False, "object_mode": "OBJECT"}}]}


class PlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.bundle = self.folder / "bundle"
        self.bundle.mkdir()
        (self.bundle / "source.blend").write_bytes(b"offline opaque source")
        self.data = snapshot()
        self.data["provenance"] = {"sampler": "blender_base_vertex_groups", "capture": SPEC,
                                   "source_sha256": digest(self.bundle / "source.blend")}
        write_json(self.bundle / "weights.json", self.data)
        write_json(self.bundle / "audit.json", audit_weights(self.data, SPEC))
        self.plan_path = self.folder / "plan.json"
        write_json(self.plan_path, make_plan(self.bundle, POLICY))

    def test_deterministic_plan_normalizes_prunes_and_preserves_auxiliary_groups(self):
        original = copy.deepcopy(self.data)
        plan = make_plan(self.bundle, POLICY)
        self.assertEqual(plan, make_plan(self.bundle, POLICY))
        self.assertEqual(self.data, original)
        ops = plan["operations"]
        self.assertEqual([op["vertex"] for op in ops], [1, 2])
        self.assertEqual(ops[0]["after"], [{"group": 0, "weight": 1}, {"group": 3, "weight": .6}])
        self.assertEqual(ops[1]["after"], [{"group": 0, "weight": 1}, {"group": 2, "weight": 1}])
        self.assertAlmostEqual(ops[1]["removed_fraction"], .2)
        self.assertEqual(plan["manual_review"][0]["reason"], "unweighted_vertices")
        self.assertEqual({f["code"] for f in plan["predicted_findings"]}, {"unweighted_vertices"})

    def test_removed_fraction_budget_leaves_whole_vertex_unchanged(self):
        plan = propose(self.data, SPEC, {**POLICY, "max_removed_fraction": .1})
        self.assertEqual([op["vertex"] for op in plan["operations"]], [1])
        reasons = {r["reason"]: r for r in plan["manual_review"]}
        self.assertEqual(reasons["removed_fraction_exceeds_budget"]["vertices"], [2])

    def test_locked_deforming_assignments_are_preserved_without_unlocking(self):
        self.data["meshes"][0]["capture"]["locked_groups"] = ["Origin"]
        plan = propose(self.data, SPEC, POLICY)
        self.assertEqual(plan["operations"], [])
        self.assertEqual(next(r for r in plan["manual_review"] if r["reason"] == "locked_deform_weights")["vertices"], [1, 2])

    def test_locked_masks_do_not_block_normalization(self):
        self.data["meshes"][0]["capture"]["locked_groups"] = ["Mask"]
        self.assertEqual(len(propose(self.data, SPEC, POLICY)["operations"]), 2)

    def test_ties_use_bone_names_and_epsilon_pruning_is_budgeted(self):
        self.data["meshes"][0]["weights"][2] = [{"group": 0, "weight": .5}, {"group": 1, "weight": .5}]
        plan = propose(self.data, SPEC, {**POLICY, "max_removed_fraction": .5})
        self.assertEqual(plan["operations"][-1]["after"], [{"group": 1, "weight": 1}])
        self.data["meshes"][0]["weights"][2] = [{"group": 0, "weight": 1}, {"group": 1, "weight": 1e-6}]
        plan = propose(self.data, SPEC, {**POLICY, "max_removed_fraction": 0})
        self.assertEqual([op["vertex"] for op in plan["operations"]], [1])

    def test_invalid_and_tiny_only_weights_are_manual(self):
        self.data["meshes"][0]["weights"] = [[{"group": 0, "weight": -1}], [{"group": 0, "weight": 1e-8}]]
        plan = propose(self.data, SPEC, POLICY)
        self.assertEqual(plan["operations"], [])
        self.assertEqual({r["reason"] for r in plan["manual_review"]}, {"invalid_weights", "unweighted_vertices"})

    def test_noop_and_manual_evidence_bounds(self):
        self.data["meshes"][0]["weights"] = [[]]*150 + [[{"group": 0, "weight": 1}]]
        plan = propose(self.data, SPEC, POLICY)
        self.assertEqual(plan["operations"], [])
        self.assertEqual(plan["manual_review"][0]["count"], 150)
        self.assertEqual(len(plan["manual_review"][0]["vertices"]), 100)

    def test_shared_mesh_override_edit_mode_and_old_capture_fail_closed(self):
        for key, value in (("mesh_users", 2), ("library_override", True), ("object_mode", "EDIT"), ("locked_groups", None)):
            data = copy.deepcopy(self.data)
            data["meshes"][0]["capture"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                propose(data, SPEC, POLICY)

    def test_plan_and_all_bundle_inputs_are_pinned(self):
        for filename in ("source.blend", "weights.json", "audit.json"):
            path = self.bundle / filename
            original = path.read_bytes()
            path.write_bytes(b"changed")
            with self.subTest(filename=filename), self.assertRaises((ValueError, KeyError)):
                load_plan(self.plan_path)
            path.write_bytes(original)
        plan = json.loads(self.plan_path.read_text())
        plan["operations"][0]["after"][0]["weight"] = .2
        write_json(self.plan_path, plan)
        with self.assertRaises(ValueError):
            load_plan(self.plan_path)

    def test_all_assignment_comparison_including_masks_and_float32(self):
        plan = load_plan(self.plan_path)
        expected = expected_snapshot(self.data, plan)
        actual = copy.deepcopy(expected)
        actual["meshes"][0]["weights"][1][0]["weight"] -= 1e-8
        self.assertTrue(weights_match(actual, expected))
        actual["meshes"][0]["weights"][1][1]["weight"] = .1
        self.assertFalse(weights_match(actual, expected))

    def test_dry_run_requires_no_blender_and_refuses_existing_or_nested_output(self):
        out = self.folder / "dry"
        with patch("cryptonyan_asset_studio.rig_repair.run_process", side_effect=AssertionError("must not run")):
            result = execute(self.plan_path, out)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["planned_vertices"], 2)
        self.assertIsNone(result["changed_vertices"])
        self.assertIsNone(result["candidate"])
        with self.assertRaises(FileExistsError):
            execute(self.plan_path, out)
        with self.assertRaises(ValueError):
            execute(self.plan_path, self.bundle / "nested")

    def test_worker_failure_receipt_does_not_publish_candidate(self):
        with patch("cryptonyan_asset_studio.rig_repair.run_process", side_effect=WorkerFailure(code="rig_repair_guard")):
            with self.assertRaises(WorkerFailure):
                execute(self.plan_path, self.folder / "failed", sys.executable, apply=True)
        report = json.loads((self.folder / "failed/result.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["candidate"])
        self.assertIsNone(report["changed_vertices"])

    def test_cli_offline_plan_dry_run_and_no_overwrite(self):
        write_json(self.folder / "policy.json", POLICY)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        base = [sys.executable, "-m", "cryptonyan_asset_studio.rig_repair"]
        command = base + ["plan", str(self.bundle), "--policy", str(self.folder / "policy.json"), "--output", str(self.folder / "cli.json")]
        result = subprocess.run(command, env=env, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command, env=env, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run(base + ["execute", str(self.folder / "cli.json"), "--output", str(self.folder / "dry")],
                                env=env, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")

    def test_policy_and_apply_types_rejected(self):
        for change in ({"max_influences": True}, {"max_removed_fraction": .51}, {"max_removed_fraction": float("nan")}, {"repair_unweighted": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy({**POLICY, **change})
        with self.assertRaises(ValueError):
            execute(self.plan_path, self.folder / "bad", apply=1)

    def test_oversized_plan_rejected_before_publication(self):
        with patch("cryptonyan_asset_studio.rig_repair.MAX_JSON", 100), self.assertRaisesRegex(ValueError, "32 MiB"):
            make_plan(self.bundle, POLICY)

    def test_incomplete_plan_fails_with_schema_error(self):
        write_json(self.plan_path, {"schema": "cryptonyan.rig-repair-plan/1"})
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            load_plan(self.plan_path)


@unittest.skipUnless(BLENDER, "Blender unavailable; set LOOPCUT_BLENDER for actual save/reopen weight repair")
class BlenderRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        for variant in ("clean", "external"):
            source = cls.folder / (variant + ".blend")
            command = [BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                       "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_rig_fixture.py"),
                       "--", str(source), "--repair"]
            if variant == "external":
                command.append("--external")
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
        cls.source = cls.folder / "clean.blend"
        cls.bundle = cls.folder / "audit"
        capture_blender(cls.source, SPEC, cls.bundle, BLENDER)
        cls.plan_path = cls.folder / "plan.json"
        write_json(cls.plan_path, make_plan(cls.bundle, {"max_influences": 4, "max_removed_fraction": .25}))

    def test_real_repair_save_reopen_masks_shape_keys_uvs_and_original_preservation(self):
        before = digest(self.source), digest(self.bundle / "source.blend")
        out = self.folder / "repaired"
        result = execute(self.plan_path, out, BLENDER, apply=True)
        self.assertEqual(result["status"], "candidate_created_review_required")
        self.assertEqual(result["changed_vertices"], 2)
        self.assertTrue(result["verified_after_reopen"])
        self.assertEqual(before, (digest(self.source), digest(self.bundle / "source.blend")))
        self.assertEqual(result["candidate"]["sha256"], digest(out / "candidate.blend"))
        data = json.loads((out / "verified-weights.json").read_text())
        report = json.loads((out / "audit.json").read_text())
        self.assertEqual({f["code"] for f in report["findings"]}, {"unweighted_vertices"})
        self.assertEqual(report["findings"][0]["vertices"], [0, 4])
        self.assertTrue(data["meshes"][0]["capture"]["shape_keys_present"])
        self.assertEqual(len(data["meshes"][0]["weights"][2]), 4)
        self.assertEqual(len(data["meshes"][0]["weights"][4]), 2)
        # Independently run the original read-only doctor on the saved candidate.
        reopened = capture_blender(out / "candidate.blend", SPEC, self.folder / "independent-audit", BLENDER)
        self.assertEqual(reopened["findings"], report["findings"])

    def test_real_locked_weights_produce_no_automatic_candidate(self):
        bundle = self.folder / "locked-audit"
        capture_blender(self.source, {**SPEC, "meshes": ["LockedBody"]}, bundle, BLENDER)
        plan = make_plan(bundle, {"max_influences": 4, "max_removed_fraction": .25})
        self.assertEqual(plan["operations"], [])
        path = self.folder / "locked-plan.json"
        write_json(path, plan)
        result = execute(path, self.folder / "locked-result", BLENDER, apply=True)
        self.assertEqual(result["status"], "no_automatic_changes")
        self.assertIsNone(result["candidate"])

    def test_real_external_resource_rejected_before_save(self):
        bundle = self.folder / "external-audit"
        capture_blender(self.folder / "external.blend", SPEC, bundle, BLENDER)
        path = self.folder / "external-plan.json"
        write_json(path, make_plan(bundle, {"max_influences": 4, "max_removed_fraction": .25}))
        out = self.folder / "external-result"
        with self.assertRaises(WorkerFailure) as failure:
            execute(path, out, BLENDER, apply=True)
        self.assertEqual(failure.exception.code, "rig_repair_guard")
        self.assertFalse((out / "candidate.blend").exists())

    def test_real_shared_mesh_refused_during_planning(self):
        bundle = self.folder / "shared-audit"
        capture_blender(self.source, {**SPEC, "meshes": ["SharedBody"]}, bundle, BLENDER)
        with self.assertRaisesRegex(ValueError, "single-user"):
            make_plan(bundle, POLICY)

    def test_real_geometry_drift_after_save_fails_reopen_verification(self):
        out = self.folder / "tampered"
        def process(command, context):
            if context.output.name == "verify":
                script = self.folder / "tamper_geometry.py"
                script.write_text("import bpy, sys\n"
                    "p = sys.argv[sys.argv.index('--')+1]\n"
                    "bpy.ops.wm.open_mainfile(filepath=p, load_ui=False, use_scripts=False)\n"
                    "bpy.data.objects['Body'].data.vertices[0].co.z += 1\n"
                    "bpy.ops.wm.save_as_mainfile(filepath=p, check_existing=False)\n", encoding="utf-8")
                result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                    "--python-exit-code", "1", "--python", str(script), "--", str(out / "candidate.blend")],
                    capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
            return supervised_process(command, context)
        with patch("cryptonyan_asset_studio.rig_repair.run_process", side_effect=process), self.assertRaises(WorkerFailure) as failure:
            execute(self.plan_path, out, BLENDER, apply=True)
        self.assertEqual(failure.exception.code, "rig_repair_verify")
        report = json.loads((out / "result.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["candidate"])
        self.assertFalse((out / "audit.json").exists())


if __name__ == "__main__":
    unittest.main()
