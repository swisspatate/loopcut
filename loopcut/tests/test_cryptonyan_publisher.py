# SPDX-License-Identifier: GPL-3.0-or-later
"""Publication integrity and Unreal orchestration; engine API here is a test double."""
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "addons_core"))
from cryptonyan_asset_studio.publication import asset_name, load_package, package_id, seal_manifest
from cryptonyan_asset_studio.schema import Mission
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.unreal_review import plan_import, probe, run_review_import


def fixture(root):
    name = asset_name("Platform")
    # A real self-contained indexed triangle, glTF Y-up (Blender Z-up bounds below).
    binary = struct.pack("<9f3H", 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 1, 2) + b"\0\0"
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": name, "mesh": 0}], "meshes": [{"primitives": [
               {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
           "materials": [{"name": "M_Test"}], "buffers": [{"byteLength": len(binary)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                           {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                          "min": [0, 0, -1], "max": [1, 0, 0]},
                         {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}]}
    raw = json.dumps(doc).encode()
    raw += b" " * (-len(raw) % 4)
    data = struct.pack("<II", len(raw), 0x4E4F534A) + raw + struct.pack("<II", len(binary), 0x004E4942) + binary
    mesh = root / (name + ".glb")
    mesh.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(data)) + data)
    write_json(root / "quality.json", {"schema": "cryptonyan.quality-batch/1", "passed": True,
        "reports": [{"schema": "cryptonyan.asset-doctor/1", "source": "blender", "passed": True,
                     "severity_counts": {}, "objects": [{"name": "Platform", "type": "MESH", "triangles": 1}]}]})
    manifest = {"schema": "cryptonyan.publication/1", "source": {"object": "Platform", "sha256": "a" * 64},
                "producer": {"studio": "test", "blender": "scripted"},
                "asset": {"name": name, "file": mesh.name, "sha256": digest(mesh), "bytes": mesh.stat().st_size,
                          "triangles": 1, "bounds_blender_m": [[0, 0, 0], [1, 1, 0]], "material_count": 1},
                "policy": {"format": "glb", "units": "meters", "pivot": "source_object_origin",
                           "transforms": "rotation_scale_baked", "target_engine": "5.8", "collision": "none",
                           "lod": "source_only", "textures": "none"}}
    seal_manifest(manifest, root)
    return root / "manifest.json"


class FakeMesh:
    def __init__(self):
        self.triangles = 1
        self.bounds = SimpleNamespace(min=SimpleNamespace(x=0, y=-100, z=0), max=SimpleNamespace(x=100, y=0, z=0))

    def get_class(self):
        return SimpleNamespace(get_name=lambda: "StaticMesh")

    def get_num_triangles(self, lod):
        return self.triangles

    def get_bounding_box(self):
        return self.bounds

    def get_editor_property(self, name):
        assert name == "static_materials"
        return [SimpleNamespace(get_editor_property=lambda name: object())]


class FakeTask:
    def __init__(self):
        self.properties = {}

    def set_editor_property(self, name, value):
        self.properties[name] = value

    def get_editor_property(self, name):
        return self.properties[name]


class FakeUnreal:
    StaticMesh = FakeMesh
    AssetImportTask = FakeTask
    StaticMeshEditorSubsystem = object

    def __init__(self):
        self.version = "5.8.0-test"
        self.mesh = FakeMesh()
        self.existing = False
        self.reserved = False
        self.tasks = []
        self.saved = []
        self.paths = []
        self.collisions = 3
        self.fail_save = False
        self.escape = False
        self.SystemLibrary = SimpleNamespace(get_engine_version=lambda: self.version)
        self.EditorAssetLibrary = SimpleNamespace(
            does_directory_exist=lambda dest: self.existing or self.reserved,
            list_assets=lambda *args, **kwargs: self.paths,
            make_directory=self.reserve, save_loaded_asset=self.save)
        self.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(import_asset_tasks=self.import_tasks))

    def get_editor_subsystem(self, cls):
        return SimpleNamespace(get_lod_count=lambda mesh: 1, remove_collisions=self.remove_collisions,
                               get_simple_collision_count=lambda mesh: self.collisions,
                               get_convex_collision_count=lambda mesh: 0)

    def remove_collisions(self, mesh):
        self.collisions = 0

    def reserve(self, path):
        self.reserved = True
        return True

    def import_tasks(self, tasks):
        self.tasks += tasks
        props = tasks[0].properties
        name = props["destination_name"]
        self.paths = [props["destination_path"] + "/" + name + "." + name]
        if self.escape:
            self.paths = ["/Game/Existing.Mesh"]
        props["imported_object_paths"] = self.paths

    def load_asset(self, path):
        return self.mesh

    def save(self, obj, **kwargs):
        if self.fail_save:
            return False
        self.saved.append(obj)
        return True


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.manifest = fixture(self.bundle)

    def rewrite(self, mutate):
        data = json.loads(self.manifest.read_text())
        mutate(data)
        data["package_id"] = package_id(data)
        write_json(self.manifest, data)

    def test_mission_requires_one_explicit_static_target(self):
        good = {"type": "asset_publish", "inputs": ["platform.blend"], "target_assets": ["Platform"]}
        self.assertEqual(Mission.parse(good).json()["type"], "asset_publish")
        for changed in ({"inputs": ["a.json"]}, {"inputs": ["a.blend", "b.blend"]},
                        {"target_assets": []}, {"target_assets": ["A", "B"]}, {"constraints": {"repair_copy": True}}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                Mission.parse({**good, **changed})

    def test_bundle_validates_and_plan_is_content_scoped(self):
        data = load_package(self.manifest)
        plan = plan_import(self.manifest)
        self.assertEqual(plan["destination"], "/Game/CryptoNyan/Review/P_" + data["package_id"])
        self.assertFalse(plan["replace_existing"])
        self.assertEqual(plan["manifest_sha256"], digest(self.manifest))
        self.assertNotEqual(asset_name("A B"), asset_name("A_B"))
        self.assertNotEqual(asset_name("A"), asset_name("a"))

    def test_tampering_rejected(self):
        data = load_package(self.manifest)
        (self.bundle / data["asset"]["file"]).write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            load_package(self.manifest)

    def test_report_tampering_rejected(self):
        (self.bundle / "quality.json").write_text("{}")
        with self.assertRaises(ValueError):
            load_package(self.manifest)

    def test_rehashed_metric_spoof_rejected(self):
        self.rewrite(lambda data: data["asset"].update(bounds_blender_m=[[0, 0, 0], [999, 1, 0]]))
        with self.assertRaises(ValueError):
            load_package(self.manifest)

    def test_manifest_extra_fields_path_escape_and_bad_policy(self):
        original = self.manifest.read_bytes()
        for mutate in (lambda data: data.update(destination="/Game/Existing"),
                       lambda data: data["asset"].update(file="../escape.glb"),
                       lambda data: data["policy"].update(units="centimeters"),
                       lambda data: data["asset"].update(triangles=True)):
            self.manifest.write_bytes(original)
            self.rewrite(mutate)
            with self.assertRaises(ValueError):
                load_package(self.manifest)

    def test_external_dependency_glb_rejected(self):
        from loopcut import glb
        package = load_package(self.manifest)
        path = self.bundle / package["asset"]["file"]
        doc, binary = glb.parse(path.read_bytes())
        doc["buffers"][0]["uri"] = "file:///private.bin"
        raw = json.dumps(doc).encode()
        raw += b" " * (-len(raw) % 4)
        data = struct.pack("<II", len(raw), glb.JSON_CHUNK) + raw + struct.pack("<II", len(binary), glb.BIN_CHUNK) + binary
        path.write_bytes(struct.pack("<III", glb.MAGIC, 2, 12 + len(data)) + data)
        self.rewrite(lambda d: d["asset"].update(sha256=digest(path), bytes=path.stat().st_size))
        with self.assertRaises(ValueError):
            load_package(self.manifest)

    def test_symlinked_asset_rejected(self):
        package = load_package(self.manifest)
        path = self.bundle / package["asset"]["file"]
        other = self.root / "other.glb"
        path.rename(other)
        try:
            path.symlink_to(other)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError):
            load_package(self.manifest)

    def test_dry_run_and_receipt_are_non_destructive(self):
        engine = FakeUnreal()
        receipt = self.root / "receipt.json"
        result = run_review_import(self.manifest, receipt, unreal_module=engine)
        self.assertEqual(result["status"], "planned")
        self.assertFalse(engine.reserved)
        self.assertEqual(engine.tasks, [])
        with self.assertRaises(FileExistsError):
            run_review_import(self.manifest, receipt, apply=True, unreal_module=engine)
        with self.assertRaises(ValueError):
            run_review_import(self.manifest, self.bundle / "receipt.json")

    def test_import_validates_before_save(self):
        engine = FakeUnreal()
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "imported", result)
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(len(engine.saved), 1)
        self.assertEqual(engine.collisions, 0)
        props = engine.tasks[0].properties
        self.assertFalse(props["replace_existing"])
        self.assertFalse(props["save"])
        self.assertFalse(props["async_"])

    def test_failed_validation_retains_review_folder_and_does_not_save(self):
        engine = FakeUnreal()
        engine.mesh.triangles = 99
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["partial_review_folder"])
        self.assertIn("triangle_count_mismatch", result["validation"]["errors"])
        self.assertEqual(engine.saved, [])
        again = run_review_import(self.manifest, self.root / "retry.json", apply=True, unreal_module=engine)
        self.assertEqual(again["status"], "failed")
        self.assertEqual(len(engine.tasks), 1)

    def test_wrong_axes_or_units_block_save(self):
        engine = FakeUnreal()
        engine.mesh.bounds.max.x = 1
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertIn("bounds_or_axis_mismatch", result["validation"]["errors"])
        self.assertFalse(engine.saved)

    def test_existing_folder_rejected_before_import(self):
        engine = FakeUnreal()
        engine.existing = True
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(engine.tasks, [])

    def test_wrong_runtime_rejected_before_mutation(self):
        engine = FakeUnreal()
        engine.version = "5.7.1"
        self.assertFalse(probe(engine)["target_version_matches"])
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertFalse(engine.reserved)
        self.assertEqual(result["status"], "failed")

    def test_outside_import_result_never_saved(self):
        engine = FakeUnreal()
        engine.escape = True
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(engine.saved)

    def test_save_failure_receipt_does_not_claim_success(self):
        engine = FakeUnreal()
        engine.fail_save = True
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_stage"], "saving")
        self.assertEqual(result["saved"], [])

    def test_missing_runtime_api_is_reported_before_mutation(self):
        engine = FakeUnreal()
        engine.StaticMesh = object
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertIn("StaticMesh.get_num_triangles", result["probe"]["missing_apis"])
        self.assertFalse(engine.reserved)

    def test_bundle_change_during_import_blocks_save(self):
        engine = FakeUnreal()
        original_import = engine.import_tasks
        def changing(tasks):
            original_import(tasks)
            (self.bundle / "quality.json").write_text("{}")
        engine.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(import_asset_tasks=changing))
        result = run_review_import(self.manifest, self.root / "receipt.json", apply=True, unreal_module=engine)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(engine.saved)

    def test_false_string_does_not_authorize_import(self):
        engine = FakeUnreal()
        with self.assertRaises(ValueError):
            run_review_import(self.manifest, self.root / "receipt.json", apply="false", unreal_module=engine)
        self.assertEqual(engine.tasks, [])

    def test_bridge_rejects_publication_from_another_source(self):
        from cryptonyan_asset_studio.bridge import MissionBridge
        assets = self.root / "inputs"
        assets.mkdir()
        (assets / "scene.blend").write_bytes(b"test snapshot; custom test executor does not use Blender")
        class WrongSource:
            name = "scripted"
            def execute(self, mission, context):
                manifest = fixture(context.output)
                package = load_package(manifest)
                return ["quality.json", "manifest.json", package["asset"]["file"]]
        with MissionBridge(self.root / "jobs", assets, WrongSource()) as bridge:
            task = bridge.submit({"type": "asset_publish", "inputs": ["scene.blend"], "target_assets": ["Platform"]})
            final = bridge.wait(task["id"], 5)
            self.assertEqual(final["state"], "failed")
            self.assertEqual(final["artifacts"], [])


if __name__ == "__main__":
    unittest.main()
