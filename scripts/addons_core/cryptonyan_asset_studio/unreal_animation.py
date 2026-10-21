# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a saved AnimSequence in its skeleton's component frame; never save assets.

AnimPoseSpaces.WORLD means component space, not a character's gameplay trajectory.
This adapter deliberately cannot certify foot contacts or cooked/Blueprint playback.
"""
import argparse
import json
from pathlib import Path

from .animation_doctor import audit_trace, exact, name, norm, number, parse_settings, read_json
from .storage import write_json
from .unreal_material_variants import _bounded, _file_state, _kind, _object_path, _outside, _path, _runtime


def specification(value):
    exact(value, ("animation", "sample_count", "settings"))
    path = _object_path(value["animation"])
    if path.split(".")[1] != path.split(".")[0].rsplit("/", 1)[1]:
        raise ValueError("Require the package's primary animation object")
    count = value["sample_count"]
    if type(count) is not int or not 2 <= count <= 2001:
        raise ValueError("Use 2 to 2001 samples including both clip endpoints")
    settings = parse_settings(value["settings"])
    if settings["contact_space"] != "unknown":
        raise ValueError("An AnimSequence has no actor world trajectory; require contact_space unknown")
    return {"animation": path, "sample_count": count, "settings": settings}


def normalized_pose(transform):
    """Reflect UE Y, convert cm to m, reorder XYZW to WXYZ in a rigid frame."""
    scale = [number(getattr(transform.scale3d, a), -1e6, 1e6) for a in "xyz"]
    if any(abs(v-1) > 1e-4 for v in scale):
        raise ValueError("Scaled bone poses require a deformation-aware sampler")
    p = [number(getattr(transform.translation, a), -1e8, 1e8)/100 for a in "xyz"]
    q = [number(getattr(transform.rotation, a), -1, 1) for a in "wxyz"]
    length = norm(q)
    if abs(length-1) > 1e-3:
        raise ValueError("Unreal returned a non-unit quaternion")
    return {"position": [p[0], -p[1], p[2]],
            "rotation": [q[0]/length, -q[1]/length, q[2]/length, -q[3]/length]}


def capture(spec, output, *, unreal_module=None):
    """Run on the editor thread, with a single owner; write only a new external folder."""
    spec = specification(spec)
    u = unreal_module
    if u is None:
        import unreal as u
    version, project = _runtime(u)
    output = _outside(output, project).resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "cryptonyan.unreal-animation-capture/1", "status": "sampling",
               "assets_saved": False, "gameplay_evaluated": False, "engine_validated": False}
    try:
        def source_state():
            # RAW evaluation still reads the skeleton; reject unsaved content globally.
            if _bounded(u.EditorLoadingAndSavingUtils.get_dirty_content_packages(), 10000, "dirty_package_budget"):
                raise ValueError("Save or discard content edits before sampling")
            seq = u.load_asset(spec["animation"])
            if _kind(seq) != "AnimSequence" or _path(seq) != spec["animation"]:
                raise ValueError("Require an existing AnimSequence without redirectors")
            if seq.get_editor_property("additive_anim_type") != u.AdditiveAnimationType.AAT_NONE or seq.get_editor_property("parent_asset") is not None:
                raise ValueError("Additive and inherited animations require a separate sampler")
            skeleton = seq.get_editor_property("skeleton")
            if _kind(skeleton) != "Skeleton":
                raise ValueError("Missing animation skeleton")
            skeleton_path = _object_path(_path(skeleton))
            project._inspection_files, project._inspection_bytes = {}, 0
            state = {"project_identity": project._project_identity(), "animation": spec["animation"],
                     "files": _file_state(project, spec["animation"]), "skeleton": skeleton_path,
                     "skeleton_files": _file_state(project, skeleton_path),
                     "duration_s": number(seq.get_editor_property("sequence_length"), 1e-4, 600),
                     "rate_scale": number(seq.get_editor_property("rate_scale"), -1000, 1000)}
            return seq, state

        seq, before = source_state()
        if before["duration_s"] / (spec["sample_count"]-1) < 1e-6:
            raise ValueError("Sample intervals must be at least one microsecond")
        options = u.AnimPoseEvaluationOptions(evaluation_type=u.AnimDataEvalType.RAW,
            should_retarget=False, extract_root_motion=False, incorporate_root_motion_into_pose=True,
            retrieve_additive_as_full_pose=False, evaluate_curves=False)
        api = u.AnimPoseExtensions
        bones = [spec["settings"]["root"], *spec["settings"]["bones"]]
        samples, initial_names = [], None
        for index in range(spec["sample_count"]):
            t = before["duration_s"] * index / (spec["sample_count"]-1)
            pose = api.get_anim_pose_at_time(seq, t, options)
            if not api.is_valid(pose):
                raise ValueError("Unreal returned an invalid animation pose")
            names = [name(str(b)) for b in _bounded(api.get_bone_names(pose), 512, "bone_budget")]
            if len(names) != len(set(names)) or not set(bones) <= set(names):
                raise ValueError("Mapped bones missing from the evaluated pose")
            if initial_names is not None and initial_names != names:
                raise ValueError("Pose bone mapping changed during capture")
            initial_names = names
            samples.append({"time_s": t, "poses": {bone: normalized_pose(
                api.get_bone_pose(pose, bone, u.AnimPoseSpaces.WORLD)) for bone in bones}})
        if source_state()[1] != before:
            raise ValueError("Animation, skeleton or project changed during capture")
        trace = {"schema": "cryptonyan.animation-trace/1", "space": "component", "clip": spec["animation"].rsplit(".", 1)[1],
                 "samples": samples, "rig": {"bone_count": len(initial_names), "skeleton": before["skeleton"]},
                 "provenance": {"sampler": "unreal_anim_pose_raw", "engine": version, "source": before,
                    "capture": spec, "frame": "skeleton_component_reflect_Y_metres_WXYZ",
                    "root_motion_incorporated": True, "retargeted": False, "rate_scale_applied": False,
                    "actor_trajectory_included": False, "blueprint_evaluated": False}}
        report = audit_trace(trace, spec["settings"])
        write_json(output / "trace.json", trace)
        write_json(output / "audit.json", report)
        write_json(output / "events.json", {**report["effect_candidates"], "audit_identity": report["identity"], "clip": trace["clip"]})
        receipt.update(status="captured_review_required", audit_identity=report["identity"])
        return report
    except Exception as error:
        receipt.update(status="failed", error=type(error).__name__)
        raise
    finally:
        write_json(output / "capture.json", receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sample an existing saved AnimSequence inside Unreal 5.8 Python")
    parser.add_argument("specification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = capture(read_json(args.specification), args.output)
    print(json.dumps({"status": report["status"], "findings": len(report["findings"])}))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
