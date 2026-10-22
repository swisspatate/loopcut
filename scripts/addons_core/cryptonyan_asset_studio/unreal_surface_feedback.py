# SPDX-License-Identifier: GPL-3.0-or-later
"""Editor-only candidate profile/animation creation, reused by unreal_director."""
import math

from .surface_feedback import SETTINGS, PAIRS, TRACK
from .unreal_director import require, owned, _path


def preflight(plan, sources, u):
    from .unreal_director import effects_preflight, TRACK as FX_TRACK
    spec = plan["recipe"]
    count = effects_preflight(plan, sources, u, track=TRACK)
    require(FX_TRACK.casefold() not in {str(t).casefold() for t in
            u.AnimationLibrary.get_animation_notify_track_names(sources[spec["animation"]])}, "source_already_has_directed_effects")
    component = u.SkeletalMeshComponent(); component.set_skeletal_mesh_asset(sources[spec["preview_mesh"]])
    require(all(component.does_socket_exist(u.Name(f)) for f in spec["foot_sockets"]), "missing_mapped_feedback_socket")
    for cue in spec["cues"]:
        for path in cue["sounds"]:
            wave = sources[path]; duration = wave.get_editor_property("duration")
            require(wave.get_editor_property("looping") is False and wave.get_editor_property("num_channels") == 1 and
                    isinstance(duration, (int,float)) and not isinstance(duration,bool) and math.isfinite(duration) and
                    .001 <= duration <= spec["settings"]["hard_stop_seconds"]*cue["pitch"][0],
                    "feedback_requires_short_mono_nonlooping_SoundWave")
    return count


def property_checked(obj, field, value, *, paths=False, numeric=False):
    obj.set_editor_property(field, value); actual = obj.get_editor_property(field)
    if paths: equal = _path(actual) == _path(value)
    elif numeric: equal = abs(actual-value) <= 1e-5
    else: equal = actual == value
    require(equal, "feedback_property_readback_failed")


def create(plan, sources, u, receipt, original_count):
    spec = plan["recipe"]; tools = u.AssetToolsHelpers.get_asset_tools()
    factory = u.DataAssetFactory()
    factory.set_editor_property("data_asset_class", u.CryptoNyanSurfaceFeedbackProfile)
    profile = owned(tools.create_asset("DA_SurfaceFeedback", spec["destination"], u.CryptoNyanSurfaceFeedbackProfile, factory),
                    spec["destination"]+"/DA_SurfaceFeedback.DA_SurfaceFeedback", "CryptoNyanSurfaceFeedbackProfile", receipt)
    property_checked(profile, "target_mesh", sources[spec["preview_mesh"]], paths=True)
    property_checked(profile, "attenuation", sources.get(spec["attenuation"]), paths=True)
    profile.set_editor_property("foot_sockets", [u.Name(f) for f in spec["foot_sockets"]])
    require([str(n) for n in profile.get_editor_property("foot_sockets")] == spec["foot_sockets"], "feedback_foot_mapping_readback_failed")
    for field, value in spec["settings"].items(): property_checked(profile, field, value, numeric=True)
    cues = []
    for item in spec["cues"]:
        cue = u.CryptoNyanSurfaceFeedbackCue()
        property_checked(cue, "kind", getattr(u.CryptoNyanFeedbackKind, item["event"].upper()))
        for field in ("physical_material", "niagara"): property_checked(cue, field, sources.get(item[field]), paths=True)
        cue.set_editor_property("sounds", [sources[p] for p in item["sounds"]])
        require([_path(p) for p in cue.get_editor_property("sounds")] == item["sounds"], "feedback_sound_readback_failed")
        for key in PAIRS:
            for prefix, value in zip(("min_", "max_"), item[key]): property_checked(cue, prefix+key, value, numeric=True)
        property_checked(cue, "reference_speed_cm_s", item["reference_speed_cm_s"], numeric=True)
        cues.append(cue)
    profile.set_editor_property("cues", cues)
    actual = profile.get_editor_property("cues")
    require(len(actual) == len(cues), "feedback_cue_count_readback_failed")
    for expected, recorded in zip(spec["cues"], actual):
        require(recorded.get_editor_property("kind") == getattr(u.CryptoNyanFeedbackKind,expected["event"].upper()), "feedback_cue_readback_failed")
        require(abs(recorded.get_editor_property("reference_speed_cm_s")-expected["reference_speed_cm_s"]) <= 1e-5, "feedback_cue_readback_failed")
        for key in PAIRS:
            for prefix,value in zip(("min_","max_"),expected[key]):
                require(abs(recorded.get_editor_property(prefix+key)-value) <= 1e-5, "feedback_cue_readback_failed")
        for field in ("physical_material", "niagara"):
            require(_path(recorded.get_editor_property(field)) == expected[field], "feedback_cue_readback_failed")
        require([_path(p) for p in recorded.get_editor_property("sounds")] ==
                expected["sounds"], "feedback_cue_readback_failed")
    require(profile.validate_profile(), "runtime_feedback_profile_validation_failed")
    source = sources[spec["animation"]]; lib = u.AnimationLibrary
    animation = owned(tools.duplicate_asset("AN_SurfaceFeedback", spec["destination"], source),
                      spec["destination"]+"/AN_SurfaceFeedback.AN_SurfaceFeedback", "AnimSequence", receipt)
    require(_path(animation.get_editor_property("skeleton")) == _path(source.get_editor_property("skeleton")) and
            abs(lib.get_sequence_length(animation)-spec["duration_s"]) <= .001 and
            len(lib.get_animation_notify_events(animation)) == original_count, "animation_copy_mismatch")
    lib.add_animation_notify_track(animation, u.Name(TRACK))
    for event in spec["events"]:
        notify = require(lib.add_animation_notify_event(animation,u.Name(TRACK),event["time_s"],u.CryptoNyanContactNotify), "feedback_notify_creation_failed")
        property_checked(notify, "foot_socket", u.Name(event["socket"]))
        property_checked(notify, "should_fire_in_editor", False)
    events = lib.get_animation_notify_events_for_track(animation,u.Name(TRACK))
    require(len(events) == len(spec["events"]) and
            all(abs(a-b["time_s"]) <= .001 for a,b in zip(sorted(lib.get_anim_notify_event_trigger_time(e) for e in events), spec["events"])) and
            len(lib.get_animation_notify_events(animation)) == original_count+len(events) and
            len(lib.get_animation_notify_events(source)) == original_count and
            TRACK.casefold() not in {str(t).casefold() for t in lib.get_animation_notify_track_names(source)},
            "feedback_notify_or_source_readback_failed")
    receipt.update(profile=_path(profile), animation=_path(animation), notify_count_added=len(events),
                   original_notifies_retained=original_count, component_installed=False,
                   anim_blueprint_modified=False, audio_playback_validated=False, collision_validated=False)
    return [profile, animation]
