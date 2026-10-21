# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect saved Unreal assets and create isolated material-instance candidates.

Run editor operations in the existing project's Python editor session. No map switch,
mesh edits, actor assignment, graph rewrites, original saves or remote RPC are used.
The injected Unreal module is for protocol tests, not engine compatibility evidence.
"""
import argparse
import hashlib
from itertools import islice
import json
import math
from pathlib import Path
import re

from .comfy_profiles import _read
from .game_project import GameProject, MAX_TARGET_BYTES
from .materials import load_material, pack_material
from .storage import digest, safe_path
from .unreal_review import ReviewError


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _object_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?", value):
        raise ReviewError("require_explicit_Game_asset_path")
    package, _, name = value.partition(".")
    if not name:
        name = package.rsplit("/", 1)[1]
    return package + "." + name


def _path(obj):
    return obj.get_path_name() if obj is not None else None


def _kind(obj):
    return obj.get_class().get_name() if obj is not None else None


def _runtime(u):
    version = str(u.SystemLibrary.get_engine_version())
    if not re.match(r"^5\.8(?:\.|-|$)", version):
        raise ReviewError("require_Unreal_5_8")
    project = GameProject(u.Paths.project_dir())
    return version, project


def _outside(path, project, *inputs):
    path = Path(path)
    if path.is_symlink() or path.resolve().is_relative_to(project.root):
        raise ReviewError("receipt_must_be_outside_game_project")
    if any(path.resolve().is_relative_to(Path(p).resolve()) for p in inputs):
        raise ReviewError("receipt_must_be_outside_input_bundle")
    return path


def _file_state(project, object_path):
    if not object_path.startswith("/Game/"):
        return None  # Engine/plugin dependency bytes are explicitly outside this scope.
    package = _object_path(object_path).split(".")[0]
    if package in project._inspection_files:
        return project._inspection_files[package]
    relative = "Content/" + package[len("/Game/"):] + ".uasset"
    size = safe_path(project.root, relative).stat().st_size
    if project._inspection_bytes + size > 1024 * 1024 * 1024:
        raise ReviewError("inspection_exceeds_1_GiB_file_budget")
    project._inspection_bytes += size
    primary = project._snapshot(relative)
    files, size = [primary], primary["bytes"]
    for suffix in (".uexp", ".ubulk"):
        path = safe_path(project.root, relative[:-7] + suffix)
        if path.exists():
            size += path.stat().st_size
            if size > MAX_TARGET_BYTES:
                raise ReviewError("package_files_exceed_512_MiB")
            project._inspection_bytes += path.stat().st_size
            if project._inspection_bytes > 1024 * 1024 * 1024:
                raise ReviewError("inspection_exceeds_1_GiB_file_budget")
            files.append({"path": path.relative_to(project.root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    project._inspection_files[package] = files
    return files


def _bounded(values, limit, message):
    values = list(islice(values, limit + 1))
    if len(values) > limit:
        raise ReviewError(message)
    return values


def _texture(texture, project):
    if texture is None:
        return None
    if _path(texture) in project._inspection_textures:
        return project._inspection_textures[_path(texture)]
    if len(project._inspection_textures) >= 256:
        raise ReviewError("too_many_inspected_textures")
    result = {"path": _path(texture), "class": _kind(texture), "files": _file_state(project, _path(texture))}
    if result["class"] == "Texture2D":
        result.update(srgb=bool(texture.get_editor_property("srgb")),
                      compression=str(texture.get_editor_property("compression_settings")),
                      virtual_texture_streaming=bool(texture.get_editor_property("virtual_texture_streaming")),
                      flip_green_channel=bool(texture.get_editor_property("flip_green_channel")))
    project._inspection_textures[_path(texture)] = result
    return result


def _material(material, u, project):
    original = _path(material)
    if original in project._inspection_materials:
        return project._inspection_materials[original]
    # Validate the chain BEFORE getters that can themselves traverse its parents.
    cursor, parents = material, set()
    while cursor is not None:
        identity, kind = _path(cursor), _kind(cursor)
        if identity in parents or len(parents) >= 16 or kind not in ("Material", "MaterialInstanceConstant"):
            raise ReviewError("unsupported_or_cyclic_material_parent_chain")
        parents.add(identity)
        next_parent = cursor.get_editor_property("parent") if kind == "MaterialInstanceConstant" else None
        if kind == "MaterialInstanceConstant" and next_parent is None:
            raise ReviewError("material_instance_missing_parent")
        cursor = next_parent
    chain, seen = [], set()
    while material is not None:
        path, kind = _path(material), _kind(material)
        if path in seen or len(chain) >= 16 or kind not in ("Material", "MaterialInstanceConstant"):
            raise ReviewError("unsupported_or_cyclic_material_parent_chain")
        seen.add(path)
        project._inspection_material_paths.add(path)
        if len(project._inspection_material_paths) > 64:
            raise ReviewError("too_many_inspected_materials")
        editing = u.MaterialEditingLibrary
        parameters = {}
        for category in ("texture", "scalar", "vector"):
            names = [str(n) for n in _bounded(getattr(editing, "get_" + category + "_parameter_names")(material), 64, "too_many_material_parameters")]
            if len(set(names)) != len(names):
                raise ReviewError("ambiguous_material_parameter_names")
            getter = getattr(editing, ("get_material_instance_" if kind == "MaterialInstanceConstant" else "get_material_default_") + category + "_parameter_value")
            values = {}
            for name in sorted(names):
                value = getter(material, name)
                if category == "texture":
                    values[name] = _texture(value, project)
                elif category == "scalar":
                    values[name] = float(value)
                else:
                    values[name] = [float(getattr(value, axis)) for axis in ("r", "g", "b", "a")]
                if category != "texture" and not all(math.isfinite(v) for v in (values[name] if isinstance(values[name], list) else [values[name]])):
                    raise ReviewError("nonfinite_material_parameter")
            parameters[category] = values
        parent = material.get_editor_property("parent") if kind == "MaterialInstanceConstant" else None
        row = {"path": path, "class": kind, "parent": _path(parent), "parameters": parameters,
               "files": _file_state(project, path)}
        if kind == "Material":
            row["tangent_space_normal"] = bool(material.get_editor_property("tangent_space_normal"))
            row["use_material_attributes"] = bool(material.get_editor_property("use_material_attributes"))
        elif parent is None:
            raise ReviewError("material_instance_missing_parent")
        chain.append(row)
        material = parent
    project._inspection_materials[original] = chain
    return chain


def inspect_native(asset_path, u):
    """Deterministic read-only report; no generated timestamps in the comparison."""
    version, project = _runtime(u)
    project._inspection_files, project._inspection_bytes = {}, 0
    project._inspection_textures, project._inspection_materials = {}, {}
    project._inspection_material_paths = set()
    path = _object_path(asset_path)
    obj = u.load_asset(path)
    if obj is None or _path(obj) != path:
        raise ReviewError("missing_asset_or_redirector")
    registry = u.AssetRegistryHelpers.get_asset_registry()
    if registry.is_loading_assets():
        raise ReviewError("wait_for_asset_registry_loading")
    package = path.split(".")[0]
    options = u.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True,
        include_searchable_names=False, include_soft_management_references=False, include_hard_management_references=False)
    dependencies = sorted(str(x) for x in _bounded(registry.get_dependencies(package, options), 2048, "too_many_dependencies"))
    referencers = sorted(str(x) for x in _bounded(registry.get_referencers(package, options), 2048, "too_many_referencers"))
    kind, slots = _kind(obj), []
    skeleton = obj.get_editor_property("skeleton") if kind in ("SkeletalMesh", "AnimSequence") else None
    if kind in ("StaticMesh", "SkeletalMesh"):
        entries = _bounded(obj.get_editor_property("static_materials" if kind == "StaticMesh" else "materials"), 32, "too_many_material_slots")
        for index, entry in enumerate(entries):
            material = entry.get_editor_property("material_interface")
            slots.append({"index": index, "name": str(entry.get_editor_property("material_slot_name")),
                          "material": _path(material), "chain": _material(material, u, project)})
    files = _file_state(project, path)
    watched = {package, *dependencies}
    for slot in slots:
        for row in slot["chain"]:
            watched.add(row["path"].split(".")[0])
            watched.update(v["path"].split(".")[0] for v in row["parameters"]["texture"].values() if v)
    if skeleton is not None:
        watched.add(_path(skeleton).split(".")[0])
    dirty = sorted(p.get_path_name() for p in u.EditorLoadingAndSavingUtils.get_dirty_content_packages() if p.get_path_name() in watched)
    return {"schema": "cryptonyan.unreal-asset-inspection/1", "engine_version": version,
            "project_file": str(project.descriptor),
            "project_identity": project._project_identity(), "asset": path, "class": kind,
            "source": files[0], "package_files": files, "slots": slots,
            "skeleton": {"path": _path(skeleton), "files": _file_state(project, _path(skeleton))} if skeleton else None,
            "material": _material(obj, u, project) if kind in ("Material", "MaterialInstanceConstant") else None,
            "texture": _texture(obj, project) if kind == "Texture2D" else None,
            "dependencies": dependencies, "referencers": referencers, "dirty_packages": dirty,
            "dependency_scope": "direct_package_references", "rig_deformation_validated": False,
            "nonparameter_texture_graphs_inspected": False, "engine_dependency_bytes_hashed": False}


def inspect_asset(asset_path, report_path, *, unreal_module=None):
    if unreal_module is None:
        import unreal as unreal_module
    _, project = _runtime(unreal_module)
    report = _outside(report_path, project)
    # Reserve before reading so failed inspections also retain a diagnostic.
    with report.open("x", encoding="utf-8") as stream:
        try:
            result = inspect_native(asset_path, unreal_module)
        except Exception as error:
            result = {"schema": "cryptonyan.unreal-inspection-failure/1", "error": str(error) if isinstance(error, ReviewError) else type(error).__name__}
            raise
        finally:
            stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def plan_variant(inspection_path, candidate_path, slot, bindings, destination):
    inspection = _read(Path(inspection_path), 16 * 1024 * 1024)
    candidate = _read(Path(candidate_path))
    if inspection.get("schema") != "cryptonyan.unreal-asset-inspection/1" or inspection.get("class") not in ("StaticMesh", "SkeletalMesh"):
        raise ReviewError("require_mesh_inspection")
    if candidate.get("schema") != "cryptonyan.asset-texture-candidate/1" or candidate.get("target") != inspection["source"] or candidate.get("project_identity") != inspection["project_identity"]:
        raise ReviewError("candidate_does_not_match_inspected_asset")
    if inspection["dirty_packages"]:
        raise ReviewError("save_or_discard_source_edits_before_planning")
    if type(slot) is not int or not 0 <= slot < len(inspection["slots"]):
        raise ReviewError("invalid_material_slot_index")
    selected = inspection["slots"][slot]
    chain = selected["chain"]
    if selected["index"] != slot or not chain or chain[0]["path"] != selected["material"]:
        raise ReviewError("slot_missing_supported_material")
    material_path = Path(candidate["texture"]["material_manifest"])
    material = load_material(material_path)
    if not isinstance(bindings, dict) or set(bindings) != set(material["channels"]):
        raise ReviewError("explicit_binding_required_for_every_texture_channel")
    names = chain[0]["parameters"]["texture"]
    if any(not isinstance(v, str) or not 1 <= len(v) <= 128 or "\x00" in v or v not in names for v in bindings.values()):
        raise ReviewError("unknown_texture_parameter")
    if len(set(bindings.values())) != len(bindings):
        raise ReviewError("texture_channels_require_distinct_parameters")
    if any(names[v] is None or names[v]["class"] != "Texture2D" or names[v].get("virtual_texture_streaming") for v in bindings.values()):
        raise ReviewError("require_existing_nonvirtual_Texture2D_parameters")
    if chain[-1].get("use_material_attributes"):
        raise ReviewError("material_attributes_and_layers_require_separate_adapter")
    if "normal" in bindings and not chain[-1].get("tangent_space_normal"):
        raise ReviewError("normal_requires_tangent_space_parent")
    if not isinstance(destination, str) or not re.fullmatch(r"/Game/CryptoNyan/MaterialVariants/[A-Za-z0-9_]{1,64}", destination):
        raise ReviewError("require_new_material_variant_destination")
    return {"schema": "cryptonyan.material-variant-plan/1",
            "project_root": str(Path(inspection["project_file"]).parent),
            "project_identity": inspection["project_identity"],
            "inspection_file": str(Path(inspection_path).resolve()), "candidate_file": str(Path(candidate_path).resolve()),
            "inspection_sha256": _hash(inspection), "candidate_sha256": digest(candidate_path),
            "asset": _object_path(inspection["asset"]), "source": inspection["source"], "slot": slot,
            "mesh_class": inspection["class"],
            "parent": selected["material"], "bindings": bindings, "destination": destination,
            "material_manifest": str(material_path.resolve()), "material": material,
            "assign_to_source_mesh": False, "create_preview_mesh": True,
            "save_originals": False, "visual_quality_validated": False}


def _load_plan(path):
    plan = _read(Path(path), 16 * 1024 * 1024)
    if plan.get("schema") != "cryptonyan.material-variant-plan/1" or plan != plan_variant(
            plan["inspection_file"], plan["candidate_file"], plan["slot"], plan["bindings"], plan["destination"]):
        raise ReviewError("plan_or_inputs_changed")
    return plan


def create_variant(plan_path, report_path, *, apply=False, unreal_module=None):
    """Create textures, a MIC and a preview mesh copy; leave source assets alone.

    Use a single owner/editor. Partial folders and receipts are retained, never deleted
    or reused. Dry run validates local inputs without importing Unreal or writing game data.
    """
    if type(apply) is not bool:
        raise ValueError("apply must be boolean")
    plan = _load_plan(plan_path)
    report = _outside(report_path, GameProject(plan["project_root"]))
    # No writes into either the source bundle or the plan/inspection/candidate files.
    if report.is_symlink() or report.resolve().is_relative_to(Path(plan["material_manifest"]).parent) or report.resolve() in {
            Path(p).resolve() for p in (plan_path, plan["inspection_file"], plan["candidate_file"])}:
        raise ReviewError("invalid_variant_receipt_path")
    u = unreal_module
    if apply:
        if u is None:
            import unreal as u
        _, project = _runtime(u)
        report = _outside(report, project)
    receipt = {"schema": "cryptonyan.material-variant-result/1", "status": "planned", "plan": plan,
               "owned_assets": [], "saved_assets": [], "mesh_modified": False, "level_saved": False,
               "visual_quality_validated": False}
    with report.open("x", encoding="utf-8") as stream:
        try:
            if not apply:
                return receipt
            def unchanged():
                if _load_plan(plan_path) != plan or _hash(inspect_native(plan["asset"], u)) != plan["inspection_sha256"]:
                    raise ReviewError("source_or_inspection_changed")
            unchanged()
            lib, editing = u.EditorAssetLibrary, u.MaterialEditingLibrary
            destination = plan["destination"]
            if lib.does_directory_exist(destination) or lib.list_assets(destination, recursive=True, include_folder=False):
                raise ReviewError("variant_destination_exists")
            # Keep immutable source images for later UE reimport, outside the project.
            inputs = report.with_name(report.stem + "-inputs")
            pack_material(Path(plan["material_manifest"]).parent,
                          {role: item["file"] for role, item in plan["material"]["channels"].items()}, inputs)
            receipt["input_snapshot"] = str(inputs.resolve())
            if load_material(inputs / "material.json") != plan["material"]:
                raise ReviewError("texture_snapshot_changed")
            unchanged()
            if not lib.make_directory(destination):
                raise ReviewError("variant_reservation_failed")
            receipt["status"] = "importing"
            textures = {}
            tools = u.AssetToolsHelpers.get_asset_tools()
            for role in plan["bindings"]:
                task = u.AssetImportTask()
                name = "T_" + role
                for key, value in {"filename": str((inputs / (role + ".png")).resolve()), "destination_path": destination,
                        "destination_name": name, "automated": True, "replace_existing": False,
                        "replace_existing_settings": False, "save": False, "async_": False}.items():
                    task.set_editor_property(key, value)
                tools.import_asset_tasks([task])
                expected = destination + "/" + name + "." + name
                paths = [_object_path(p) for p in _bounded(task.get_editor_property("imported_object_paths"), 16, "unexpected_texture_import_count")]
                if paths != [expected]:
                    receipt["unexpected_import_paths"] = paths[:32]
                    raise ReviewError("unexpected_texture_import_paths")
                receipt["owned_assets"].append(expected)
                texture = u.load_asset(expected)
                if _kind(texture) != "Texture2D" or _path(texture) != expected:
                    raise ReviewError("unexpected_texture_import_class")
                compression = getattr(u.TextureCompressionSettings, "TC_NORMALMAP" if role == "normal" else "TC_DEFAULT" if role == "base_color" else "TC_MASKS")
                settings = {"srgb": role == "base_color", "compression_settings": compression,
                            "flip_green_channel": role == "normal"}
                for key, value in settings.items():
                    texture.set_editor_property(key, value)
                    if texture.get_editor_property(key) != value:
                        raise ReviewError("texture_settings_readback_failed")
                textures[role] = texture
            unchanged()
            receipt["status"] = "creating_instance"
            parent = u.load_asset(plan["parent"])
            instance = tools.create_asset("MI_Variant", destination, u.MaterialInstanceConstant, u.MaterialInstanceConstantFactoryNew())
            expected = destination + "/MI_Variant.MI_Variant"
            if _kind(instance) != "MaterialInstanceConstant" or _path(instance) != expected:
                raise ReviewError("material_instance_creation_failed")
            receipt["owned_assets"].append(expected)
            editing.set_material_instance_parent(instance, parent)
            if _path(instance.get_editor_property("parent")) != plan["parent"]:
                raise ReviewError("material_parent_readback_failed")
            for role, parameter in plan["bindings"].items():
                if not editing.set_material_instance_texture_parameter_value(instance, parameter, textures[role]):
                    raise ReviewError("texture_parameter_assignment_failed")
            editing.update_material_instance(instance)
            for role, parameter in plan["bindings"].items():
                if _path(editing.get_material_instance_texture_parameter_value(instance, parameter)) != _path(textures[role]):
                    raise ReviewError("texture_parameter_readback_failed")
            original = _read(Path(plan["inspection_file"]), 16 * 1024 * 1024)["slots"][plan["slot"]]["chain"][0]["parameters"]
            for category in ("scalar", "vector", "texture"):
                getter = getattr(editing, "get_material_instance_" + category + "_parameter_value")
                for name, value in original[category].items():
                    if category == "texture" and name in plan["bindings"].values():
                        continue
                    actual = getter(instance, name)
                    expected_value = value
                    if category == "texture":
                        actual, expected_value = _path(actual), value["path"] if value else None
                    elif category == "vector":
                        actual = [float(getattr(actual, axis)) for axis in ("r", "g", "b", "a")]
                    if actual != expected_value:
                        raise ReviewError("inherited_parameter_changed")
            receipt["status"] = "creating_preview"
            original_inspection = _read(Path(plan["inspection_file"]), 16 * 1024 * 1024)
            preview_name = "SM_Preview" if plan["mesh_class"] == "StaticMesh" else "SK_Preview"
            preview = tools.duplicate_asset(preview_name, destination, u.load_asset(plan["asset"]))
            preview_path = destination + "/" + preview_name + "." + preview_name
            if _kind(preview) != plan["mesh_class"] or _path(preview) != preview_path:
                raise ReviewError("preview_mesh_duplication_failed")
            receipt["owned_assets"].append(preview_path)
            property_name = "static_materials" if plan["mesh_class"] == "StaticMesh" else "materials"
            preview_slots = list(preview.get_editor_property(property_name))
            if len(preview_slots) != len(original_inspection["slots"]):
                raise ReviewError("preview_slot_count_changed")
            preview_slots[plan["slot"]].set_editor_property("material_interface", instance)
            preview.set_editor_property(property_name, preview_slots)
            for index, (entry, original_slot) in enumerate(zip(preview.get_editor_property(property_name), original_inspection["slots"])):
                wanted = _path(instance) if index == plan["slot"] else original_slot["material"]
                if _path(entry.get_editor_property("material_interface")) != wanted or str(entry.get_editor_property("material_slot_name")) != original_slot["name"]:
                    raise ReviewError("preview_slot_readback_failed")
            if plan["mesh_class"] == "SkeletalMesh" and _path(preview.get_editor_property("skeleton")) != original_inspection["skeleton"]["path"]:
                raise ReviewError("preview_skeleton_changed")
            expected_assets = set(receipt["owned_assets"])
            actual = {_object_path(p) for p in _bounded(lib.list_assets(destination, recursive=True, include_folder=False), 16, "unexpected_variant_asset_count")}
            if actual != expected_assets:
                raise ReviewError("unexpected_assets_in_variant_folder")
            if load_material(inputs / "material.json") != plan["material"]:
                raise ReviewError("texture_snapshot_changed")
            unchanged()
            receipt["status"] = "saving"
            for obj in [*textures.values(), instance, preview]:
                if not lib.save_loaded_asset(obj, only_if_is_dirty=False):
                    raise ReviewError("variant_save_failed")
                receipt["saved_assets"].append(_path(obj))
            unchanged()
            receipt["status"] = "created_review_required"
            receipt["material_instance"] = expected
            receipt["preview_mesh"] = preview_path
            return receipt
        except Exception as error:
            receipt["failed_stage"], receipt["status"] = receipt["status"], "failed"
            receipt["error"] = str(error) if isinstance(error, ReviewError) else type(error).__name__
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect Unreal assets and prepare isolated material variants")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Run inside Unreal Python; read saved asset metadata")
    inspect.add_argument("asset")
    inspect.add_argument("--report", type=Path, required=True)
    plan = commands.add_parser("plan", help="Prepare a variant plan outside Unreal from local receipts")
    plan.add_argument("--inspection", type=Path, required=True)
    plan.add_argument("--candidate", type=Path, required=True)
    plan.add_argument("--slot", type=int, required=True)
    plan.add_argument("--bindings", type=Path, required=True, help="JSON channel-to-existing-texture-parameter mapping")
    plan.add_argument("--destination", required=True)
    plan.add_argument("--report", type=Path, required=True)
    create = commands.add_parser("create", help="Dry-run outside Unreal; --apply requires Unreal Python")
    create.add_argument("plan", type=Path)
    create.add_argument("--report", type=Path, required=True)
    create.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "inspect":
        result = inspect_asset(args.asset, args.report)
    elif args.command == "plan":
        result = plan_variant(args.inspection, args.candidate, args.slot, _read(args.bindings), args.destination)
        report = _outside(args.report, GameProject(result["project_root"]), Path(result["material_manifest"]).parent)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    else:
        result = create_variant(args.plan, args.report, apply=args.apply)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
