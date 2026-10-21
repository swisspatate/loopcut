# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated base-weight capture. Never evaluate, normalize, rename or save the rig."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.rig_doctor import MAX_ASSIGNMENTS, MAX_VERTICES, specification
from cryptonyan_asset_studio.storage import write_json


def sample(spec):
    import bpy
    spec = specification(spec)
    if bpy.data.libraries or len(bpy.data.objects) > 10000:
        raise WorkerFailure(code="rig_mapping")
    armature = bpy.data.objects.get(spec["armature"])
    if armature is None or armature.type != "ARMATURE" or not 1 <= len(armature.data.bones) <= 512:
        raise WorkerFailure(code="rig_mapping")
    bones = [{"name": b.name, "parent": b.parent.name if b.parent else None, "deform": b.use_deform}
             for b in armature.data.bones]
    meshes, total, assignments = [], 0, 0
    for mesh_name in spec["meshes"]:
        obj = bpy.data.objects.get(mesh_name)
        if obj is None or obj.type != "MESH":
            raise WorkerFailure(code="rig_mapping")
        modifiers = [m for m in obj.modifiers if m.type == "ARMATURE"]
        if len(modifiers) != 1:
            raise WorkerFailure(code="rig_binding")
        modifier = modifiers[0]
        if (modifier.object != armature or not modifier.show_viewport or not modifier.show_render
                or not modifier.use_vertex_groups or modifier.use_bone_envelopes or modifier.use_multi_modifier
                or modifier.vertex_group):
            raise WorkerFailure(code="rig_binding")
        total += len(obj.data.vertices)
        if not obj.data.vertices or total > MAX_VERTICES or len(obj.vertex_groups) > 1024:
            raise WorkerFailure(code="complexity_budget")
        weights = []
        for vertex in obj.data.vertices:
            assignments += len(vertex.groups)
            if assignments > MAX_ASSIGNMENTS:
                raise WorkerFailure(code="complexity_budget")
            weights.append([{"group": g.group, "weight": g.weight} for g in vertex.groups])
        meshes.append({"name": obj.name, "groups": [g.name for g in obj.vertex_groups], "weights": weights,
                       "capture": {"armature_modifier": modifier.name,
                           "preserve_volume": modifier.use_deform_preserve_volume,
                           "other_modifiers": [m.type for m in obj.modifiers if m != modifier],
                           "shape_keys_present": obj.data.shape_keys is not None}})
    return {"schema": "cryptonyan.rig-weights/1", "armature": armature.name, "bones": bones, "meshes": meshes,
            "provenance": {"sampler": "blender_base_vertex_groups", "blender": bpy.app.version_string}}


def main():
    import bpy
    request = Path(sys.argv[sys.argv.index("--")+1])
    output = request.parent
    try:
        bpy.ops.wm.open_mainfile(filepath=str(output / "source.blend"), load_ui=False, use_scripts=False)
        write_json(output / "weights.json", sample(read_json(request)))
    except Exception as error:
        write_json(output / "worker_error.json", {"code": error.code if isinstance(error, WorkerFailure) else "invalid_asset"})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
