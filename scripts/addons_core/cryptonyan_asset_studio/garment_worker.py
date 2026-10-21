# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.animation_worker import sample as sample_animation
from cryptonyan_asset_studio.biome_materials import _png
from cryptonyan_asset_studio.garment_fit import specification
from cryptonyan_asset_studio.rig_worker import sample as sample_weights
from cryptonyan_asset_studio.rig_doctor import audit_weights
from cryptonyan_asset_studio.storage import write_json


def triangles(obj, evaluated=False):
    import bpy
    current = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()) if evaluated else obj
    mesh = current.to_mesh() if evaluated else current.data
    try:
        if len(mesh.vertices) > 50000 or len(mesh.polygons) > 100000:
            raise ValueError("Body geometry budget exceeded")
        mesh.calc_loop_triangles()
        points = [current.matrix_world @ v.co for v in mesh.vertices]
        return points, [tuple(t.vertices) for t in mesh.loop_triangles]
    finally:
        if evaluated:
            current.to_mesh_clear()


def barycentric(p, a, b, c):
    x, y, z = b-a, c-a, p-a
    d = x.dot(x)*y.dot(y)-x.dot(y)**2
    if d <= 1e-16:
        raise ValueError("Degenerate body triangle")
    v = (y.dot(y)*z.dot(x)-x.dot(y)*z.dot(y))/d
    w = (x.dot(x)*z.dot(y)-x.dot(y)*z.dot(x))/d
    values = [max(0, 1-v-w), max(0, v), max(0, w)]
    total = sum(values)
    return [v/total for v in values]


def closed_outward(points, faces):
    edges, volume = {}, 0
    for face in faces:
        a, b, c = [points[i] for i in face]
        if (b-a).cross(c-a).length < 1e-10:
            raise ValueError("Degenerate body triangle")
        volume += a.dot(b.cross(c))/6
        for x, y in zip(face, face[1:]+face[:1]):
            key = tuple(sorted((x, y)))
            edges.setdefault(key, []).append((x, y))
    if volume <= 1e-9 or any(len(v) != 2 or v[0] != v[1][::-1] for v in edges.values()):
        raise ValueError("Fitting requires a closed consistently outward body or proxy")


def uv_mask(obj, path, size):
    mesh = obj.data
    if mesh.uv_layers.active is None:
        raise ValueError("Body and garment need explicit UV maps")
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers.active.data
    pixels, budget = bytearray(size*size*3), 0
    for tri in mesh.loop_triangles:
        coords = [uv[i].uv.copy() for i in tri.loops]
        if any(not 0 <= v <= 1 for p in coords for v in p):
            raise ValueError("UV mask export supports one 0-1 tile")
        xs, ys = [p.x*size for p in coords], [(1-p.y)*size for p in coords]
        lowx, highx = max(0, int(min(xs))), min(size-1, int(max(xs)))
        lowy, highy = max(0, int(min(ys))), min(size-1, int(max(ys)))
        budget += (highx-lowx+1)*(highy-lowy+1)
        if budget > 16000000:
            raise ValueError("UV raster budget exceeded; reduce resolution")
        for y in range(lowy, highy+1):
            for x in range(lowx, highx+1):
                cross = [(xs[(i+1)%3]-xs[i])*(y+.5-ys[i])-(ys[(i+1)%3]-ys[i])*(x+.5-xs[i]) for i in range(3)]
                if max(cross) <= 0 or min(cross) >= 0:
                    offset = (y*size+x)*3; pixels[offset:offset+3] = b"\xff\xff\xff"
    path.write_bytes(_png(size, pixels))


def fit(spec, output):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    spec = specification(spec)
    if bpy.data.libraries or bpy.utils.blend_paths(absolute=True, packed=True, local=False):
        raise ValueError("Require a self-contained source")
    capture = spec["capture"]
    body, garment, rig = (bpy.data.objects.get(n) for n in (spec["body"], spec["garment"], capture["armature"]))
    if body is None or garment is None or rig is None or body.type != "MESH" or garment.type != "MESH" or rig.type != "ARMATURE":
        raise ValueError("Explicit body, garment and rig required")
    if garment.parent or garment.constraints or garment.modifiers or garment.data.shape_keys or garment.mode != "OBJECT" or not 1 <= len(garment.data.vertices) <= 10000:
        raise ValueError("Use a static garment without modifiers or shape keys, at most 10000 vertices")
    if len(body.modifiers) != 1 or body.modifiers[0].type != "ARMATURE" or body.modifiers[0].object != rig:
        raise ValueError("Use a body with only the selected Armature modifier")
    if any(o.matrix_world.to_3x3().determinant() <= 1e-12 for o in (body, garment, rig)):
        raise ValueError("Reflected or singular transform")
    settings = {"armature": rig.name, "meshes": [body.name]}
    original_weights = sample_weights(settings)
    scale = bpy.context.scene.unit_settings.scale_length
    if not 1e-6 <= scale <= 1000:
        raise ValueError("Invalid scene units")
    points, faces = triangles(body)
    closed_outward(points, faces)
    bvh = BVHTree.FromPolygons(points, faces, all_triangles=True)
    deform = {b.name for b in rig.data.bones if b.use_deform}
    body_groups = {g.index: g.name for g in body.vertex_groups if g.name in deform}
    if any(g.lock_weight and g.name in deform for g in garment.vertex_groups):
        raise ValueError("Locked garment deform groups")
    if "CN_GarmentCandidate" in bpy.data.objects:
        raise ValueError("Candidate name already exists in source")
    candidate = garment.copy(); candidate.data = garment.data.copy(); candidate.name = "CN_GarmentCandidate"
    bpy.context.scene.collection.objects.link(candidate)
    for bone in sorted(deform):
        if bone not in candidate.vertex_groups:
            candidate.vertex_groups.new(name=bone)
    moved, max_shift = 0, 0
    for vertex in candidate.data.vertices:
        p = candidate.matrix_world @ vertex.co
        near, normal, index, distance = bvh.find_nearest(p)
        if near is None or distance*scale > spec["max_distance_m"]:
            raise ValueError("Garment too far from body; align it before fitting")
        signed = (p-near).dot(normal)*scale
        if signed < spec["clearance_m"]:
            fitted = near+normal*(spec["clearance_m"]/scale)
            shift = (fitted-p).length*scale
            if shift > spec["max_distance_m"]:
                raise ValueError("Fit displacement budget exceeded")
            vertex.co = candidate.matrix_world.inverted() @ fitted
            moved += 1; max_shift = max(max_shift, shift)
        weights = {}
        tri = faces[index]
        for source_index, factor in zip(tri, barycentric(near, *[points[i] for i in tri])):
            for group in body.data.vertices[source_index].groups:
                if group.group in body_groups:
                    bone = body_groups[group.group]
                    weights[bone] = weights.get(bone, 0)+factor*group.weight
        selected = sorted(((b, w) for b, w in weights.items() if w > 1e-8), key=lambda x: (-x[1], x[0]))[:spec["max_influences"]]
        total = sum(w for _, w in selected)
        if total <= 0:
            raise ValueError("Nearest body triangle has no usable deform weights")
        for index in [g.group for g in vertex.groups]:
            if candidate.vertex_groups[index].name in deform:
                candidate.vertex_groups[index].remove([vertex.index])
        for bone, weight in selected:
            candidate.vertex_groups[bone].add([vertex.index], weight/total, "REPLACE")
    modifier = candidate.modifiers.new("CN_TransferredSkin", "ARMATURE"); modifier.object = rig
    modifier.use_bone_envelopes = False
    if sample_weights(settings) != original_weights:
        raise ValueError("Body weights changed unexpectedly")
    uv_mask(body, output / "body-uv-mask.png", spec["uv_size"])
    uv_mask(candidate, output / "garment-uv-mask.png", spec["uv_size"])
    # Reuse explicit action/slot selection and simulation guards, without guessing rig names.
    sample_animation(capture)
    samples = []
    for frame in range(capture["start_frame"], capture["end_frame"]+1, capture["step_frames"]):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        target_points, target_faces = triangles(body, True)
        closed_outward(target_points, target_faces)
        tree = BVHTree.FromPolygons(target_points, target_faces, all_triangles=True)
        garment_points, _ = triangles(candidate, True)
        bad, depth = [], 0
        for index, point in enumerate(garment_points):
            near, normal, _, distance = tree.find_nearest(point)
            signed = (point-near).dot(normal)*scale
            if signed < -.0001:
                bad.append(index); depth = max(depth, -signed)
        samples.append({"frame": frame, "negative_signed_distance_vertices": len(bad), "indices": bad[:100], "max_depth_m": depth})
    audit_spec = {"armature": rig.name, "meshes": [candidate.name], "max_influences": spec["max_influences"]}
    weights = sample_weights(audit_spec)
    report = {"schema": "cryptonyan.garment-fit/1", "candidate_object": candidate.name, "moved_vertices": moved,
              "max_displacement_m": max_shift, "samples": samples, "penetrating_samples": sum(bool(s["negative_signed_distance_vertices"]) for s in samples),
              "weight_audit": audit_weights(weights, audit_spec), "surface_collision_certified": False,
              "visual_quality_validated": False, "blender": bpy.app.version_string}
    garment.hide_render = True; garment.hide_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "candidate.blend"), check_existing=False, copy=True, relative_remap=False)
    bpy.ops.wm.open_mainfile(filepath=str(output / "candidate.blend"), load_ui=False, use_scripts=False)
    if sample_weights(audit_spec) != weights:
        raise ValueError("Saved garment weights differ")
    write_json(output / "garment.json", report)


if __name__ == "__main__":
    import bpy
    request = Path(sys.argv[sys.argv.index("--")+1])
    try:
        bpy.ops.wm.open_mainfile(filepath=str(request.parent / "source.blend"), load_ui=False, use_scripts=False)
        fit(read_json(request), request.parent)
    except Exception:
        write_json(request.parent / "worker_error.json", {"code": "garment_fit_guard"})
        raise SystemExit(1)
