# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit empty-review-level placement using the independent CryptoNyan runtime actor."""
import argparse
import json
from pathlib import Path
import re

from .runner_kit import read_json
from .runner_motion import position_at
from .unreal_review import ReviewError, probe, validate_mesh, _vector
from .world_assembly import plan_world


def expected_location(item, seconds=0):
    placement = {"origin_m": [v/100 for v in item["origin_cm"]], "motion": {
        "fps": 30, "amplitude_m": item["amplitude_cm"]/100,
        "period_frames": item["period_seconds"]*30, "phase_frames": item["phase_seconds"]*30}}
    return [v*100 for v in position_at(placement, seconds)]


def sample_runtime(plan, *, unreal_module=None):
    """Read-only PIE pose sample. This measures positions, not rider/collision gameplay."""
    from .procedural_level_builder import _hash
    if not isinstance(plan, dict) or plan.get("world_id") != _hash({k: v for k, v in plan.items() if k != "world_id"}):
        raise ValueError("World plan identity changed")
    if unreal_module is None:
        import unreal as unreal_module
    unreal = unreal_module
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    if world is None:
        raise ReviewError("play_in_editor_required")
    expected = {a["id"]: a for a in plan["actors"]}
    found, rows, errors = set(), [], []
    tag = "cryptonyan:" + plan["world_id"]
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.CryptoNyanPlatform):
        tags = [str(t) for t in actor.get_editor_property("tags")]
        if tag not in tags:
            continue
        ids = [t.removeprefix("cryptonyan-item:") for t in tags if t.startswith("cryptonyan-item:")]
        if len(ids) != 1 or ids[0] not in expected or ids[0] in found:
            errors.append("unknown_or_duplicate_actor")
            continue
        identity = ids[0]
        found.add(identity)
        seconds = actor.get_motion_elapsed_seconds()
        wanted = expected_location(expected[identity], seconds)
        actual = _vector(actor.get_actor_location())
        delta = max(abs(a-b) for a, b in zip(actual, wanted))
        rows.append({"id": identity, "elapsed_seconds": seconds, "error_cm": delta, "passed": delta <= 2.0})
    missing = sorted(set(expected) - found)
    return {"schema": "cryptonyan.runtime-sample/1", "world_id": plan["world_id"],
            "sampled_pose_passed": bool(rows) and not errors and not missing and all(r["passed"] for r in rows),
            "missing": missing, "errors": errors, "samples": rows, "tolerance_cm": 2.0,
            "controller_validated": False, "collision_validated": False}


def _make_material(unreal, destination, name, biome):
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_" + name, destination, unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        raise ReviewError("material_creation_failed")
    editor = unreal.MaterialEditingLibrary
    color = editor.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -300, 0)
    rough = editor.create_material_expression(material, unreal.MaterialExpressionConstant, -300, 150)
    if color is None or rough is None:
        raise ReviewError("material_expression_failed")
    color.set_editor_property("constant", unreal.LinearColor(*biome["color_linear"], 1.0))
    rough.set_editor_property("r", biome["roughness"])
    if (not editor.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR) or
            not editor.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)):
        raise ReviewError("material_connection_failed")
    editor.recompile_material(material)
    return material


def run_world_review(recipe, source_root, report_path, *, apply=False, target_level=None, unreal_module=None):
    if type(apply) is not bool:
        raise ValueError("apply must be boolean")
    root = Path(source_root).resolve(strict=True)
    report = Path(report_path)
    if report.is_symlink() or report.parent.resolve().is_relative_to(root):
        raise ValueError("Place the exclusive review receipt outside the immutable kit root")
    plan = plan_world(recipe, root)
    destination = "/Game/CryptoNyan/WorldReviews/W_" + plan["world_id"][:16]
    receipt = {"schema": "cryptonyan.world-review/1", "world_id": plan["world_id"], "plan": plan,
               "apply": apply, "target_level": target_level, "destination": destination, "status": "planned",
               "owned_actors": [], "owned_materials": [], "saved_materials": [], "level_saved": False,
               "engine_validated": False, "dynamics_validated": False}
    with report.open("x", encoding="utf-8") as stream:
        try:
            if not apply:
                return receipt
            if not isinstance(target_level, str) or not re.fullmatch(r"/Game/CryptoNyan/ReviewMaps/[A-Za-z0-9_]+", target_level):
                raise ReviewError("require_explicit_review_map: save/open an empty map under /Game/CryptoNyan/ReviewMaps")
            if unreal_module is None:
                import unreal as unreal_module
            unreal = unreal_module
            runtime = probe(unreal)
            required = ("CryptoNyanPlatform", "EditorActorSubsystem", "UnrealEditorSubsystem", "Vector",
                        "Material", "MaterialFactoryNew", "MaterialEditingLibrary", "MaterialExpressionConstant3Vector",
                        "MaterialExpressionConstant", "MaterialProperty", "LinearColor", "Name")
            if runtime["missing_apis"] or not runtime["target_version_matches"] or any(not hasattr(unreal, k) for k in required):
                raise ReviewError("unsupported_runtime: require UE 5.8, editor Python and the compiled CryptoNyanRuntime plugin")
            if any(not callable(getattr(unreal.CryptoNyanPlatform, k, None)) for k in
                   ("configure_platform", "get_motion_elapsed_seconds")):
                raise ReviewError("runtime_plugin_api_mismatch")
            for method in ("create_material_expression", "connect_material_property", "recompile_material"):
                if not callable(getattr(unreal.MaterialEditingLibrary, method, None)):
                    raise ReviewError("missing_material_api")
            editor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            if any(not callable(getattr(editor, k, None)) for k in ("get_all_level_actors", "spawn_actor_from_class")):
                raise ReviewError("missing_actor_editor_api")
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            if world is None or world.get_path_name() != target_level + "." + target_level.rsplit("/", 1)[1]:
                raise ReviewError("wrong_current_map: no level switch or save is performed automatically")
            if any(a.get_class().get_name() != "WorldSettings" for a in editor.get_all_level_actors()):
                raise ReviewError("review_map_not_empty: use a new empty map")
            library = unreal.EditorAssetLibrary
            if library.does_directory_exist(destination) or library.list_assets(destination, recursive=True, include_folder=False):
                raise ReviewError("review_destination_exists")
            meshes = {}
            for identity, module in plan["modules"].items():
                imported = module["import"]
                path = imported["destination"] + "/" + imported["asset_name"]
                mesh = unreal.load_asset(path)
                if not isinstance(mesh, unreal.StaticMesh) or not validate_mesh(unreal, mesh, imported["asset"])["passed"]:
                    raise ReviewError("module_missing_or_invalid: import each module using its existing review importer first")
                meshes[identity] = mesh
            if plan_world(recipe, root) != plan:
                raise ReviewError("world_inputs_changed")
            if not library.make_directory(destination):
                raise ReviewError("world_reservation_failed")
            receipt["status"] = "creating_materials"
            materials = {}
            for name, biome in plan["recipe"]["biomes"].items():
                receipt["owned_materials"].append(destination + "/M_" + name)
                materials[name] = _make_material(unreal, destination, name, biome)
            receipt["status"] = "placing"
            for item in plan["actors"]:
                actor = editor.spawn_actor_from_class(unreal.CryptoNyanPlatform, unreal.Vector(*item["origin_cm"]))
                if actor is None:
                    raise ReviewError("actor_spawn_failed")
                receipt["owned_actors"].append(actor.get_path_name())
                actor.set_actor_label("CN_" + item["id"])
                actor.set_editor_property("tags", [unreal.Name("cryptonyan:" + plan["world_id"]),
                                                   unreal.Name("cryptonyan-item:" + item["id"])])
                actor.set_actor_scale3d(unreal.Vector(*item["scale"]))
                if not actor.configure_platform(meshes[item["module"]], materials[item["biome"]],
                    unreal.Vector(*item["origin_cm"]), item["collision"], item["amplitude_cm"],
                    item["period_seconds"], item["phase_seconds"]):
                    raise ReviewError("actor_configuration_failed")
                if (any(abs(a-b) > .01 for a, b in zip(_vector(actor.get_actor_location()), expected_location(item))) or
                        any(abs(a-b) > 1e-5 for a, b in zip(_vector(actor.get_actor_scale3d()), item["scale"]))):
                    raise ReviewError("actor_transform_mismatch")
            if plan_world(recipe, root) != plan:
                raise ReviewError("world_inputs_changed_during_placement")
            receipt["status"] = "saving_materials"
            for name, material in materials.items():
                if not library.save_loaded_asset(material, only_if_is_dirty=False):
                    raise ReviewError("material_save_failed")
                receipt["saved_materials"].append(destination + "/M_" + name)
            receipt["status"] = "placed_review_required"
            return receipt
        except Exception as error:
            receipt["failed_stage"] = receipt["status"]
            receipt["status"] = "failed"
            receipt["error"] = str(error) if isinstance(error, ReviewError) else type(error).__name__
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
            stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan/place a world in an explicit empty Unreal review map")
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-level")
    args = parser.parse_args(argv)
    receipt = run_world_review(read_json(args.recipe), args.source, args.report,
                               apply=args.apply, target_level=args.target_level)
    print(json.dumps({k: v for k, v in receipt.items() if k != "plan"}, indent=2))
    return 1 if receipt["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
