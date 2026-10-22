# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply planned assignments, then independently reopen and inspect the saved copy."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.rig_repair import expected_snapshot, load_plan, weights_match
from cryptonyan_asset_studio.rig_worker import sample
from cryptonyan_asset_studio.storage import digest, write_json


def protected_state(spec):
    """Hash selected base geometry, UVs, shape keys and rig rest/basis transforms."""
    import bpy
    result, budget = hashlib.sha256(), 0
    def add(value):
        nonlocal budget
        budget += 1
        if budget > 2000000:
            raise WorkerFailure(code="complexity_budget")
        result.update(json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n")
    def matrix(value):
        return [list(row) for row in value]
    rig = bpy.data.objects[spec["armature"]]
    add([rig.name, matrix(rig.matrix_basis), rig.data.pose_position])
    for bone in rig.data.bones:
        add([bone.name, matrix(bone.matrix_local), matrix(rig.pose.bones[bone.name].matrix_basis)])
    for mesh_name in spec["meshes"]:
        obj = bpy.data.objects[mesh_name]
        mesh = obj.data
        if len(mesh.loops) > 500000 or len(mesh.polygons) > 100000 or len(mesh.uv_layers) > 8:
            raise WorkerFailure(code="complexity_budget")
        add([obj.name, mesh.name, matrix(obj.matrix_basis), obj.parent.name if obj.parent else None])
        add([[g.name, g.lock_weight] for g in obj.vertex_groups])
        for vertex in mesh.vertices:
            add(list(vertex.co))
        for edge in mesh.edges:
            add(list(edge.vertices))
        for face in mesh.polygons:
            add([list(face.vertices), face.material_index, face.use_smooth])
        for uv in mesh.uv_layers:
            add(uv.name)
            for item in uv.data:
                add(list(item.uv))
        if mesh.shape_keys:
            if len(mesh.shape_keys.key_blocks) > 64:
                raise WorkerFailure(code="complexity_budget")
            for key in mesh.shape_keys.key_blocks:
                add([key.name, key.value, key.relative_key.name, key.vertex_group])
                for point in key.data:
                    add(list(point.co))
    return result.hexdigest()


def main():
    import bpy
    request_path = Path(sys.argv[sys.argv.index("--")+1])
    try:
        request = read_json(request_path)
        output, stage = Path(request["output"]), request["stage"]
        if stage not in ("apply", "verify"):
            raise WorkerFailure(code="rig_repair_guard")
        plan = load_plan(output / "plan.json")
        if digest(output / "source.blend") != plan["source_sha256"]:
            raise WorkerFailure(code="rig_repair_guard")
        input_path = output / ("source.blend" if stage == "apply" else "candidate.blend")
        bpy.ops.wm.open_mainfile(filepath=str(input_path), load_ui=False, use_scripts=False)
        # Saving elsewhere must not silently break relative external resources.
        if bpy.data.libraries or bpy.utils.blend_paths(absolute=True, packed=False, local=False):
            raise WorkerFailure(code="rig_repair_guard")
        spec = plan["settings"]
        for mesh_name in spec["meshes"]:
            obj = bpy.data.objects.get(mesh_name)
            if obj is None or obj.type != "MESH" or obj.data.users != 1 or obj.mode != "OBJECT" or obj.override_library or obj.data.override_library:
                raise WorkerFailure(code="rig_repair_guard")
        rig = bpy.data.objects.get(spec["armature"])
        if rig is None or rig.override_library or rig.data.override_library:
            raise WorkerFailure(code="rig_repair_guard")
        snapshot = read_json(Path(plan["bundle"]) / "weights.json")
        actual, protected = sample(spec), protected_state(spec)
        expected = expected_snapshot(snapshot, plan)
        if stage == "verify":
            if protected != read_json(output / "protected.json")["sha256"] or not weights_match(actual, expected):
                raise WorkerFailure(code="rig_repair_verify")
            write_json(output / "verified-weights.json", actual)
            return
        if not weights_match(actual, snapshot):
            raise WorkerFailure(code="rig_repair_guard")
        deform = {b["name"] for b in actual["bones"] if b["deform"]}
        for op in plan["operations"]:
            obj = bpy.data.objects[op["mesh"]]
            for entry in op["before"]:
                group = obj.vertex_groups[entry["group"]]
                if group.name in deform:
                    if group.lock_weight:
                        raise WorkerFailure(code="rig_repair_guard")
                    group.remove([op["vertex"]])
            for entry in op["after"]:
                group = obj.vertex_groups[entry["group"]]
                if group.name in deform:
                    group.add([op["vertex"]], entry["weight"], "REPLACE")
        if protected_state(spec) != protected or not weights_match(sample(spec), expected):
            raise WorkerFailure(code="rig_repair_verify")
        write_json(output / "protected.json", {"sha256": protected})
        candidate = output / "candidate.blend"
        if candidate.exists():
            raise WorkerFailure(code="rig_repair_guard")
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False,
                                   copy=True, relative_remap=False, compress=True)
    except Exception as error:
        write_json(request_path.parent / "worker_error.json", {"code": error.code if isinstance(error, WorkerFailure) else "invalid_asset"})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
