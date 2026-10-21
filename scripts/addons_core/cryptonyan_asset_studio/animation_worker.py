# SPDX-License-Identifier: GPL-3.0-or-later
"""Private headless sampler for Animation Doctor. Never saves the opened blend."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.animation_doctor import name, number, parse_capture, read_json
from cryptonyan_asset_studio.storage import write_json
from cryptonyan_asset_studio.executors import WorkerFailure


def sample(spec):
    import bpy
    from mathutils import Matrix
    from loopcut.scene_context import _fcurves

    spec = parse_capture(spec)
    # A relocated snapshot cannot resolve linked rigs, external caches or custom scripts reliably.
    if bpy.data.libraries or len(bpy.data.objects) > 10000:
        raise WorkerFailure(code="animation_dependencies")
    rig = bpy.data.objects.get(spec["armature"])
    action = bpy.data.actions.get(spec["action"])
    if (rig is None or rig.type != "ARMATURE" or rig.name not in bpy.context.view_layer.objects
            or rig.hide_viewport or rig.data.pose_position != "POSE" or len(rig.pose.bones) > 512):
        raise WorkerFailure(code="animation_mapping")
    if action is None or spec["start_frame"] < action.frame_range[0] or spec["end_frame"] > action.frame_range[1]:
        raise WorkerFailure(code="animation_action")
    selected = [spec["settings"]["root"], *spec["settings"]["bones"]]
    if any(b not in rig.pose.bones for b in selected):
        raise WorkerFailure(code="animation_mapping")
    # Bake physics/cache-driven motion before sampling. Ordinary rig constraints/IK are evaluated.
    scene = bpy.context.scene
    if scene.rigidbody_world or any(o.modifiers and any(m.type in {"CLOTH", "FLUID", "SOFT_BODY", "MESH_CACHE", "MESH_SEQUENCE_CACHE"}
                                                      for m in o.modifiers) for o in scene.objects):
        raise WorkerFailure(code="animation_dependencies")
    rig.animation_data_create()
    rig.animation_data.use_nla = False
    rig.animation_data.action_blend_type = "REPLACE"
    rig.animation_data.action_influence = 1
    rig.animation_data.action = action
    slots = [s for s in getattr(action, "slots", ()) if s.target_id_type == "OBJECT"]
    if slots:
        chosen = [s for s in slots if s.identifier == spec["action_slot"]] if "action_slot" in spec else slots
        if len(chosen) != 1:
            raise WorkerFailure(code="animation_action")
        rig.animation_data.action_slot = chosen[0]
    elif "action_slot" in spec:
        raise WorkerFailure(code="animation_action")
    if not any(f.data_path.startswith('pose.bones[') for f in _fcurves(rig)):
        raise WorkerFailure(code="animation_action")
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    fps = number(scene.render.fps / scene.render.fps_base, 1, 240)
    scale = number(scene.unit_settings.scale_length, 1e-6, 1000)
    start, end, step = spec["start_frame"], spec["end_frame"], spec["step_frames"]
    if (end-start)/fps > 600:
        raise ValueError("Clip duration budget exceeded")
    frames = range(start, end+1, step)
    samples = []
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        evaluated = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        poses = {}
        for bone in selected:
            matrix = evaluated.matrix_world @ evaluated.pose.bones[bone].matrix
            # Reflections/singular transforms make quaternion decomposition ambiguous.
            if matrix.to_3x3().determinant() <= 1e-12:
                raise ValueError("Singular or reflected transform")
            poses[bone] = {"position": [v*scale for v in matrix.translation],
                           "rotation": list(matrix.to_quaternion().normalized())}
        samples.append({"time_s": (frame-start)/fps, "poses": poses})
    return {"schema": "cryptonyan.animation-trace/1", "clip": name(action.name), "samples": samples,
            "provenance": {"blender": bpy.app.version_string},
            "rig": {"armature": rig.name, "bone_count": len(rig.pose.bones), "fps": fps,
                    "unit_scale_m": scale, "nla_enabled": False,
                    "selected_bones": [{"name": b, "parent": rig.data.bones[b].parent.name if rig.data.bones[b].parent else None,
                                        "deform": rig.data.bones[b].use_deform,
                                        "constraints": [c.type for c in rig.pose.bones[b].constraints]}
                                       for b in selected]}}


def main():
    import bpy
    request = Path(sys.argv[sys.argv.index("--")+1]).resolve()
    spec = parse_capture(read_json(request))
    bpy.ops.wm.open_mainfile(filepath=str(request.parent / "source.blend"), load_ui=False, use_scripts=False)
    write_json(request.parent / "trace.json", sample(spec))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        request = Path(sys.argv[sys.argv.index("--")+1]).resolve()
        write_json(request.parent / "worker_error.json", {"code": error.code if isinstance(error, WorkerFailure) else "invalid_asset"})
        raise SystemExit(1)
