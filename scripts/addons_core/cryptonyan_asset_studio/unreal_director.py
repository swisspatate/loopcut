# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit editor execution of directed review plans; never overwrite or save a level."""
import argparse
import json
from pathlib import Path

from .creative_director import load_plan
from .game_project import GameProject
from .unreal_material_variants import _runtime, _outside, _path, _kind, _object_path, _bounded
from .unreal_review import ReviewError

TRACK = "CN_DirectedEffects"
CHANNELS = tuple(f"{group}.{axis}" for group in ("Location", "Rotation", "Scale") for axis in "XYZ")


def require(value, reason):
    if not value:
        raise ReviewError(reason)
    return value


def owned(obj, expected, kind, receipt):
    # A broken API must never make an original asset appear owned by this operation.
    if obj is not None and _path(obj).startswith(expected.rsplit("/", 1)[0]+"/"):
        receipt["owned_assets"].append(_path(obj))
    require(_path(obj) == expected and _kind(obj) == kind, "candidate_creation_mismatch")
    return obj


def clean_content(u, owned_assets=()):
    permitted = {p.split(".")[0] for p in owned_assets}
    dirty = u.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    require(all(p.get_path_name() in permitted for p in dirty), "save_content_changes_before_director_run")


def validate_sources(plan, u):
    result = {}
    for path, kind in plan["source_classes"].items():
        obj = u.load_asset(path)
        require(_path(obj) == path and _kind(obj) == kind, "missing_source_wrong_class_or_redirector")
        result[path] = obj
    return result


def effects_preflight(plan, sources, u, *, track=TRACK):
    spec = plan["recipe"]
    animation, mesh = sources[spec["animation"]], sources[spec["preview_mesh"]]
    require(_path(animation.get_editor_property("skeleton")) is not None and
            _path(animation.get_editor_property("skeleton")) == _path(mesh.get_editor_property("skeleton")),
            "animation_mesh_skeleton_mismatch")
    lib = u.AnimationLibrary
    require(abs(lib.get_sequence_length(animation)-spec["duration_s"]) <= .001, "animation_duration_mismatch")
    tracks = [str(n) for n in lib.get_animation_notify_track_names(animation)]
    require(track.casefold() not in {n.casefold() for n in tracks}, "source_already_has_directed_effects")
    component = u.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    for event in plan["operations"]:
        require(component.does_socket_exist(u.Name(event["socket"])), "missing_effect_bone_or_socket")
    return len(lib.get_animation_notify_events(animation))


def create_effects(plan, sources, u, receipt, original_count):
    spec, lib = plan["recipe"], u.AnimationLibrary
    path = spec["destination"] + "/AN_Directed.AN_Directed"
    source = sources[spec["animation"]]
    animation = owned(u.AssetToolsHelpers.get_asset_tools().duplicate_asset("AN_Directed", spec["destination"], source),
                      path, "AnimSequence", receipt)
    require(_path(animation.get_editor_property("skeleton")) == _path(source.get_editor_property("skeleton")) and
            abs(lib.get_sequence_length(animation)-spec["duration_s"]) <= .001 and
            len(lib.get_animation_notify_events(animation)) == original_count, "animation_copy_mismatch")
    lib.add_animation_notify_track(animation, u.Name(TRACK))
    for event in plan["operations"]:
        notify = require(lib.add_animation_notify_event(animation, u.Name(TRACK), event["time_s"],
                                                        u.AnimNotify_PlayNiagaraEffect), "notify_creation_failed")
        notify.set_editor_property("template", sources[event["niagara"]])
        notify.set_editor_property("socket_name", u.Name(event["socket"]))
        notify.set_editor_property("attached", event["attached"])
        notify.set_editor_property("location_offset", u.Vector(*event["offset_cm"]))
        notify.set_editor_property("scale", u.Vector(*event["scale"]))
        notify.set_editor_property("absolute_scale", True)
        notify.set_editor_property("should_fire_in_editor", False)
        require(_path(notify.get_editor_property("template")) == event["niagara"] and
                str(notify.get_editor_property("socket_name")) == event["socket"] and
                notify.get_editor_property("attached") == event["attached"], "notify_property_readback_failed")
        for field, expected in (("location_offset", event["offset_cm"]), ("scale", event["scale"])):
            actual = notify.get_editor_property(field)
            require(all(abs(a-b) <= 1e-4 for a, b in zip((actual.x, actual.y, actual.z), expected)),
                    "notify_transform_readback_failed")
    events = lib.get_animation_notify_events_for_track(animation, u.Name(TRACK))
    times = sorted(lib.get_anim_notify_event_trigger_time(e) for e in events)
    require(len(times) == len(plan["operations"]) and
            all(abs(a-b["time_s"]) <= .001 for a, b in zip(times, plan["operations"])), "notify_time_readback_failed")
    require(len(lib.get_animation_notify_events(animation)) == original_count+len(events) and
            len(lib.get_animation_notify_events(source)) == original_count and
            TRACK not in [str(n) for n in lib.get_animation_notify_track_names(source)], "original_notify_count_changed")
    receipt["notify_count_added"] = len(events)
    return animation


def create_cinematic(plan, u, receipt):
    spec = plan["recipe"]
    sequence = owned(u.AssetToolsHelpers.get_asset_tools().create_asset("LS_Directed", spec["destination"],
                       u.LevelSequence, u.LevelSequenceFactoryNew()),
                     spec["destination"]+"/LS_Directed.LS_Directed", "LevelSequence", receipt)
    sequence.set_display_rate(u.FrameRate(numerator=spec["fps"], denominator=1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(plan["operations"][-1]["end"])
    editor = u.get_editor_subsystem(u.LevelSequenceEditorSubsystem)
    cuts = require(sequence.add_track(u.MovieSceneCameraCutTrack), "camera_cut_track_failed")
    for shot in plan["operations"]:
        binding = editor.add_spawnable_from_class(sequence, u.CineCameraActor)
        require(binding is not None and binding.is_valid(), "camera_binding_failed")
        binding.set_display_name("CN_"+shot["id"])
        transform = require(binding.add_track(u.MovieScene3DTransformTrack), "camera_transform_track_failed")
        section = require(transform.add_section(), "camera_transform_section_failed")
        section.set_range(shot["start"], shot["end"])
        all_channels = section.get_all_channels()
        channels = {str(c.get_editor_property("channel_name")): c for c in all_channels}
        require(len(channels) == len(all_channels) and set(CHANNELS) <= channels.keys(), "unsupported_transform_channels")
        for key in shot["keys"]:
            values = [*key["position_cm"], *key["rotation_rpy_deg"], 1, 1, 1]
            for field, value in zip(CHANNELS, values):
                created = channels[field].add_key(u.FrameNumber(key["frame"]), value,
                    time_unit=u.MovieSceneTimeUnit.DISPLAY_RATE, interpolation=u.MovieSceneKeyInterpolation.LINEAR)
                require(created is not None and abs(created.get_value()-value) <= 1e-4, "camera_key_readback_failed")
                keyed_time = created.get_time(time_unit=u.MovieSceneTimeUnit.DISPLAY_RATE)
                # Uncommon display rates may not divide Sequencer's tick resolution exactly.
                require(abs(keyed_time.frame_number.value + keyed_time.sub_frame-key["frame"]) <= .01,
                        "camera_key_time_readback_failed")
        cut = require(cuts.add_section(), "camera_cut_section_failed")
        cut.set_range(shot["start"], shot["end"])
        cut.set_camera_binding_id(u.MovieSceneSequenceExtensions.get_binding_id(sequence, binding))
        require(cut.get_camera_binding_id() == u.MovieSceneSequenceExtensions.get_binding_id(sequence, binding),
                "camera_cut_binding_readback_failed")
    receipt["camera_count"] = len(plan["operations"])
    receipt["lens_policy"] = "CineCameraActor_defaults_review_locally"
    return sequence


def review_map(plan, u):
    target = plan["recipe"]["target_level"]
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(_path(world) == _object_path(target), "wrong_current_review_map")
    editor = u.get_editor_subsystem(u.EditorActorSubsystem)
    require(all(_kind(a) == "WorldSettings" for a in editor.get_all_level_actors()), "review_map_not_empty")
    return editor


def place_architecture(plan, sources, u, receipt, spawned):
    editor = review_map(plan, u)
    for item in plan["operations"]:
        actor = require(editor.spawn_actor_from_class(u.StaticMeshActor, u.Vector(*item["position_cm"]),
                        u.Rotator(pitch=0, yaw=item["yaw_deg"], roll=0)), "module_spawn_failed")
        spawned.append(actor)
        receipt["owned_actors"].append(_path(actor))
        actor.set_actor_label("CN_"+item["id"])
        component = actor.get_component_by_class(u.StaticMeshComponent)
        require(component is not None and component.set_static_mesh(sources[item["mesh"]]), "module_mesh_assignment_failed")
        actor.set_actor_scale3d(u.Vector(*item["scale"]))
        actual = actor.get_actor_location()
        require(all(abs(a-b) <= .01 for a, b in zip((actual.x, actual.y, actual.z), item["position_cm"])),
                "module_position_readback_failed")
        require(_path(component.get_editor_property("static_mesh")) == item["mesh"], "module_mesh_readback_failed")
        scale = actor.get_actor_scale3d()
        require(all(abs(a-b) <= 1e-4 for a, b in zip((scale.x, scale.y, scale.z), item["scale"])),
                "module_scale_readback_failed")
        actual_yaw = actor.get_actor_rotation().yaw
        require(abs((actual_yaw-item["yaw_deg"]+180) % 360-180) <= .01, "module_rotation_readback_failed")
    receipt["collision_navigation_validated"] = False


def execute(plan_path, report_path, *, apply=False, unreal_module=None):
    if type(apply) is not bool:
        raise ValueError("apply must be boolean")
    plan = load_plan(plan_path)
    project = GameProject(plan["project_root"])
    report = _outside(report_path, project)
    receipt = {"schema": "cryptonyan.director-result/1", "identity": plan["identity"],
               "kind": plan["recipe"]["kind"], "status": "planned", "owned_assets": [], "saved_assets": [],
               "owned_actors": [], "removed_actors": [], "level_saved": False, "engine_validated": False,
               "visual_quality_validated": False}
    spawned, u = [], unreal_module
    with report.open("x", encoding="utf-8") as stream:
        try:
            if not apply:
                return receipt
            receipt["status"] = "preflight"
            if u is None:
                import unreal as u
            version, active_project = _runtime(u)
            require(active_project._project_identity() == plan["project_identity"], "wrong_active_project")
            receipt["engine_version"] = version
            kind = receipt["kind"]
            required = {"effects": ("AnimationLibrary", "AnimNotify_PlayNiagaraEffect", "SkeletalMeshComponent"),
                        "cinematic": ("LevelSequence", "LevelSequenceFactoryNew", "LevelSequenceEditorSubsystem",
                                      "CineCameraActor", "MovieSceneCameraCutTrack", "MovieScene3DTransformTrack",
                                      "MovieSceneTimeUnit", "MovieSceneSequenceExtensions"),
                        "architecture": ("StaticMeshActor", "StaticMeshComponent", "EditorActorSubsystem", "UnrealEditorSubsystem"),
                        "surface_feedback": ("AnimationLibrary", "SkeletalMeshComponent", "DataAssetFactory",
                                             "CryptoNyanSurfaceFeedbackProfile", "CryptoNyanSurfaceFeedbackCue",
                                             "CryptoNyanFeedbackKind", "CryptoNyanContactNotify")}[kind]
            require(all(getattr(u, key, None) is not None for key in required), "missing_director_editor_APIs")
            clean_content(u)
            sources = validate_sources(plan, u)
            original_count = effects_preflight(plan, sources, u) if kind == "effects" else None
            if kind == "surface_feedback":
                from .unreal_surface_feedback import preflight
                original_count = preflight(plan, sources, u)
            if kind == "architecture":
                review_map(plan, u)
            require(load_plan(plan_path) == plan, "plan_changed_during_preflight")
            lib, target = u.EditorAssetLibrary, plan["recipe"]["destination"]
            require(not lib.does_directory_exist(target) and not lib.list_assets(target, recursive=True, include_folder=False),
                    "director_destination_exists")
            require(lib.make_directory(target), "director_reservation_failed")
            receipt["destination"] = target
            receipt["status"] = "creating"
            obj = None; objects = []
            if kind == "effects":
                obj = create_effects(plan, sources, u, receipt, original_count)
            elif kind == "cinematic":
                obj = create_cinematic(plan, u, receipt)
            elif kind == "surface_feedback":
                from .unreal_surface_feedback import create
                objects = create(plan, sources, u, receipt, original_count)
            else:
                place_architecture(plan, sources, u, receipt, spawned)
            expected = set(receipt["owned_assets"])
            actual = {_object_path(p) for p in _bounded(lib.list_assets(target, recursive=True, include_folder=False), 4,
                                                       "unexpected_director_assets")}
            require(expected == actual, "unexpected_director_assets")
            require(load_plan(plan_path) == plan, "source_changed_before_save")
            clean_content(u, receipt["owned_assets"])
            if obj is not None: objects.append(obj)
            for obj in objects:
                require(load_plan(plan_path) == plan, "source_changed_before_save")
                clean_content(u, receipt["owned_assets"])
                receipt["status"] = "saving"
                require(lib.save_loaded_asset(obj, only_if_is_dirty=False), "director_save_failed")
                receipt["saved_assets"].append(_path(obj))
            require(load_plan(plan_path) == plan, "source_changed_after_save")
            clean_content(u, receipt["owned_assets"])
            receipt["status"] = "placed_review_required" if kind == "architecture" else "created_review_required"
            return receipt
        except Exception as error:
            receipt["failed_stage"], receipt["status"] = receipt["status"], "failed"
            receipt["error"] = str(error) if isinstance(error, ReviewError) else type(error).__name__
            # Roll back only this call's new architecture actors; never touch existing actors/assets.
            if spawned:
                editor = u.get_editor_subsystem(u.EditorActorSubsystem)
                for actor in reversed(spawned):
                    try:
                        actor_path = _path(actor)
                        if editor.destroy_actor(actor):
                            receipt["removed_actors"].append(actor_path)
                    except Exception:
                        pass
            receipt["remaining_actors"] = [p for p in receipt["owned_actors"] if p not in receipt["removed_actors"]]
            return receipt
        finally:
            stream.write(json.dumps(receipt, indent=2, allow_nan=False)+"\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Execute a directed review plan in Unreal 5.8; defaults to dry run")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = execute(args.plan, args.report, apply=args.apply)
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
