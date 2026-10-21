# SPDX-License-Identifier: GPL-3.0-or-later
"""Unreal editor protocol doubles; these tests do NOT execute an Unreal engine."""
import copy
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.materials import pack_material
from cryptonyan_asset_studio.mcp_stdio import MCPServer
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.unreal_material_variants import inspect_asset, inspect_native, plan_variant, create_variant
from test_cryptonyan_materials import png


class Object:
    def __init__(self, path, kind, **properties):
        self.path, self.kind, self.properties = path, kind, properties

    def get_class(self):
        return SimpleNamespace(get_name=lambda: self.kind)

    def get_path_name(self):
        return self.path

    def get_editor_property(self, name):
        return self.properties[name]

    def set_editor_property(self, name, value):
        self.properties[name] = value


class Task:
    def __init__(self):
        self.properties = {}

    def get_editor_property(self, name):
        return self.properties[name]

    def set_editor_property(self, name, value):
        self.properties[name] = value


class Editor:
    AssetImportTask = Task
    MaterialInstanceConstant = object
    MaterialInstanceConstantFactoryNew = object
    AssetRegistryDependencyOptions = SimpleNamespace
    TextureCompressionSettings = SimpleNamespace(TC_DEFAULT="default", TC_MASKS="masks", TC_NORMALMAP="normal")

    def __init__(self, project):
        self.root = project
        self.version, self.loading = "5.8.3-test", False
        self.objects, self.directories, self.dirty = {}, set(), []
        self.imports, self.saved, self.created = [], [], []
        self.bad_import, self.bad_parameter, self.save_failure, self.on_import = False, False, False, None
        self.SystemLibrary = SimpleNamespace(get_engine_version=lambda: self.version)
        self.Paths = SimpleNamespace(project_dir=lambda: str(project))
        self.AssetRegistryHelpers = SimpleNamespace(get_asset_registry=lambda: SimpleNamespace(
            is_loading_assets=lambda: self.loading, get_dependencies=lambda *args: ["/Game/Materials/M_Lantern", "/Script/Engine"],
            get_referencers=lambda *args: ["/Game/Maps/Garden"]))
        self.EditorLoadingAndSavingUtils = SimpleNamespace(get_dirty_content_packages=lambda: [Object(p, "Package") for p in self.dirty])
        self.EditorAssetLibrary = SimpleNamespace(does_directory_exist=lambda p: p in self.directories,
            list_assets=lambda dest, **kwargs: sorted(p for p in self.objects if p.startswith(dest + "/")),
            make_directory=self.reserve, save_loaded_asset=self.save)
        self.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(import_asset_tasks=self.import_tasks, create_asset=self.create_asset, duplicate_asset=self.duplicate_asset))
        mel = self.MaterialEditingLibrary = SimpleNamespace(set_material_instance_parent=lambda instance, parent: instance.set_editor_property("parent", parent),
            set_material_instance_texture_parameter_value=self.set_parameter, update_material_instance=lambda instance: None)
        for category in ("texture", "scalar", "vector"):
            setattr(mel, "get_" + category + "_parameter_names", lambda obj, c=category: list(self.parameters(obj, c)))
            for prefix in ("get_material_instance_", "get_material_default_"):
                setattr(mel, prefix + category + "_parameter_value", lambda obj, name, c=category: self.parameters(obj, c).get(name))

    def add(self, path, kind, **properties):
        obj = Object(path, kind, **properties)
        self.objects[path] = obj
        if path.startswith("/Game/"):
            file = self.root / ("Content/" + path.split(".")[0][len("/Game/"):] + ".uasset")
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(("opaque test package " + path).encode())
        return obj

    def load_asset(self, path):
        return self.objects.get(path)

    def parameters(self, obj, category):
        result = self.parameters(obj.properties["parent"], category) if obj.properties.get("parent") else {}
        return {**result, **obj.properties.get(category, {})}

    def reserve(self, path):
        self.directories.add(path)
        return True

    def import_tasks(self, tasks):
        for task in tasks:
            self.imports.append(copy.deepcopy(task.properties))
            props = task.properties
            path = props["destination_path"] + "/" + props["destination_name"] + "." + props["destination_name"]
            # An import creates unsaved editor objects, no synthetic on-disk originals.
            self.objects[path] = Object(path, "Texture2D", srgb=True, compression_settings="default", flip_green_channel=False, virtual_texture_streaming=False)
            task.properties["imported_object_paths"] = ["/Game/Existing.Wrong"] if self.bad_import else [path]
            if self.on_import:
                self.on_import()

    def create_asset(self, name, dest, cls, factory):
        path = dest + "/" + name + "." + name
        obj = Object(path, "MaterialInstanceConstant", parent=None, texture={})
        self.objects[path] = obj
        self.created.append(path)
        return obj

    def set_parameter(self, obj, name, value):
        if self.bad_parameter:
            return False
        obj.properties["texture"][name] = value
        return True

    def duplicate_asset(self, name, dest, source):
        path = dest + "/" + name + "." + name
        props = dict(source.properties)
        slots = "static_materials" if source.kind == "StaticMesh" else "materials"
        props[slots] = [Object(s.path, s.kind, **s.properties) for s in props[slots]]
        result = Object(path, source.kind, **props)
        self.objects[path] = result
        return result

    def save(self, obj, **kwargs):
        if self.save_failure:
            return False
        self.saved.append(obj.path)
        return True


class VariantTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "Game.uproject").write_text('{"FileVersion":3,"EngineAssociation":"5.8"}')
        self.u = Editor(self.game)
        self.texture = self.u.add("/Game/Textures/T_Paper.T_Paper", "Texture2D", srgb=True,
            compression_settings="default", flip_green_channel=False, virtual_texture_streaming=False)
        self.base = self.u.add("/Game/Materials/M_Lantern.M_Lantern", "Material", tangent_space_normal=True,
            use_material_attributes=False, texture={"PaperColor": self.texture, "PaperNormal": self.texture},
            scalar={"Glow": 2.0}, vector={"Tint": SimpleNamespace(r=1., g=.5, b=.2, a=1.)})
        self.parent = self.u.add("/Game/Materials/MI_Lantern.MI_Lantern", "MaterialInstanceConstant", parent=self.base, scalar={"Glow": 3.0})
        self.skeleton = self.u.add("/Game/Characters/SKEL_Example.SKEL_Example", "Skeleton")
        self.mesh = self.u.add("/Game/Props/SM_Lantern.SM_Lantern", "StaticMesh", static_materials=[
            Object("", "Slot", material_slot_name="Paper", material_interface=self.parent),
            Object("", "Slot", material_slot_name="Frame", material_interface=self.parent)])
        self.inspection = self.root / "inspection.json"
        self.candidate = self.root / "candidate.json"
        self.plan_file = self.root / "plan.json"
        self.report = self.root / "result.json"
        self.destination = "/Game/CryptoNyan/MaterialVariants/LanternRed"
        self.source = self.root / "images"
        self.source.mkdir()
        (self.source / "color.png").write_bytes(png())
        (self.source / "normal.png").write_bytes(png())
        pack_material(self.source, {"base_color": "color.png"}, self.root / "material")
        self.refresh()

    def refresh(self):
        report = inspect_native(self.mesh.path, self.u)
        write_json(self.inspection, report)
        write_json(self.candidate, {"schema": "cryptonyan.asset-texture-candidate/1", "target": report["source"],
            "project_identity": report["project_identity"], "texture": {"material_manifest": str(self.root / "material/material.json")}})

    def plan(self, **changes):
        result = plan_variant(self.inspection, self.candidate, **{**dict(slot=0, bindings={"base_color": "PaperColor"}, destination=self.destination), **changes})
        write_json(self.plan_file, result)
        return result

    def apply(self):
        return create_variant(self.plan_file, self.report, apply=True, unreal_module=self.u)

    def original_bytes(self):
        return {p.relative_to(self.game).as_posix(): digest(p) for p in self.game.rglob("*") if p.is_file()}

    def test_inspector_editor_classes_slots_parent_overrides_dependencies_and_sidecars(self):
        (self.game / "Content/Props/SM_Lantern.uexp").write_bytes(b"sidecar")
        before = self.original_bytes()
        output = inspect_asset(self.mesh.path, self.root / "read.json", unreal_module=self.u)
        self.assertEqual(output["class"], "StaticMesh")
        self.assertEqual([s["name"] for s in output["slots"]], ["Paper", "Frame"])
        self.assertEqual(output["slots"][0]["chain"][0]["parameters"]["scalar"]["Glow"], 3.0)
        self.assertEqual(len(output["package_files"]), 2)
        self.assertIn("/Game/Materials/M_Lantern", output["dependencies"])
        self.assertEqual(output["referencers"], ["/Game/Maps/Garden"])
        self.assertEqual(self.original_bytes(), before)
        self.assertFalse(self.u.saved or self.u.imports or self.u.created)

    def test_skeletal_mesh_keeps_skeleton_reference_without_deformation_claim(self):
        self.mesh.kind = "SkeletalMesh"
        self.mesh.properties["materials"] = self.mesh.properties.pop("static_materials")
        self.mesh.properties["skeleton"] = self.skeleton
        self.refresh()
        inspection = json.loads(self.inspection.read_text())
        self.assertEqual(inspection["skeleton"]["path"], self.skeleton.path)
        self.assertFalse(inspection["rig_deformation_validated"])
        self.plan()
        result = self.apply()
        self.assertEqual(result["status"], "created_review_required")
        self.assertIs(self.u.objects[result["preview_mesh"]].properties["skeleton"], self.skeleton)
        self.assertIs(self.mesh.properties["skeleton"], self.skeleton)

    def test_material_variant_preserves_slots_sources_parent_and_other_parameters(self):
        before = self.original_bytes()
        self.plan()
        result = self.apply()
        self.assertEqual(result["status"], "created_review_required", result)
        self.assertEqual(len(result["saved_assets"]), 3)
        instance = self.u.load_asset(result["material_instance"])
        self.assertIs(instance.properties["parent"], self.parent)
        self.assertEqual(self.u.parameters(instance, "scalar")["Glow"], 3.0)
        self.assertIs(self.u.parameters(instance, "texture")["PaperNormal"], self.texture)
        self.assertTrue(all(slot.properties["material_interface"] is self.parent for slot in self.mesh.properties["static_materials"]))
        preview_slots = self.u.objects[result["preview_mesh"]].properties["static_materials"]
        self.assertIs(preview_slots[0].properties["material_interface"], instance)
        self.assertIs(preview_slots[1].properties["material_interface"], self.parent)
        texture = self.u.parameters(instance, "texture")["PaperColor"]
        self.assertTrue(texture.properties["srgb"])
        self.assertFalse(texture.properties["flip_green_channel"])
        self.assertFalse(result["mesh_modified"] or result["level_saved"])
        self.assertEqual(self.original_bytes(), before)
        self.assertTrue(Path(result["input_snapshot"]).is_dir())
        self.assertFalse(self.u.imports[0]["save"] or self.u.imports[0]["replace_existing"])

    def test_normal_conversion_is_import_setting_once_and_png_bytes_are_preserved(self):
        pack_material(self.source, {"base_color": "color.png", "normal": "normal.png"}, self.root / "pbr")
        candidate = json.loads(self.candidate.read_text())
        candidate["texture"]["material_manifest"] = str(self.root / "pbr/material.json")
        write_json(self.candidate, candidate)
        self.plan(bindings={"base_color": "PaperColor", "normal": "PaperNormal"})
        result = self.apply()
        self.assertEqual(result["status"], "created_review_required", result)
        normal = self.u.objects[self.destination + "/T_normal.T_normal"]
        self.assertFalse(normal.properties["srgb"])
        self.assertTrue(normal.properties["flip_green_channel"])
        self.assertEqual(normal.properties["compression_settings"], "normal")
        self.assertEqual(digest(Path(result["input_snapshot"]) / "normal.png"), digest(self.source / "normal.png"))

    def test_invalid_slots_bindings_and_destinations_refused_offline(self):
        for changes in ({"slot": True}, {"slot": 3}, {"bindings": {}}, {"bindings": {"base_color": "Typo"}},
                        {"destination": "/Game/Existing"}, {"destination": self.destination + "/../Bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.plan(**changes)
        self.assertFalse(self.u.imports)

    def test_world_normals_layers_virtual_textures_and_empty_defaults_refused(self):
        self.texture.properties["virtual_texture_streaming"] = True
        self.refresh()
        with self.assertRaisesRegex(ValueError, "nonvirtual"):
            self.plan()
        self.texture.properties["virtual_texture_streaming"] = False
        self.base.properties["use_material_attributes"] = True
        self.refresh()
        with self.assertRaisesRegex(ValueError, "layers"):
            self.plan()
        self.base.properties["use_material_attributes"] = False
        self.base.properties["texture"]["PaperColor"] = None
        self.refresh()
        with self.assertRaisesRegex(ValueError, "Texture2D"):
            self.plan()
        self.base.properties["texture"]["PaperColor"] = self.texture
        self.base.properties["tangent_space_normal"] = False
        self.refresh()
        pack_material(self.source, {"base_color": "color.png", "normal": "normal.png"}, self.root / "world-normal")
        candidate = json.loads(self.candidate.read_text())
        candidate["texture"]["material_manifest"] = str(self.root / "world-normal/material.json")
        write_json(self.candidate, candidate)
        with self.assertRaisesRegex(ValueError, "tangent_space"):
            self.plan(bindings={"base_color": "PaperColor", "normal": "PaperNormal"})

    def test_candidate_from_another_asset_cannot_be_planned(self):
        candidate = json.loads(self.candidate.read_text())
        candidate["target"]["sha256"] = "a" * 64
        write_json(self.candidate, candidate)
        with self.assertRaisesRegex(ValueError, "does_not_match"):
            self.plan()

    def test_dirty_source_and_changed_live_material_block_before_import(self):
        self.u.dirty = [self.parent.path.split(".")[0]]
        self.refresh()
        with self.assertRaisesRegex(ValueError, "save_or_discard"):
            self.plan()
        self.u.dirty = []
        self.refresh()
        self.plan()
        self.parent.properties["scalar"]["Glow"] = 7.0
        self.assertEqual(self.apply()["error"], "source_or_inspection_changed")
        self.assertFalse(self.u.imports or self.u.directories)

    def test_changed_sidecar_and_source_file_block_before_import(self):
        for name in ("SM_Lantern.uasset", "SM_Lantern.ubulk"):
            with self.subTest(name=name):
                self.report.unlink(missing_ok=True)
                self.refresh()
                self.plan()
                (self.game / "Content/Props" / name).write_bytes(b"changed")
                self.assertEqual(self.apply()["error"], "source_or_inspection_changed")
                self.assertFalse(self.u.imports)

    def test_existing_destination_or_receipt_never_overwritten(self):
        self.plan()
        self.u.directories.add(self.destination)
        self.assertEqual(self.apply()["error"], "variant_destination_exists")
        self.assertFalse(self.u.imports)
        with self.assertRaises(FileExistsError):
            self.apply()

    def test_corrupt_bundle_and_plan_fail_before_editor_mutations(self):
        plan = self.plan()
        plan["parent"] = "/Game/Other.Other"
        write_json(self.plan_file, plan)
        with self.assertRaisesRegex(ValueError, "plan_or_inputs"):
            self.apply()
        self.plan()
        (self.root / "material/base_color.png").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.u.imports or self.report.exists())

    def test_import_escape_or_parameter_failure_retains_receipt_without_save(self):
        self.plan()
        self.u.bad_import = True
        result = self.apply()
        self.assertEqual(result["error"], "unexpected_texture_import_paths")
        self.assertFalse(result["saved_assets"])
        self.assertTrue(self.u.directories)
        self.assertTrue(Path(result["input_snapshot"]).exists())

    def test_parameter_assignment_and_save_failures_are_reported(self):
        self.plan()
        self.u.bad_parameter = True
        result = self.apply()
        self.assertEqual(result["error"], "texture_parameter_assignment_failed")
        self.assertFalse(self.u.saved)
        self.u.bad_parameter = False
        self.u.save_failure = True
        self.report = self.root / "second.json"
        self.destination = "/Game/CryptoNyan/MaterialVariants/Second"
        self.plan()
        result = self.apply()
        self.assertEqual(result["error"], "variant_save_failed")
        self.assertEqual(result["failed_stage"], "saving")

    def test_source_changed_during_import_prevents_saving(self):
        self.plan()
        self.u.on_import = lambda: self.parent.properties["scalar"].update(Glow=8.0)
        result = self.apply()
        self.assertEqual(result["error"], "source_or_inspection_changed")
        self.assertFalse(self.u.saved)

    def test_engine_loading_missing_asset_and_cycles_fail_read_only(self):
        for field, value in (("version", "5.7.0"), ("loading", True)):
            old = getattr(self.u, field)
            setattr(self.u, field, value)
            with self.assertRaises(ValueError):
                inspect_native(self.mesh.path, self.u)
            setattr(self.u, field, old)
        with self.assertRaises(ValueError):
            inspect_native("/Game/Missing.Missing", self.u)
        self.parent.properties["parent"] = self.parent
        with self.assertRaises(ValueError):
            inspect_native(self.mesh.path, self.u)
        self.assertFalse(self.u.imports or self.u.saved)

    def test_dry_run_needs_no_engine_and_reports_cannot_be_inside_game(self):
        self.plan()
        self.assertEqual(create_variant(self.plan_file, self.report)["status"], "planned")
        with self.assertRaisesRegex(ValueError, "outside_game"):
            create_variant(self.plan_file, self.game / "report.json")
        with self.assertRaisesRegex(ValueError, "outside_game"):
            inspect_asset(self.mesh.path, self.game / "report.json", unreal_module=self.u)
        self.assertFalse((self.game / "report.json").exists())

    def test_mcp_owned_plan_uses_verified_candidate_and_confined_inspection(self):
        workspace = self.root / "textures"
        workspace.mkdir()
        project = GameProject(self.game, SimpleNamespace(root=workspace))
        inspect_dir = workspace / "inspections"
        inspect_dir.mkdir()
        (inspect_dir / "lamp.json").write_bytes(self.inspection.read_bytes())
        candidate = json.loads(self.candidate.read_text())
        write_json(project.bindings / "lamp-01.candidate.json", candidate)
        write_json(project.bindings / "lamp-01.json", {"project_identity": candidate["project_identity"],
            "source": candidate["target"], "request": {"request_id": "lamp-01", "target": candidate["target"]["path"]}})
        args = dict(request_id="lamp-01", inspection="lamp.json", slot=0, bindings={"base_color": "PaperColor"}, variant_id="LampRed")
        server = MCPServer(None, project.textures, project)
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "project_material_plan", "arguments": args}})
        self.assertFalse(response["result"]["isError"], response)
        first = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(Path(first["plan_file"]).exists())
        self.assertEqual(project.material_plan(**args), first)
        with self.assertRaises(ValueError):
            project.material_plan(**{**args, "inspection": "../../inspection.json"})
        with self.assertRaisesRegex(ValueError, "different parameters"):
            project.material_plan(**{**args, "slot": 1})

    def test_actual_plan_and_dry_run_cli_need_no_unreal_module(self):
        bindings = self.root / "bindings.json"
        write_json(bindings, {"base_color": "PaperColor"})
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        command = [sys.executable, "-m", "cryptonyan_asset_studio.unreal_material_variants"]
        result = subprocess.run([*command, "plan", "--inspection", str(self.inspection), "--candidate", str(self.candidate),
            "--slot", "0", "--bindings", str(bindings), "--destination", self.destination, "--report", str(self.plan_file)],
            text=True, capture_output=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([*command, "create", str(self.plan_file), "--report", str(self.report)],
            text=True, capture_output=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")
        self.assertFalse(self.u.imports or self.u.saved)

    def test_parameter_success_without_effective_readback_blocks_saving(self):
        self.plan()
        getter = self.u.MaterialEditingLibrary.get_material_instance_texture_parameter_value
        self.u.MaterialEditingLibrary.get_material_instance_texture_parameter_value = lambda obj, name: self.texture if obj.path.endswith(".MI_Variant") else getter(obj, name)
        result = self.apply()
        self.assertEqual(result["error"], "texture_parameter_readback_failed")
        self.assertFalse(self.u.saved)


if __name__ == "__main__":
    unittest.main()
