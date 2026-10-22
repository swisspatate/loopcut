# SPDX-License-Identifier: GPL-3.0-or-later
"""Private Blender worker. Reuses rig/animation capture and garment geometry helpers."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.animation_doctor import audit_trace, read_json
from cryptonyan_asset_studio.animation_worker import sample as sample_animation
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.garment_worker import closed_outward, triangles
from cryptonyan_asset_studio.rig_doctor import audit_weights
from cryptonyan_asset_studio.rig_worker import sample as sample_weights
from cryptonyan_asset_studio.storage import write_json
from cryptonyan_asset_studio.wardrobe_review import rank, specification


def geometry(obj):
    import math
    points, faces = triangles(obj, True)
    if not points or not faces or any(not math.isfinite(v) for p in points for v in p):
        raise ValueError("Empty or nonfinite evaluated mesh")
    if len(points) != len(obj.data.vertices):
        raise ValueError("Vertex topology changed")
    return points, faces


def crossings(points, faces, target, source, scale, tolerance):
    """One bounded ray per unique edge, excluding endpoint contacts. Not coplanar testing."""
    edges = sorted({tuple(sorted((a, b))) for face in faces for a, b in zip(face, face[1:]+face[:1])})
    count, evidence = 0, []
    epsilon = tolerance/scale
    for a, b in edges:
        delta = points[b]-points[a]
        length = delta.length
        if length <= 2*epsilon:
            continue
        direction = delta/length
        point, _, triangle, distance = target.ray_cast(points[a]+direction*epsilon, direction, length-2*epsilon)
        if point is not None:
            count += 1
            if len(evidence) < 100:
                evidence.append({"source": source, "edge": [a, b], "target_triangle": triangle})
    return count, evidence


def review(spec, output):
    import bpy
    from mathutils.bvhtree import BVHTree
    spec = specification(spec)
    if bpy.data.libraries or bpy.utils.blend_paths(absolute=True, packed=False, local=False):
        raise ValueError("Require a self-contained source; pack resources first")
    scene = bpy.context.scene
    if any(m.name.startswith("CN_WR_") for m in scene.timeline_markers):
        raise ValueError("Reserved review markers already exist")
    selected = [spec["body"], *spec["garments"]]
    objects = [bpy.data.objects.get(n) for n in selected]
    for obj in objects:
        if (obj is None or obj.type != "MESH" or obj.name not in bpy.context.view_layer.objects
                or obj.hide_viewport or obj.mode != "OBJECT" or obj.constraints
                or len(obj.modifiers) != 1 or obj.modifiers[0].type != "ARMATURE"):
            raise ValueError("Select local Object-mode meshes with only their Armature modifier")
        obj.hide_set(False)
        if not obj.visible_get() or obj.matrix_world.to_3x3().determinant() <= 1e-12:
            raise ValueError("Excluded, reflected or singular mesh")
    body, garments = objects[0], objects[1:]
    if any(len(o.data.vertices) > 10000 for o in garments) or sum(len(o.data.vertices) for o in garments) > 20000:
        raise ValueError("Garment vertex budget exceeded")
    weight_spec = {"armature": spec["armature"], "meshes": selected, "max_influences": spec["max_influences"]}
    weights = sample_weights(weight_spec)
    report = {"schema": "cryptonyan.wardrobe-report/1", "specification": spec, "clips": [],
              "weight_audit": audit_weights(weights, weight_spec), "flagged_samples": 0,
              "visual_quality_validated": False, "surface_collision_certified": False,
              "method": "nearest_triangle_signed_distance_and_bvh_edge_rays",
              "coverage": {"sampled_deformed_meshes": True, "garment_garment": False,
                           "continuous_collision": False, "cloth_simulation": False, "automatic_repair": False},
              "blender": bpy.app.version_string}
    work, saved_bytes = 0, 0
    for clip_index, capture in enumerate(spec["captures"], 1):
        trace = sample_animation(capture)
        scale, fps = trace["rig"]["unit_scale_m"], trace["rig"]["fps"]
        clip = {"index": clip_index, "capture": capture, "animation_audit": audit_trace(trace, capture["settings"]),
                "review_file": f"review-{clip_index:02d}.blend", "garments": []}
        samples = {g.name: [] for g in garments}
        for frame in range(capture["start_frame"], capture["end_frame"]+1, capture["step_frames"]):
            scene.frame_set(frame); bpy.context.view_layer.update()
            points, faces = geometry(body)
            closed_outward(points, faces)
            tree = BVHTree.FromPolygons(points, faces, all_triangles=True)
            work += len(points)+len(faces)
            for garment in garments:
                gp, gf = geometry(garment)
                work += len(gp)+len(gf)
                if work > 8000000:
                    raise ValueError("Combined evaluated geometry/frame budget exceeded")
                bad, depth = [], 0.0
                for index, point in enumerate(gp):
                    near, normal, _, _ = tree.find_nearest(point)
                    signed = (point-near).dot(normal)*scale
                    if signed < -spec["tolerance_m"]:
                        bad.append(index); depth = max(depth, -signed)
                # Probe edges in both directions of the mesh pair. Unlike a vertex-only
                # check, this catches a large face slicing the body with all vertices outside.
                garment_tree = BVHTree.FromPolygons(gp, gf, all_triangles=True)
                count, evidence = crossings(points, faces, garment_tree, "body", scale, spec["tolerance_m"])
                other, more = crossings(gp, gf, tree, "garment", scale, spec["tolerance_m"])
                samples[garment.name].append({"frame": frame, "time_s": (frame-capture["start_frame"])/fps,
                    "negative_signed_distance_vertices": len(bad), "indices": bad[:100],
                    "indices_truncated": len(bad)>100, "max_depth_m": depth,
                    "surface_crossing_edges": count+other, "crossing_edges": (evidence+more)[:100],
                    "crossing_edges_truncated": count+other>100,
                    "flagged": bool(bad or count or other)})
        for garment in garments:
            rows = samples[garment.name]
            clip["garments"].append({"name": garment.name, "samples": rows,
                "flagged_frames": sum(s["flagged"] for s in rows), "worst": max(rows, key=rank)})
        worst_garment = max(clip["garments"], key=lambda g: rank(g["worst"]))
        worst = worst_garment["worst"]
        clip["review_frame"] = worst["frame"]
        for marker in list(scene.timeline_markers):
            if marker.name.startswith("CN_WR_"):
                scene.timeline_markers.remove(marker)
        for frame in range(capture["start_frame"], capture["end_frame"]+1, capture["step_frames"]):
            if any(s["frame"] == frame and s["flagged"] for rows in samples.values() for s in rows):
                scene.timeline_markers.new(f"CN_WR_{frame}", frame=frame)
        scene.frame_start, scene.frame_end = capture["start_frame"], capture["end_frame"]
        scene.frame_set(worst["frame"]); bpy.context.view_layer.update()
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        active = bpy.data.objects[worst_garment["name"]]; active.select_set(True)
        bpy.context.view_layer.objects.active = active
        scene["cryptonyan_wardrobe_window"] = clip_index
        if sample_weights(weight_spec) != weights:
            raise ValueError("Source skin weights changed")
        path = output / clip["review_file"]
        bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False, copy=True, relative_remap=False)
        saved_bytes += path.stat().st_size
        if saved_bytes > 1024*1024*1024:
            raise ValueError("Review copies exceed 1 GiB")
        report["flagged_samples"] += sum(g["flagged_frames"] for g in clip["garments"])
        report["clips"].append(clip)
    # Verify the persisted rig binding and base weights, not only the in-memory data.
    for clip in report["clips"]:
        bpy.ops.wm.open_mainfile(filepath=str(output / clip["review_file"]), load_ui=False, use_scripts=False)
        if sample_weights(weight_spec) != weights or bpy.context.scene.frame_current != clip["review_frame"]:
            raise ValueError("Saved review differs from captured state")
    write_json(output / "wardrobe.json", report)


if __name__ == "__main__":
    import bpy
    request = Path(sys.argv[sys.argv.index("--")+1])
    try:
        bpy.ops.wm.open_mainfile(filepath=str(request.parent / "source.blend"), load_ui=False, use_scripts=False)
        review(read_json(request), request.parent)
    except Exception as error:
        write_json(request.parent / "worker_error.json", {"code": error.code if isinstance(error, WorkerFailure) else "invalid_asset"})
        raise SystemExit(1)
