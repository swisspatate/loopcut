# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit in-editor GLB import into a new review folder. Engine execution is opt-in.

No network, subprocess, remote editor control, reimport or overwrite. The injected
Unreal module allows protocol tests; those tests do not establish UE 5.8 compatibility.
"""
import json
import math
from pathlib import Path
import re

from .publication import load_package, review_destination
from .storage import digest, safe_path


class ReviewError(ValueError):
    """Fixed public preflight/import diagnostics, never raw engine exception text."""


def plan_import(manifest_path):
    package = load_package(manifest_path)
    return {"schema": "cryptonyan.import-plan/1", "package_id": package["package_id"],
            "manifest_sha256": digest(manifest_path), "destination": review_destination(package),
            "source": str(safe_path(Path(manifest_path).parent, package["asset"]["file"])),
            "asset_name": package["asset"]["name"], "replace_existing": False,
            "save_after_validation": True, "target_engine": "5.8", "asset": package["asset"]}


def probe(unreal):
    version = str(unreal.SystemLibrary.get_engine_version())
    symbols = ("AssetImportTask", "AssetToolsHelpers", "EditorAssetLibrary", "StaticMesh",
               "StaticMeshEditorSubsystem", "get_editor_subsystem", "load_asset")
    missing = [name for name in symbols if not hasattr(unreal, name)]
    if not missing:
        subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        missing += ["StaticMeshEditorSubsystem." + name for name in (
            "get_lod_count", "remove_collisions", "get_simple_collision_count", "get_convex_collision_count")
            if not callable(getattr(subsystem, name, None))]
        missing += ["StaticMesh." + name for name in ("get_num_triangles", "get_bounding_box")
                    if not callable(getattr(unreal.StaticMesh, name, None))]
    return {"schema": "cryptonyan.unreal-probe/1", "engine_version": version,
            "target_version_matches": bool(re.match(r"^5\.8(?:\.|-|$)", version)),
            "missing_apis": missing, "importer_verified": False,
            "note": "Enable Python Editor Script, Editor Scripting Utilities and glTF/Interchange import support; validate with the fixture."}


def _vector(value):
    result = [float(value.x), float(value.y), float(value.z)]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Nonfinite editor bounds")
    return result


def validate_mesh(unreal, mesh, item):
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    box = mesh.get_bounding_box()
    bounds = [_vector(box.min), _vector(box.max)]
    lo, hi = item["bounds_blender_m"]
    # glTF Y-up/RH -> UE Z-up/LH: (Blender x, -Blender y, Blender z), metres -> cm.
    expected = [[100 * lo[0], -100 * hi[1], 100 * lo[2]],
                [100 * hi[0], -100 * lo[1], 100 * hi[2]]]
    errors = []
    if any(abs(a - b) > max(0.1, abs(b) * 0.001) for av, bv in zip(bounds, expected) for a, b in zip(av, bv)):
        errors.append("bounds_or_axis_mismatch")
    triangles = mesh.get_num_triangles(0)
    if triangles != item["triangles"]:
        errors.append("triangle_count_mismatch")
    lods = subsystem.get_lod_count(mesh)
    if lods != 1:
        errors.append("unexpected_lods")
    materials = mesh.get_editor_property("static_materials")
    if len(materials) != item["material_count"] or any(m.get_editor_property("material_interface") is None for m in materials):
        errors.append("missing_material_binding")
    collision_count = subsystem.get_simple_collision_count(mesh) + subsystem.get_convex_collision_count(mesh)
    if collision_count != 0:
        errors.append("unexpected_collision")
    return {"passed": not errors, "errors": errors, "triangles": triangles, "lods": lods,
            "bounds_cm": bounds, "expected_bounds_cm": expected, "material_slots": len(materials),
            "collision_count": collision_count,
            "visual_quality": "not_evaluated", "material_appearance": "requires_visual_review"}


def run_review_import(manifest_path, report_path, *, apply=False, unreal_module=None):
    """Run inside Unreal, or plan outside it. One writer/editor must own the destination.

    Receipt is created exclusively before mutations. Failed imports retain their owned
    folder for inspection; no rollback/deletion is attempted. A retry cannot overwrite it.
    """
    if type(apply) is not bool:
        raise ValueError("apply must be a boolean")
    if Path(manifest_path).is_symlink():
        raise ValueError("Manifest symlinks are not allowed")
    manifest = Path(manifest_path).resolve(strict=True)
    report_path = Path(report_path)
    # Never let a receipt overwrite or become part of the immutable input bundle.
    if report_path.is_symlink() or report_path.parent.resolve().is_relative_to(manifest.parent):
        raise ValueError("Write the receipt outside the publication bundle")
    plan = plan_import(manifest)
    receipt = {"schema": "cryptonyan.unreal-import/1", "plan": plan, "apply": apply,
               "status": "planned", "saved": [], "owned_assets": [], "validation": None}
    with report_path.open("x", encoding="utf-8") as stream:
        reserved = False
        try:
            if unreal_module is None and apply:
                import unreal as unreal_module
            if unreal_module is not None:
                receipt["probe"] = probe(unreal_module)
            if not apply:
                return receipt
            unreal = unreal_module
            if receipt["probe"]["missing_apis"] or not receipt["probe"]["target_version_matches"]:
                raise ReviewError("unsupported_runtime: require Unreal 5.8 and the APIs listed by probe")
            library = unreal.EditorAssetLibrary
            destination = plan["destination"]
            if library.does_directory_exist(destination) or library.list_assets(destination, recursive=True, include_folder=False):
                raise ReviewError("destination_exists: inspect the existing review folder; automatic replacement is disabled")
            # Verify again immediately before crossing the editor mutation boundary.
            if plan_import(manifest) != plan:
                raise ReviewError("publication_changed: regenerate the plan from an intact bundle")
            if not library.make_directory(destination):
                raise ReviewError("reservation_failed: cannot create review folder")
            reserved = True
            receipt["status"] = "importing"
            task = unreal.AssetImportTask()
            for name, value in {"filename": plan["source"], "destination_path": destination,
                                "destination_name": plan["asset_name"], "automated": True,
                                "replace_existing": False, "replace_existing_settings": False,
                                "save": False, "async_": False}.items():
                task.set_editor_property(name, value)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            paths = sorted(set(task.get_editor_property("imported_object_paths")) |
                           set(library.list_assets(destination, recursive=True, include_folder=False)))
            if not paths or any(not p.startswith(destination + "/") or not re.fullmatch(
                    r"[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*(?:\.[A-Za-z0-9_]+)?", p[len(destination) + 1:]) for p in paths):
                raise ReviewError("import_result_invalid: check glTF/Interchange support and returned asset paths")
            receipt["owned_assets"] = paths
            objects = [unreal.load_asset(p) for p in paths]
            if any(obj is None or obj.get_class().get_name() not in (
                    "StaticMesh", "Material", "MaterialInstanceConstant") for obj in objects):
                raise ReviewError("unsupported_assets: this importer accepts one static mesh and its materials")
            meshes = [obj for obj in objects if isinstance(obj, unreal.StaticMesh)]
            if len(meshes) != 1:
                raise ReviewError("mesh_count_mismatch: expected exactly one static mesh")
            mesh = meshes[0]
            # Only the newly created review mesh is modified; source-only LOD and no
            # generated collision are explicit publication policies, not game-ready claims.
            unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(mesh)
            receipt["validation"] = validate_mesh(unreal, mesh, plan["asset"])
            if not receipt["validation"]["passed"]:
                raise ReviewError("validation_failed: inspect the measured differences in the receipt")
            if plan_import(manifest) != plan:
                raise ReviewError("publication_changed: bundle changed during import; no save attempted")
            receipt["status"] = "saving"
            for path, obj in zip(paths, objects):
                if not library.save_loaded_asset(obj, only_if_is_dirty=False):
                    raise ReviewError("save_failed: inspect saved and owned_assets before retrying")
                receipt["saved"].append(path)
            receipt["status"] = "imported"
            return receipt
        except Exception as error:
            receipt["failed_stage"] = receipt["status"]
            receipt["status"] = "failed"
            receipt["error"] = str(error) if isinstance(error, ReviewError) else type(error).__name__
            receipt["partial_review_folder"] = reserved
            # Raw engine diagnostics can contain local paths/account data; the editor
            # log remains available locally, while the receipt stores measured fields.
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
            stream.flush()
