# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only base-mesh diagnostics. No claim about evaluated geometry or aesthetic quality."""
from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

from .schema import SuccessCriteria, integer, keys, now

REPORT_SCHEMA = "cryptonyan.asset-doctor/1"
MAX_VERTICES = 200000
MAX_FACES = 100000
MAX_CORNERS = 500000


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    evidence: dict
    suggested_repair: str


def _vector(value, size=3):
    if not isinstance(value, (list, tuple)) or len(value) != size or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Expected a finite numeric vector")
    return tuple(value)


def _area(points):
    # Newell's area: a diagnostic candidate, not robust self-intersection repair.
    normal = [0.0, 0.0, 0.0]
    for a, b in zip(points, points[1:] + points[:1]):
        for i in range(3):
            j, k = (i + 1) % 3, (i + 2) % 3
            normal[i] += (a[j] - b[j]) * (a[k] + b[k])
    return math.sqrt(sum(v * v for v in normal)) * 0.5


def audit_mesh(mesh, criteria=None):
    """Audit normalized fixture/base-mesh data, rejecting pathological allocation sizes."""
    criteria = criteria or SuccessCriteria()
    name = mesh.get("name")
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise ValueError("Mesh name is required")
    raw_vertices, faces = mesh.get("vertices"), mesh.get("faces")
    if not isinstance(raw_vertices, list) or len(raw_vertices) > MAX_VERTICES or not isinstance(faces, list) or len(faces) > MAX_FACES:
        raise ValueError("Mesh exceeds MVP complexity budget or has invalid arrays")
    vertices = [_vector(v) for v in raw_vertices]
    if any(not isinstance(f, list) for f in faces) or sum(map(len, faces)) > MAX_CORNERS:
        raise ValueError("Mesh corner budget exceeded or invalid faces")
    scale = _vector(mesh.get("scale", [1, 1, 1]))
    rotation = _vector(mesh.get("rotation", [0, 0, 0]))
    findings = []

    def add(code, severity, evidence, repair):
        findings.append(asdict(Finding(code, severity, evidence, repair)))

    invalid, degenerate, seen, duplicate = [], [], set(), []
    edges, directions = Counter(), Counter()
    triangles = 0
    for index, face in enumerate(faces):
        if len(face) < 3 or any(type(v) is not int or v < 0 or v >= len(vertices) for v in face):
            invalid.append(index)
            continue
        triangles += len(face) - 2
        if len(set(face)) != len(face) or _area([vertices[v] for v in face]) <= 1e-12:
            degenerate.append(index)
        canonical = tuple(sorted(face))
        if canonical in seen:
            duplicate.append(index)
        seen.add(canonical)
        for a, b in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directions[(a, b)] += 1
    for code, ids in (("invalid_faces", invalid), ("degenerate_candidates", degenerate), ("duplicate_candidates", duplicate)):
        if ids:
            add(code, "error", {"count": len(ids), "face_indices": ids[:100]}, "Review affected faces on a copy; no automatic deletion.")
    boundary = sum(count == 1 for count in edges.values())
    nonmanifold = sum(count > 2 for count in edges.values())
    winding = sum(count == 2 and (directions[(a, b)] == 2 or directions[(b, a)] == 2) for (a, b), count in edges.items())
    if boundary or nonmanifold or winding:
        add("edge_topology", "warning", {"boundary_edges": boundary, "overused_edges": nonmanifold,
            "inconsistent_winding_edges": winding}, "Review intentional open surfaces and winding before editing.")
    if not vertices or not faces:
        add("empty_mesh", "error", {"vertices": len(vertices), "faces": len(faces)}, "Supply a non-empty mesh.")
    actual_triangles = integer(mesh.get("triangle_count", triangles), "triangle_count", 0, MAX_CORNERS)
    actual_edges = integer(mesh.get("edge_count", len(edges)), "edge_count", 0, MAX_CORNERS)
    if actual_triangles > criteria.max_triangles:
        add("triangle_budget", "error", {"actual": actual_triangles, "limit": criteria.max_triangles}, "Create and review an optimized copy or LOD.")
    if scale != (1, 1, 1):
        add("unapplied_scale", "warning", {"scale": scale}, "Review rigs, parenting and modifiers before applying transforms; MVP never applies them.")
    uv_layers = mesh.get("uv_layers", [])
    materials = mesh.get("material_slots", [])
    if not isinstance(uv_layers, list) or not isinstance(materials, list) or any(not isinstance(v, str) for v in uv_layers + materials):
        raise ValueError("Invalid UV layers or material slots")
    if not uv_layers:
        add("missing_uv", "warning", {}, "Use Loopcut inspect_uv/uv_unwrap on an owned copy if this material needs UVs.")
    guards = mesh.get("repair_guards", [])
    if not isinstance(guards, list) or any(not isinstance(v, str) for v in guards):
        raise ValueError("Invalid repair guards")
    if guards:
        add("repair_guard", "warning", {"reasons": guards}, "Audit only; copying/renaming this object requires manual review.")
    bounds = [[min(v[i] for v in vertices) for i in range(3)], [max(v[i] for v in vertices) for i in range(3)]] if vertices else None
    return {"name": name, "type": "MESH", "vertices": len(vertices), "edges": actual_edges,
            "faces": len(faces), "triangles": actual_triangles, "bounds_local": bounds,
            "bounds_world": mesh.get("bounds_world"), "scale": scale, "rotation_euler_radians": rotation,
            "rotation_mode": mesh.get("rotation_mode", "XYZ"),
            "material_slots": materials, "uv_layers": uv_layers, "findings": findings,
            "topology": {"boundary_edges": boundary, "overused_edges": nonmanifold,
                         "inconsistent_winding_edges": winding, "vertex_manifold": "not_evaluated",
                         "self_intersections": "not_evaluated"},
            "loopcut": mesh.get("loopcut", {})}


def report(objects, criteria=None, *, source="fixture", repairs=None):
    criteria = criteria or SuccessCriteria()
    findings = [f for obj in objects for f in obj["findings"]]
    counts = dict(Counter(f["severity"] for f in findings))
    return {"schema": REPORT_SCHEMA, "created_at": now(), "source": source,
            "geometry_basis": "base_mesh", "dry_run": not bool(repairs), "repairs": repairs or [],
            "objects": objects, "severity_counts": counts,
            "passed": any(obj["type"] == "MESH" for obj in objects) and counts.get("error", 0) == 0 and
                      (criteria.allow_warnings or counts.get("warning", 0) == 0),
            "limitations": ["No evaluated modifier geometry, vertex-manifold proof or self-intersection test.",
                            "No aesthetic score. Degenerate faces are candidates at an absolute 1e-12 area threshold."]}


def audit_fixture(path, targets=(), criteria=None):
    if Path(path).stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Fixture exceeds 20 MiB budget")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "cryptonyan.mesh-fixture/1" or not isinstance(data.get("objects"), list):
        raise ValueError("Unsupported fixture schema")
    objects = data["objects"]
    if len(objects) > 128 or any(not isinstance(obj, dict) for obj in objects):
        raise ValueError("Invalid objects or too many objects")
    for obj in objects:
        keys(obj, ("name", "vertices", "faces", "uv_layers", "material_slots", "scale", "rotation", "repair_guards"))
    if any(not isinstance(obj.get("name"), str) for obj in objects) or len({obj["name"] for obj in objects}) != len(objects):
        raise ValueError("Fixture object names must be unique strings")
    if targets and set(targets) - {obj.get("name") for obj in objects}:
        raise ValueError("Target asset not found")
    return report([audit_mesh(obj, criteria) for obj in objects if not targets or obj.get("name") in targets], criteria)


def blender_mesh(obj):
    """Called only in the child. Reuse upstream scene summaries and UV mathematics."""
    from loopcut import object_info, uv_tools
    mesh = obj.data
    if len(mesh.vertices) > MAX_VERTICES or len(mesh.polygons) > MAX_FACES or len(mesh.loops) > MAX_CORNERS:
        raise ValueError("Mesh exceeds MVP complexity budget")
    mesh.calc_loop_triangles()
    faces = [list(p.vertices) for p in mesh.polygons]
    vertices = [list(v.co) for v in mesh.vertices]
    world = [list(obj.matrix_world @ v.co) for v in mesh.vertices]
    if obj.rotation_mode == "QUATERNION":
        rotation = obj.rotation_quaternion.to_euler()
    elif obj.rotation_mode == "AXIS_ANGLE":
        from mathutils import Quaternion
        rotation = Quaternion(obj.rotation_axis_angle[1:], obj.rotation_axis_angle[0]).to_euler()
    else:
        rotation = obj.rotation_euler
    guards = [label for label, active in (
        ("modifiers", bool(obj.modifiers)), ("shape_keys", bool(mesh.shape_keys)),
        ("parent", obj.parent is not None), ("constraints", bool(obj.constraints)),
        ("animation", obj.animation_data is not None or mesh.animation_data is not None),
        ("linked_data", obj.library is not None or mesh.library is not None),
        ("library_override", obj.override_library is not None or mesh.override_library is not None),
        ("vertex_groups", bool(obj.vertex_groups)), ("children", bool(obj.children))
    ) if active]
    upstream = {"object_info": object_info.brief(obj), "uv_audit": "no_active_uv"}
    # Upstream UV gutter/overlap analysis is deliberately bounded for this MVP.
    if mesh.uv_layers.active and faces:
        if len(mesh.loops) <= 3000:
            uvs = [[list(mesh.uv_layers.active.data[i].uv) for i in p.loop_indices] for p in mesh.polygons]
            stats = uv_tools.audit(world, faces, uvs)
            upstream["uv_audit"] = {k: stats[k] for k in ("islands", "zero", "flipped", "outside", "overlap", "density")}
        else:
            upstream["uv_audit"] = "skipped_complexity_budget"
    return {"name": obj.name, "vertices": vertices, "faces": faces,
            "edge_count": len(mesh.edges), "triangle_count": len(mesh.loop_triangles),
            "scale": list(obj.scale), "rotation": list(rotation), "rotation_mode": obj.rotation_mode,
            "bounds_world": [[min(v[i] for v in world) for i in range(3)], [max(v[i] for v in world) for i in range(3)]] if world else None,
            "material_slots": [slot.material.name if slot.material else "" for slot in obj.material_slots],
            "uv_layers": [uv.name for uv in mesh.uv_layers], "repair_guards": guards, "loopcut": upstream}


def audit_blender(targets=(), criteria=None, *, repair_copy=False):
    import bpy
    import re
    objects = list(bpy.context.scene.objects)
    if targets and set(targets) - {obj.name for obj in objects}:
        raise ValueError("Target asset not found")
    selected = [obj for obj in objects if not targets or obj.name in targets]
    if len(selected) > 128:
        raise ValueError("Scene object budget exceeded")
    rows, repairs = [], []
    collection = None
    for obj in selected:
        if obj.type != "MESH":
            rows.append({"name": obj.name, "type": obj.type, "findings": [asdict(Finding(
                "unsupported_object", "warning", {"type": obj.type}, "Use a type-specific auditor; Asset Doctor audits meshes."))]})
            continue
        data = blender_mesh(obj)
        rows.append(audit_mesh(data, criteria))
        if repair_copy and not data["repair_guards"]:
            if collection is None:
                collection = bpy.data.collections.new("CryptoNyan_Reviewed_Copies")
                bpy.context.scene.collection.children.link(collection)
            duplicate = obj.copy()
            duplicate.data = obj.data.copy()
            duplicate.name = "SM_" + re.sub(r"[^A-Za-z0-9_]", "_", obj.name)[:50]
            collection.objects.link(duplicate)
            repairs.append({"operation": "copy_and_organize", "source": obj.name, "copy": duplicate.name,
                            "collection": collection.name, "transforms_changed": False})
    result = report(rows, criteria, source="blender", repairs=repairs)
    result["blender_version"] = bpy.app.version_string
    return result
