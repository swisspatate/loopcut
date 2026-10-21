# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage existing assets in an empty review map. No source saves or level saves."""
import argparse
import json
from pathlib import Path

from .scene_recipes import load_plan, ELEMENTS, MECHANISMS
from .game_project import GameProject
from .unreal_director import require, clean_content, review_map, validate_sources
from .unreal_material_variants import _runtime, _outside, _path


def set_materials(component, bindings, sources):
    for binding in bindings:
        slot = binding["slot"]
        require(slot < component.get_num_materials(), "missing_outfit_material_slot")
        component.set_material(slot, sources[binding["material"]])
        require(_path(component.get_material(slot)) == binding["material"], "material_assignment_readback_failed")


def wardrobe_preflight(plan, sources, u):
    spec, outfit = plan["recipe"], plan["operations"][0]
    for path in [spec["body"], outfit["animation"], *[g["mesh"] for g in outfit["garments"]]]:
        require(_path(sources[path].get_editor_property("skeleton")) == spec["skeleton"], "outfit_skeleton_mismatch")
    component = u.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(sources[spec["body"]])
    for part in outfit["accessories"]:
        require(component.does_socket_exist(u.Name(part["socket"])), "accessory_socket_missing")
    for path, bindings in [(spec["body"], outfit["materials"]), *[(g["mesh"], g["materials"]) for g in outfit["garments"]]]:
        component.set_skeletal_mesh_asset(sources[path])
        require(all(b["slot"] < component.get_num_materials() for b in bindings), "missing_outfit_material_slot")


def execute(plan_path, report_path, *, apply=False, unreal_module=None):
    if type(apply) is not bool:
        raise ValueError("apply must be boolean")
    plan = load_plan(plan_path)
    report = _outside(report_path, GameProject(plan["project_root"]))
    receipt = {"schema": "cryptonyan.scene-result/1", "plan_identity": plan["identity"], "status": "planned",
               "owned_actors": [], "removed_actors": [], "level_saved": False, "source_assets_saved": False,
               "engine_validated": False, "visual_quality_validated": False}
    u, editor, spawned = unreal_module, None, []
    with report.open("x", encoding="utf-8") as stream:
        try:
            if not apply:
                return receipt
            if u is None:
                import unreal as u
            _, project = _runtime(u)
            require(project._project_identity() == plan["project_identity"], "wrong_active_project")
            clean_content(u)
            editor = review_map(plan, u)
            sources = validate_sources(plan, u)
            if plan["recipe"]["kind"] == "wardrobe":
                wardrobe_preflight(plan, sources, u)
            else:
                require(hasattr(u, "CryptoNyanAtmosphere") and hasattr(u, "CryptoNyanMechanism"), "compile_CryptoNyanRuntime_first")
                for module in plan["recipe"]["modules"].values():
                    box = sources[module["mesh"]].get_bounding_box()
                    require(all(abs(getattr(box.min, axis)+half*100) <= .1 and abs(getattr(box.max, axis)-half*100) <= .1
                                for axis, half in zip("xyz", module["half_m"])), "module_bounds_or_pivot_differ_from_recipe")
            require(load_plan(plan_path) == plan, "source_changed_during_preflight")
            def spawn(kind, position, label, yaw=0):
                actor = require(editor.spawn_actor_from_class(kind, u.Vector(*[x*100 for x in position]),
                    u.Rotator(pitch=0, yaw=yaw, roll=0)), "scene_spawn_failed")
                spawned.append(actor); receipt["owned_actors"].append(_path(actor))
                actor.set_actor_label("CN_"+label)
                location = actor.get_actor_location()
                require(all(abs(getattr(location, a)-v*100) <= .1 for a, v in zip("xyz", position)), "spawn_position_mismatch")
                return actor
            def mesh_actor(path, label, position, skeletal=False):
                actor = spawn(u.SkeletalMeshActor if skeletal else u.StaticMeshActor, position, label)
                component = actor.get_component_by_class(u.SkeletalMeshComponent if skeletal else u.StaticMeshComponent)
                require(component is not None, "missing_mesh_component")
                if skeletal:
                    component.set_skeletal_mesh_asset(sources[path])
                    require(_path(component.get_skinned_asset()) == path, "skeletal_mesh_readback_failed")
                else:
                    require(component.set_static_mesh(sources[path]), "mesh_assignment_failed")
                    require(_path(component.get_editor_property("static_mesh")) == path, "mesh_readback_failed")
                return actor, component
            receipt["status"] = "placing"
            if plan["recipe"]["kind"] == "wardrobe":
                outfit = plan["operations"][0]
                body, component = mesh_actor(outfit["body"], "Outfit", [0, 0, 0], True)
                component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
                component.set_editor_property("disable_post_process_blueprint", True)
                component.set_editor_property("disable_cloth_simulation", True)
                component.set_simulate_physics(False)
                component.set_editor_property("suppress_notify_event_dispatch", True)
                set_materials(component, outfit["materials"], sources)
                # Serialized single-node animation; local viewport/PIE playback acceptance required.
                component.override_animation_data(sources[outfit["animation"]], True, True, 0.0, 1.0)
                component.set_update_animation_in_editor(True)
                for garment in outfit["garments"]:
                    actor, follower = mesh_actor(garment["mesh"], garment["id"], [0, 0, 0], True)
                    require(actor.attach_to_component(component, u.Name("None"), u.AttachmentRule.SNAP_TO_TARGET,
                        u.AttachmentRule.SNAP_TO_TARGET, u.AttachmentRule.SNAP_TO_TARGET, False), "garment_attachment_failed")
                    follower.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
                    follower.set_editor_property("disable_post_process_blueprint", True)
                    follower.set_editor_property("disable_cloth_simulation", True)
                    follower.set_simulate_physics(False)
                    follower.set_editor_property("suppress_notify_event_dispatch", True)
                    follower.set_leader_pose_component(component, True, False)
                    require(follower.get_editor_property("leader_pose_component") == component, "garment_pose_link_failed")
                    set_materials(follower, garment["materials"], sources)
                for accessory in outfit["accessories"]:
                    actor, part = mesh_actor(accessory["mesh"], accessory["id"], [0, 0, 0])
                    part.set_mobility(u.ComponentMobility.MOVABLE)
                    part.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
                    require(actor.attach_to_component(component, u.Name(accessory["socket"]), u.AttachmentRule.SNAP_TO_TARGET,
                        u.AttachmentRule.SNAP_TO_TARGET, u.AttachmentRule.SNAP_TO_TARGET, False), "accessory_attachment_failed")
                    actor.set_actor_relative_location(u.Vector(*[x*100 for x in accessory["offset_m"]]), False, True)
                    roll, pitch, yaw = accessory["rotation_rpy_deg"]
                    actor.set_actor_relative_rotation(u.Rotator(pitch=pitch, yaw=yaw, roll=roll), False, True)
                    actor.set_actor_relative_scale3d(u.Vector(*accessory["scale"]))
                    require(actor.get_attach_parent_actor() == body, "accessory_parent_readback_failed")
                receipt["outfit"] = plan["recipe"]["outfit"]
                receipt["animation"] = outfit["animation"]
            else:
                for op in plan["operations"]:
                    if op["kind"] == "mesh":
                        actor, component = mesh_actor(op["mesh"], op["id"], op["position_m"])
                        actor.set_actor_rotation(u.Rotator(pitch=0, yaw=op["yaw_deg"], roll=0), True)
                        actor.set_actor_scale3d(u.Vector(*op["scale"]))
                        actual_scale, actual_rotation = actor.get_actor_scale3d(), actor.get_actor_rotation()
                        require(all(abs(getattr(actual_scale, a)-v) <= 1e-5 for a, v in zip("xyz", op["scale"])), "scale_readback_failed")
                        require(abs((actual_rotation.yaw-op["yaw_deg"]+180)%360-180) < .01, "rotation_readback_failed")
                        if op["material"]:
                            set_materials(component, [{"slot": i, "material": op["material"]} for i in range(component.get_num_materials())], sources)
                    elif op["kind"] == "platform":
                        require(hasattr(u, "CryptoNyanPlatform"), "compile_CryptoNyanRuntime_first")
                        actor = spawn(u.CryptoNyanPlatform, op["position_m"], op["id"])
                        require(actor.configure_platform(sources[op["mesh"]], sources.get(op["material"]),
                            u.Vector(*[x*100 for x in op["position_m"]]), True, op["amplitude_m"]*100,
                            op["period_s"], op["phase_s"]), "platform_configuration_failed")
                    else:
                        actor = spawn(u.CryptoNyanMechanism, op["position_m"], op["id"])
                        event = op["mechanism"]
                        require(actor.configure_mechanism(MECHANISMS.index(event["kind"]), ELEMENTS.index(event["element"]),
                            event["strength"], u.Vector(*[x*100 for x in event["half_m"]])), "mechanism_configuration_failed")
                theme = plan["recipe"]["themes"][plan["recipe"]["theme"]]
                atmosphere = spawn(u.CryptoNyanAtmosphere, [0, 0, 0], "Atmosphere")
                weather = getattr(u.CryptoNyanWeather, theme["weather"].upper())
                atmosphere.configure_atmosphere(theme["sun_lux"], theme["fog_density"], weather)
                for i, light in enumerate(theme["lights"]):
                    actor = spawn(u.PointLight, light["position_m"], f"Light_{i}")
                    component = actor.get_component_by_class(u.PointLightComponent)
                    component.set_intensity(light["intensity"])
                    component.set_light_color(u.LinearColor(*light["color"], 1), False)
                    component.set_attenuation_radius(light["radius_m"]*100)
                if theme["sound"]:
                    actor = spawn(u.AmbientSound, [0, 0, 0], "AmbientSound")
                    actor.get_component_by_class(u.AudioComponent).set_sound(sources[theme["sound"]])
                if theme["niagara"]:
                    actor = spawn(u.NiagaraActor, [0, 0, 0], "AmbientEffect")
                    actor.get_component_by_class(u.NiagaraComponent).set_asset(sources[theme["niagara"]])
            require(load_plan(plan_path) == plan, "source_changed_during_placement")
            clean_content(u)
            receipt["status"] = "placed_review_required"
            return receipt
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            for actor in reversed(spawned):
                try:
                    path = _path(actor)
                    if editor.destroy_actor(actor):
                        receipt["removed_actors"].append(path)
                except Exception:
                    pass
            receipt["remaining_actors"] = [p for p in receipt["owned_actors"] if p not in receipt["removed_actors"]]
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False)+"\n")


def main(argv=None):
    p = argparse.ArgumentParser(description="Stage rich levels and outfits in an empty Unreal review map")
    p.add_argument("plan", type=Path); p.add_argument("--report", type=Path, required=True); p.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    result = execute(args.plan, args.report, apply=args.apply)
    print(json.dumps(result)); return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
