# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a small elemental review scene in an explicitly empty UE 5.8 map."""
import argparse
import json
from pathlib import Path
import re

from .unreal_review import ReviewError, probe


def review(report_path, *, apply=False, target_level=None, unreal_module=None):
    report = Path(report_path)
    if report.is_symlink() or type(apply) is not bool:
        raise ValueError("Invalid review receipt or apply flag")
    receipt = {"schema": "cryptonyan.creative-review/1", "apply": apply, "status": "planned",
               "target_level": target_level, "owned_actors": [], "owned_assets": [], "saved_assets": [],
               "level_saved": False, "engine_validated": False,
               "required_classes": ["CryptoNyanElementSurface", "CryptoNyanAtmosphere", "CryptoNyanPowerComponent", "CryptoNyanPowerMenu"]}
    with report.open("x", encoding="utf-8") as stream:
        try:
            if not apply:
                return receipt
            if not isinstance(target_level, str) or not re.fullmatch(r"/Game/CryptoNyan/ReviewMaps/[A-Za-z0-9_]+", target_level):
                raise ReviewError("require_explicit_empty_review_map")
            if unreal_module is None:
                import unreal as unreal_module
            u = unreal_module
            runtime = probe(u)
            required = (*receipt["required_classes"], "EditorActorSubsystem", "UnrealEditorSubsystem",
                        "MaterialExpressionVectorParameter", "CryptoNyanWeather", "PlayerStart")
            if runtime["missing_apis"] or not runtime["target_version_matches"] or any(not hasattr(u, name) for name in required):
                raise ReviewError("require_UE_5_8_and_compiled_creative_plugin")
            world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
            if world is None or world.get_path_name() != target_level+"."+target_level.rsplit("/",1)[1]:
                raise ReviewError("wrong_current_review_map")
            editor = u.get_editor_subsystem(u.EditorActorSubsystem)
            if any(a.get_class().get_name() != "WorldSettings" for a in editor.get_all_level_actors()):
                raise ReviewError("review_map_not_empty")
            destination = "/Game/CryptoNyan/CreativeReviews/"+target_level.rsplit("/",1)[1]
            receipt["destination"] = destination
            library = u.EditorAssetLibrary
            if library.does_directory_exist(destination) or library.list_assets(destination, recursive=True, include_folder=False):
                raise ReviewError("creative_destination_exists")
            if not library.make_directory(destination):
                raise ReviewError("creative_reservation_failed")
            receipt["status"] = "creating_material"
            material = u.AssetToolsHelpers.get_asset_tools().create_asset("M_Element", destination, u.Material, u.MaterialFactoryNew())
            if material is None:
                raise ReviewError("material_creation_failed")
            receipt["owned_assets"].append(destination+"/M_Element")
            material.set_editor_property("used_with_instanced_static_meshes", True)
            editing = u.MaterialEditingLibrary
            color = editing.create_material_expression(material, u.MaterialExpressionVectorParameter, -300, 0)
            if color is None:
                raise ReviewError("material_expression_failed")
            color.set_editor_property("parameter_name", u.Name("Tint"))
            color.set_editor_property("default_value", u.LinearColor(.2,.6,1,1))
            if not editing.connect_material_property(color, "", u.MaterialProperty.MP_BASE_COLOR):
                raise ReviewError("material_connection_failed")
            if not editing.connect_material_property(color, "", u.MaterialProperty.MP_EMISSIVE_COLOR):
                raise ReviewError("material_connection_failed")
            editing.recompile_material(material)
            receipt["status"] = "placing"
            examples = [("Combustible", {"flammable": True}), ("Bassin", {"liquid": True, "freezable": True}),
                        ("Pilier", {"movable": True}), ("Conducteur", {"conductive": True}),
                        ("Humide", {"initially_wet": True, "freezable": True})]
            for index, (name, properties) in enumerate(examples):
                actor = editor.spawn_actor_from_class(u.CryptoNyanElementSurface, u.Vector(index*250, 500, 50))
                if actor is None:
                    raise ReviewError("actor_spawn_failed")
                receipt["owned_actors"].append(actor.get_path_name())
                actor.set_actor_label("CN_"+name)
                for key, value in properties.items():
                    actor.set_editor_property(key, value)
                actor.get_editor_property("surface").set_material(0, material)
            floor = editor.spawn_actor_from_class(u.CryptoNyanElementSurface, u.Vector(0,0,-50))
            if floor is None:
                raise ReviewError("floor_spawn_failed")
            receipt["owned_actors"].append(floor.get_path_name())
            floor.set_actor_label("CN_ReviewFloor")
            floor.set_actor_scale3d(u.Vector(40,40,1))
            floor.set_editor_property("freezable", False)
            start = editor.spawn_actor_from_class(u.PlayerStart, u.Vector(0,-500,100))
            if start is None:
                raise ReviewError("player_start_failed")
            receipt["owned_actors"].append(start.get_path_name())
            atmosphere = editor.spawn_actor_from_class(u.CryptoNyanAtmosphere, u.Vector(0,0,0))
            if atmosphere is None:
                raise ReviewError("atmosphere_spawn_failed")
            receipt["owned_actors"].append(atmosphere.get_path_name())
            atmosphere.set_editor_property("weather_material", material)
            atmosphere.configure_atmosphere(5000, .01, u.CryptoNyanWeather.SNOW)
            if not library.save_loaded_asset(material, only_if_is_dirty=False):
                raise ReviewError("material_save_failed")
            receipt["saved_assets"].append(destination+"/M_Element")
            receipt["status"] = "placed_review_required"
            return receipt
        except Exception as error:
            receipt["failed_stage"] = receipt["status"]
            receipt["status"] = "failed"
            receipt["error"] = str(error) if isinstance(error, ReviewError) else type(error).__name__
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2)+"\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare an exclusive elemental review scene; never save or switch the level")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--target-level")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = review(args.report, apply=args.apply, target_level=args.target_level)
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
