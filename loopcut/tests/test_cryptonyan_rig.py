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
from cryptonyan_asset_studio.rig_doctor import audit_weights, capture_blender, specification
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.storage import digest

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


def spec(**changes):
    return {"armature": "ExistingRig", "meshes": ["Body"], **changes}


def snapshot():
    return {"schema": "cryptonyan.rig-weights/1", "armature": "ExistingRig", "bones": [
        {"name": "Origin", "parent": None, "deform": True},
        {"name": "Leg", "parent": "Origin", "deform": True},
        {"name": "Helper", "parent": "Origin", "deform": False}],
        "meshes": [{"name": "Body", "groups": ["Origin", "Leg", "Helper", "Mask"],
                    "weights": [[{"group": 0, "weight": 1}], [{"group": 1, "weight": 1}]]}]}


def findings(report):
    return {f["code"]: f for f in report["findings"]}


class RigTests(unittest.TestCase):
    def test_repeatability_and_scope_without_mutation(self):
        data, settings = snapshot(), spec()
        before = copy.deepcopy((data, settings))
        result = audit_weights(data, settings)
        self.assertEqual(result, audit_weights(data, settings))
        self.assertEqual((data, settings), before)
        self.assertEqual(result["status"], "no_findings_within_scope")
        self.assertFalse(result["coverage"]["evaluated_deformation"])
        self.assertFalse(result["coverage"]["automatic_repair"])

    def test_only_deforming_bones_contribute_to_weight_sum(self):
        data = snapshot()
        data["meshes"][0]["weights"] = [[{"group": 2, "weight": 1}, {"group": 3, "weight": 1}],
                                         [{"group": 1, "weight": .4}, {"group": 3, "weight": 1}]]
        report = audit_weights(data, spec())
        self.assertEqual(findings(report)["unweighted_vertices"]["vertices"], [0])
        self.assertEqual(findings(report)["weight_sum"]["vertices"], [1])
        self.assertEqual(report["meshes"][0]["non_bone_groups"], ["Mask"])
        self.assertEqual(report["meshes"][0]["nondeforming_bone_groups"], ["Helper"])

    def test_influence_limit_epsilon_and_sum_tolerance(self):
        data = snapshot()
        data["meshes"][0]["weights"] = [[{"group": 0, "weight": .5}, {"group": 1, "weight": .5}],
                                         [{"group": 0, "weight": .9999}, {"group": 1, "weight": 1e-6}]]
        report = audit_weights(data, spec(max_influences=1))
        self.assertEqual(set(findings(report)), {"too_many_influences"})
        self.assertEqual(findings(report)["too_many_influences"]["vertices"], [0])
        self.assertIn("weight_sum", findings(audit_weights(data, spec(sum_tolerance=0))))

    def test_invalid_weights_reported_not_normalized(self):
        data = snapshot()
        data["meshes"][0]["weights"][0][0]["weight"] = -1
        data["meshes"][0]["weights"][1][0]["weight"] = 2
        result = audit_weights(data, spec())
        self.assertEqual(findings(result)["invalid_weights"]["vertices"], [0, 1])
        self.assertEqual(data["meshes"][0]["weights"][1][0]["weight"], 2)

    def test_findings_are_bounded_but_counts_are_complete(self):
        data = snapshot()
        data["meshes"][0]["weights"] = [[] for _ in range(150)]
        finding = findings(audit_weights(data, spec()))["unweighted_vertices"]
        self.assertEqual(finding["count"], 150)
        self.assertEqual(finding["vertices"], list(range(100)))
        self.assertTrue(finding["indices_truncated"])

    def test_hierarchy_cycle_missing_parent_and_duplicate_bones_fail(self):
        for change in ("cycle", "missing", "duplicate"):
            data = snapshot()
            if change == "duplicate":
                data["bones"].append(data["bones"][0])
            else:
                data["bones"][0]["parent"] = "Leg" if change == "cycle" else "Missing"
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit_weights(data, spec())

    def test_mesh_mapping_and_assignment_indices_fail_closed(self):
        for entries in ([{"group": 4, "weight": 1}], [{"group": True, "weight": 1}],
                        [{"group": 0, "weight": 1}]*2, [{"group": 0, "weight": float("nan")}]):
            data = snapshot()
            data["meshes"][0]["weights"][0] = entries
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                audit_weights(data, spec())
        with self.assertRaises(ValueError):
            audit_weights(snapshot(), spec(meshes=["Other"]))

    def test_combined_vertex_and_assignment_budgets(self):
        data = snapshot()
        for limit in ("MAX_VERTICES", "MAX_ASSIGNMENTS"):
            with patch("cryptonyan_asset_studio.rig_doctor." + limit, 1), self.assertRaises(ValueError):
                audit_weights(data, spec())

    def test_configuration_rejects_unknown_fields_and_ambiguous_values(self):
        for change in ({"meshes": []}, {"meshes": ["Body", "Body"]}, {"max_influences": True},
                       {"weight_epsilon": float("inf")}, {"sum_tolerance": -.1}, {"repair": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                specification(spec(**change))

    def test_cli_report_exit_codes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "weights.json").write_text(json.dumps(snapshot()))
            (folder / "spec.json").write_text(json.dumps(spec()))
            env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
            command = [sys.executable, "-m", "cryptonyan_asset_studio.rig_doctor", "audit",
                       str(folder / "weights.json"), str(folder / "spec.json"), "--output", str(folder / "audit")]
            result = subprocess.run(command, env=env, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = digest(folder / "audit/audit.json")
            result = subprocess.run(command, env=env, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(digest(folder / "audit/audit.json"), before)


@unittest.skipUnless(BLENDER, "Blender unavailable; set LOOPCUT_BLENDER to test actual existing skin weights")
class BlenderRigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.source = cls.folder / "existing.blend"
        result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
            "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_rig_fixture.py"),
            "--", str(cls.source)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def test_real_weights_findings_and_source_preservation(self):
        before = digest(self.source)
        report = capture_blender(self.source, spec(), self.folder / "good", BLENDER)
        self.assertEqual(digest(self.source), before)
        self.assertEqual(report["provenance"]["source_sha256"], before)
        self.assertEqual(findings(report)["unweighted_vertices"]["vertices"], [0, 4])
        self.assertEqual(findings(report)["weight_sum"]["vertices"], [1])
        self.assertEqual(findings(report)["too_many_influences"]["vertices"], [2])
        self.assertEqual(report["meshes"][0]["max_influences"], 5)
        self.assertEqual(report["meshes"][0]["non_bone_groups"], ["PaintMask"])
        self.assertFalse(report["coverage"]["evaluated_deformation"])

    def test_ambiguous_armature_binding_fails_without_audit(self):
        before = digest(self.source)
        with self.assertRaises(WorkerFailure) as error:
            capture_blender(self.source, spec(meshes=["AmbiguousBody"]), self.folder / "ambiguous", BLENDER)
        self.assertEqual(error.exception.code, "rig_binding")
        self.assertEqual(digest(self.source), before)
        self.assertFalse((self.folder / "ambiguous/audit.json").exists())

    def test_missing_armature_fails_without_audit(self):
        with self.assertRaises(WorkerFailure) as error:
            capture_blender(self.source, spec(armature="Missing"), self.folder / "missing", BLENDER)
        self.assertEqual(error.exception.code, "rig_mapping")


if __name__ == "__main__":
    unittest.main()
