# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.image_workshop import specification, prepare, load_bundle, run, inspect_source, comparison_html, budgets
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.executors import WorkerFailure, BudgetExpired
from cryptonyan_asset_studio.materials import read_png
from test_cryptonyan_materials import png
from test_glb import glb_bytes

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


def recipe():
    return {"schema": "cryptonyan.image-workshop/1", "id": "Temple", "intent": "Temple de référence",
            "assumptions": ["Les faces cachées sont symétriques"], "triangle_budget": 1000,
            "camera": {"position_m": [7, -9, 6], "target_m": [0, 0, 1], "projection": "ORTHO",
                       "lens_mm": 50, "ortho_scale_m": 6, "resolution": [64, 64], "samples": 1},
            "parts": [{"id": "Base", "shape": "box", "position_m": [0, 0, .25], "size_m": [3, 2, .5],
                       "yaw_deg": 0, "color": [.3, .5, .7]}], "sources": {}}


def source_glb(edit=None, textured=False):
    binary = struct.pack("<12f12H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3)
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": "Source", "mesh": 0}], "meshes": [{"primitives": [
               {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
           "materials": [{"name": "Material"}], "buffers": [{"byteLength": len(binary)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48},
                           {"buffer": 0, "byteOffset": 48, "byteLength": 24}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3",
                          "min": [0, 0, 0], "max": [1, 1, 1]},
                         {"bufferView": 1, "componentType": 5123, "count": 12, "type": "SCALAR"}]}
    if textured:
        uv_offset = len(binary)
        binary += struct.pack("<8f", 0, 0, 1, 0, 0, 1, 1, 1)
        image = png((200, 50, 30))
        image_offset = len(binary); binary += image
        binary += b"\0" * (-len(binary) % 4)
        doc["buffers"][0]["byteLength"] = len(binary)
        doc["bufferViews"] += [{"buffer": 0, "byteOffset": uv_offset, "byteLength": 32},
                               {"buffer": 0, "byteOffset": image_offset, "byteLength": len(image)}]
        doc["accessors"].append({"bufferView": 2, "componentType": 5126, "count": 4, "type": "VEC2"})
        doc["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"] = 2
        doc["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
        doc["materials"][0]["pbrMetallicRoughness"] = {"baseColorTexture": {"index": 0}}
    if edit:
        edit(doc)
    return glb_bytes(doc, binary)


class Fixture:
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.reference = self.root / "input.png"
        self.reference.write_bytes(png(width=64, height=64))

    def prepare(self, value=None, name="bundle"):
        return prepare(self.reference, value or recipe(), self.root / name)

    def external(self):
        (self.root / "mesh.glb").write_bytes(source_glb())
        value = recipe()
        value["sources"] = {"Hero": {"file": "mesh.glb", "provider": "fixture", "model": "tetrahedron",
                                      "license": "test", "reference_sha256": digest(self.reference)}}
        value["parts"][0].update(shape="glb", source="Hero")
        return value


class ContractTests(Fixture, unittest.TestCase):
    def test_deterministic_immutable_reference_bundle(self):
        value = recipe(); before = copy.deepcopy(value)
        a = self.prepare(value); b = self.prepare(value, "second")
        self.assertEqual(a, b); self.assertEqual(value, before)
        self.assertEqual(load_bundle(self.root / "bundle"), a)
        self.assertEqual(digest(self.reference), digest(self.root / "bundle/reference.png"))
        with self.assertRaises(FileExistsError): self.prepare()

    def test_invalid_camera_names_dimensions_and_budgets(self):
        for field, val in [("triangle_budget", True), ("triangle_budget", 200001), ("assumptions", []), ("id", "../x")]:
            value = recipe(); value[field] = val
            with self.subTest(field=field), self.assertRaises(ValueError): specification(value)
        for field, val in [("position_m", [0, 0, 1]), ("samples", 65), ("resolution", [0, 64]), ("lens_mm", float("nan"))]:
            value = recipe(); value["camera"][field] = val
            with self.subTest(field=field), self.assertRaises(ValueError): specification(value)

    def test_duplicate_parts_unknown_shapes_and_missing_sources(self):
        value = recipe(); value["parts"] *= 2
        with self.assertRaises(ValueError): specification(value)
        for change in ({"shape": "python"}, {"shape": "glb", "source": "Absent"}, {"size_m": [1, 0, 1]}, {"source": "Unknown"}):
            value = recipe(); value["parts"][0].update(change)
            with self.assertRaises(ValueError): specification(value)

    def test_budget_rejected_before_any_output(self):
        value = recipe(); value["triangle_budget"] = 12; value["parts"][0]["shape"] = "cylinder"
        with self.assertRaises(ValueError): self.prepare(value)
        self.assertFalse((self.root / "bundle").exists())

    def test_instances_count_towards_vertex_and_decoded_pixel_budgets(self):
        value = self.external()
        part = copy.deepcopy(value["parts"][0]); part["id"] = "Second"
        value["parts"].append(part)
        for source in ({"triangles": 4, "vertices": 400000, "textures": []},
                       {"triangles": 4, "vertices": 4, "textures": [{"width": 4096, "height": 4096}]*2}):
            with self.assertRaises(ValueError): budgets(value, {"Hero": source})

    def test_corrupt_image_and_changed_reference(self):
        self.prepare(); (self.root / "bundle/reference.png").write_bytes(png((2, 3, 4)))
        with self.assertRaises(ValueError): load_bundle(self.root / "bundle")
        self.reference.write_bytes(b"not png")
        with self.assertRaises(ValueError): self.prepare(name="other")

    def test_changed_plan_is_refused(self):
        data = self.prepare(); data["recipe"]["parts"][0]["size_m"] = [9, 9, 9]
        write_json(self.root / "bundle/plan.json", data)
        with self.assertRaises(ValueError): load_bundle(self.root / "bundle")

    def test_external_mesh_snapshot_and_provenance(self):
        value = self.external(); result = self.prepare(value)
        self.assertEqual(result["estimated_triangles"], 4)
        self.assertEqual(load_bundle(self.root / "bundle"), result)
        (self.root / "mesh.glb").write_bytes(b"changed outside")
        self.assertEqual(load_bundle(self.root / "bundle"), result)

    def test_source_path_escape_and_wrong_reference(self):
        for field, val in [("file", "../mesh.glb"), ("file", "https://host/model.glb"), ("reference_sha256", "0"*64)]:
            value = self.external(); value["sources"]["Hero"][field] = val
            with self.subTest(field=field), self.assertRaises(ValueError): self.prepare(value)

    def test_changed_glb_and_unused_source(self):
        value = self.external(); self.prepare(value)
        (self.root / "bundle/source_Hero.glb").write_bytes(b"corrupt")
        with self.assertRaises(ValueError): load_bundle(self.root / "bundle")
        value["parts"][0].pop("source"); value["parts"][0]["shape"] = "box"
        with self.assertRaises(ValueError): specification(value)

    def test_complex_glb_contract_rejections(self):
        edits = [lambda d: d.update(animations=[{}]), lambda d: d.update(skins=[{}]),
                 lambda d: d["nodes"][0].update(scale=[1, 1, 1]),
                 lambda d: d["buffers"][0].update(uri="external.bin"),
                 lambda d: d["meshes"][0]["primitives"][0].update(targets=[{}]),
                 lambda d: d["materials"][0].update(extensions={"unknown": {}}),
                 lambda d: d["materials"][0].update(alphaMode="BLEND"),
                 lambda d: d["accessors"][0].update(count=600001),
                 lambda d: d["nodes"].append({"mesh": 0})]
        for index, edit in enumerate(edits):
            path = self.root / "mesh.glb"; path.write_bytes(source_glb(edit))
            with self.subTest(index=index), self.assertRaises(ValueError): inspect_source(path)

    def test_embedded_png_provenance_and_missing_uv(self):
        path = self.root / "mesh.glb"; path.write_bytes(source_glb(textured=True))
        _, result = inspect_source(path)
        self.assertEqual(result["textures"][0]["role"], "base_color")
        self.assertEqual(result["textures"][0]["width"], 2)
        for edit in (lambda d: d["images"][0].update(mimeType="image/jpeg"),
                     lambda d: d["meshes"][0]["primitives"][0]["attributes"].pop("TEXCOORD_0")):
            path.write_bytes(source_glb(edit, textured=True))
            with self.assertRaises(ValueError): inspect_source(path)

    def test_symlink_sources_refused(self):
        link = self.root / "link.png"
        try: link.symlink_to(self.reference)
        except OSError: self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError): prepare(link, recipe(), self.root / "bundle")

    def test_comparison_embeds_images_escapes_text_no_score(self):
        value = recipe(); value["intent"] = "<script>alert(1)</script>"; value["assumptions"] = ["<b>hidden</b>"]
        text = comparison_html(self.reference, self.reference, value)
        self.assertIn("&lt;script&gt;", text); self.assertIn("&lt;b&gt;", text)
        self.assertNotIn("<script>", text); self.assertNotIn('src="http', text)
        self.assertEqual(text.count("data:image/png;base64,"), 2)

    def test_worker_failure_and_timeout_persist_receipt(self):
        self.prepare()
        for index, exception in enumerate((WorkerFailure(), BudgetExpired())):
            output = self.root / str(index)
            with patch("cryptonyan_asset_studio.image_workshop.run_process", side_effect=exception), self.assertRaises(type(exception)):
                run(self.root / "bundle", output, sys.executable)
            self.assertEqual(json.loads((output / "operation.json").read_text())["status"], "failed")
            self.assertFalse((output / "comparison.html").exists())

    def test_invalid_run_paths_and_no_overwrite(self):
        self.prepare()
        with self.assertRaises(ValueError): run(self.root / "bundle", self.root / "bundle/attempt", sys.executable)
        with self.assertRaises(ValueError): run(self.root / "bundle", self.root / "attempt", self.root / "absent")
        with self.assertRaises(FileExistsError): run(self.root / "bundle", self.root, sys.executable)

    def test_real_cli_prepare_and_check(self):
        path = self.root / "recipe.json"; write_json(path, recipe())
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        for args in (["prepare", str(self.reference), str(path), "--output", str(self.root / "bundle")],
                     ["check", str(self.root / "bundle")]):
            p = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio.image_workshop", *args],
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["reference"]["sha256"], digest(self.reference))
        path = self.root / "source.glb"; path.write_bytes(source_glb())
        p = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio.image_workshop", "inspect-glb", str(path)],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["triangles"], 4)


@unittest.skipUnless(BLENDER, "Blender executable unavailable")
class BlenderTests(Fixture, unittest.TestCase):
    def test_real_primitives_render_export_and_saved_scene(self):
        value = recipe()
        for index, shape in enumerate(("cylinder", "cone")):
            part = copy.deepcopy(value["parts"][0]); part.update(id=shape, shape=shape, size_m=[.5, .5, 1], position_m=[index, 0, 1])
            value["parts"].append(part)
        before = digest(self.reference); plan = self.prepare(value)
        out = self.root / "attempt"; result = run(self.root / "bundle", out, BLENDER)
        self.assertEqual(result["status"], "candidate_created_review_required")
        report = json.loads((out / "geometry.json").read_text())
        self.assertEqual(report["triangles"], 198); self.assertEqual(report["bounding_boxes_outside_camera"], [])
        self.assertEqual(digest(self.reference), before); self.assertEqual(load_bundle(self.root / "bundle"), plan)
        self.assertFalse(result["engine_validated"])
        self.assertEqual(read_png(out / "render.png")[1], {"width": 64, "height": 64})
        for filename, meta in result["artifacts"].items(): self.assertEqual(digest(out / filename), meta["sha256"])
        expression = "import bpy; assert bpy.data.objects.get('Base'); assert len([o for o in bpy.data.objects if o.type == 'MESH']) == 3"
        p = subprocess.run([BLENDER, "--background", "--disable-autoexec", str(out / "candidate.blend"),
                            "--python-exit-code", "1", "--python-expr", expression], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)

    def test_real_external_glb_normalization_and_framing_warning(self):
        value = self.external(); value["camera"]["ortho_scale_m"] = .1
        (self.root / "mesh.glb").write_bytes(source_glb(textured=True))
        self.prepare(value)
        out = self.root / "attempt"; run(self.root / "bundle", out, BLENDER)
        report = json.loads((out / "geometry.json").read_text())
        self.assertEqual(report["triangles"], 4)
        self.assertEqual(report["objects"]["Base"]["size"], [3.0, 2.0, .5])
        self.assertEqual(report["bounding_boxes_outside_camera"], ["Base"])
        from cryptonyan_asset_studio.publication import describe_textures
        self.assertEqual(describe_textures(out / "candidate.glb")[0]["role"], "base_color")
        expression = "import bpy; assert any(i.packed_file for i in bpy.data.images if i.type == 'IMAGE')"
        p = subprocess.run([BLENDER, "--background", "--disable-autoexec", str(out / "candidate.blend"),
                            "--python-exit-code", "1", "--python-expr", expression], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)


if __name__ == "__main__":
    unittest.main()
