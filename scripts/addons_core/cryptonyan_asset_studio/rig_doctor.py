# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, read-only skin-weight diagnostics for explicitly selected existing rigs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time

from .animation_doctor import exact, name, number, read_json
from .executors import BudgetExpired, ExecutionContext, WorkerFailure, WORKER_MESSAGES, run_process
from .storage import digest, write_json

MAX_VERTICES = 200000
MAX_ASSIGNMENTS = 200000


def specification(value):
    exact(value, ("armature", "meshes"), ("max_influences", "weight_epsilon", "sum_tolerance"))
    name(value["armature"])
    meshes = value["meshes"]
    if not isinstance(meshes, list) or not 1 <= len(meshes) <= 32:
        raise ValueError("Select 1 to 32 meshes explicitly")
    meshes = [name(v) for v in meshes]
    if len(set(meshes)) != len(meshes) or value["armature"] in meshes:
        raise ValueError("Select distinct mesh and armature objects")
    count = value.get("max_influences", 4)
    if type(count) is not int or not 1 <= count <= 32:
        raise ValueError("max_influences must be 1 to 32")
    return {**value, "meshes": meshes, "max_influences": count,
            "weight_epsilon": number(value.get("weight_epsilon", 1e-5), 0, .01),
            "sum_tolerance": number(value.get("sum_tolerance", .001), 0, .1)}


def audit_weights(snapshot, spec):
    spec = specification(spec)
    exact(snapshot, ("schema", "armature", "bones", "meshes"), ("provenance",))
    if snapshot["schema"] != "cryptonyan.rig-weights/1" or snapshot["armature"] != spec["armature"]:
        raise ValueError("Snapshot does not match requested armature")
    bones = snapshot["bones"]
    if not isinstance(bones, list) or not 1 <= len(bones) <= 512:
        raise ValueError("Expected 1 to 512 bones")
    by_name = {}
    for bone in bones:
        exact(bone, ("name", "parent", "deform"))
        bone_name = name(bone["name"])
        if bone_name in by_name or type(bone["deform"]) is not bool:
            raise ValueError("Invalid bone mapping")
        if bone["parent"] is not None:
            name(bone["parent"])
        by_name[bone_name] = bone
    for bone_name in by_name:
        seen, current = set(), bone_name
        while current is not None:
            if current in seen or current not in by_name:
                raise ValueError("Bone hierarchy contains a cycle or missing parent")
            seen.add(current)
            current = by_name[current]["parent"]
    deform = {b for b in by_name if by_name[b]["deform"]}
    if not deform:
        raise ValueError("Armature has no deforming bones")
    meshes = snapshot["meshes"]
    if not isinstance(meshes, list) or len(meshes) != len(spec["meshes"]) or [m.get("name") for m in meshes if isinstance(m, dict)] != spec["meshes"]:
        raise ValueError("Snapshot mesh selection differs from request")
    findings, results, vertices_total, assignments = [], [], 0, 0
    for mesh in meshes:
        exact(mesh, ("name", "groups", "weights"), ("capture",))
        groups, weights = mesh["groups"], mesh["weights"]
        if not isinstance(groups, list) or len(groups) > 1024:
            raise ValueError("Vertex group budget exceeded")
        groups = [name(g) for g in groups]
        if len(set(groups)) != len(groups):
            raise ValueError("Duplicate vertex groups")
        if not isinstance(weights, list) or not 1 <= len(weights) <= MAX_VERTICES:
            raise ValueError("Invalid vertex count")
        vertices_total += len(weights)
        if vertices_total > MAX_VERTICES:
            raise ValueError("Combined vertex budget exceeded")
        issues = {key: {"count": 0, "vertices": []} for key in (
            "unweighted_vertices", "weight_sum", "too_many_influences", "invalid_weights")}
        max_count, min_sum, max_sum, used = 0, None, 0, set()
        for index, entries in enumerate(weights):
            if not isinstance(entries, list) or len(entries) > len(groups):
                raise ValueError("Invalid weight assignments")
            assignments += len(entries)
            if assignments > MAX_ASSIGNMENTS:
                raise ValueError("Weight assignment budget exceeded")
            visited, active, invalid, total = set(), 0, False, 0.0
            for entry in entries:
                exact(entry, ("group", "weight"))
                group, weight = entry["group"], number(entry["weight"], -1e6, 1e6)
                if type(group) is not int or not 0 <= group < len(groups) or group in visited:
                    raise ValueError("Unknown or duplicate group index")
                visited.add(group)
                if not 0 <= weight <= 1:
                    invalid = True
                elif groups[group] in deform:
                    total += weight
                    if weight > spec["weight_epsilon"]:
                        active += 1
                        used.add(groups[group])
            max_count = max(max_count, active)
            min_sum = total if min_sum is None else min(min_sum, total)
            max_sum = max(max_sum, total)
            flags = {"unweighted_vertices": active == 0, "weight_sum": active > 0 and abs(total-1) > spec["sum_tolerance"],
                     "too_many_influences": active > spec["max_influences"], "invalid_weights": invalid}
            for code, flag in flags.items():
                if flag:
                    issues[code]["count"] += 1
                    if len(issues[code]["vertices"]) < 100:
                        issues[code]["vertices"].append(index)
        for code, evidence in issues.items():
            if evidence["count"]:
                findings.append({"code": code, "mesh": mesh["name"], "severity": "warning", **evidence,
                                 "indices_truncated": evidence["count"] > 100, "automatic_repair": False})
        results.append({"name": mesh["name"], "vertex_count": len(weights), "max_influences": max_count,
                        "deform_weight_sum_range": [min_sum, max_sum],
                        "unused_deform_groups": sorted(set(groups) & deform - used),
                        "non_bone_groups": sorted(set(groups) - set(by_name)),
                        "nondeforming_bone_groups": sorted(set(groups) & (set(by_name) - deform)),
                        "capture": mesh.get("capture")})
    identity = hashlib.sha256(json.dumps({"snapshot": snapshot, "settings": spec}, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"schema": "cryptonyan.rig-audit/1", "identity": identity, "armature": snapshot["armature"],
            "status": "issues_found" if findings else "no_findings_within_scope", "settings": spec,
            "findings": findings, "meshes": results, "bone_count": len(bones), "deform_bone_count": len(deform),
            "roots": sorted(b for b in by_name if by_name[b]["parent"] is None),
            "provenance": snapshot.get("provenance"), "coverage": {"base_vertex_weights": True,
                "evaluated_deformation": False, "constraints_ik": False, "shape_keys": False,
                "unreal_import_influences": False, "automatic_repair": False}}


def capture_blender(source, spec, output, blender, timeout=120):
    spec = specification(spec)
    number(timeout, 1, 600)
    source, output, blender = Path(source).resolve(), Path(output).resolve(), Path(blender).resolve()
    if source.suffix.lower() != ".blend" or not source.is_file() or not 1 <= source.stat().st_size <= 512*1024*1024:
        raise ValueError("Expected a self-contained .blend of at most 512 MiB")
    if not blender.is_file():
        raise ValueError("Blender executable missing")
    before = digest(source)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    snapshot = output / "source.blend"
    shutil.copyfile(source, snapshot)
    if digest(snapshot) != before or digest(source) != before:
        raise ValueError("Source changed during snapshot")
    write_json(output / "request.json", spec)
    context = ExecutionContext(output, output, ("source.blend",), threading.Event(), time.monotonic()+timeout)
    run_process([str(blender), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                 "--python-exit-code", "1", "--python", str(Path(__file__).with_name("rig_worker.py")),
                 "--", str(output / "request.json")], context)
    if digest(source) != before or digest(snapshot) != before:
        raise ValueError("Source changed during audit")
    data = read_json(output / "weights.json")
    data["provenance"] = {**data.get("provenance", {}), "source_sha256": before, "capture": spec}
    report = audit_weights(data, spec)
    write_json(output / "weights.json", data)
    write_json(output / "audit.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Rig Doctor for existing skin weights")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("source", type=Path)
    capture.add_argument("--blender", required=True, type=Path)
    capture.add_argument("--timeout", type=int, default=120)
    offline = sub.add_parser("audit")
    offline.add_argument("snapshot", type=Path)
    for command in (capture, offline):
        command.add_argument("specification", type=Path)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = read_json(args.specification)
    if args.command == "capture":
        report = capture_blender(args.source, spec, args.output, args.blender, args.timeout)
    else:
        report = audit_weights(read_json(args.snapshot), spec)
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        write_json(args.output / "audit.json", report)
    print(json.dumps({"status": report["status"], "findings": len(report["findings"])}))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, WorkerFailure, BudgetExpired) as error:
        message = WORKER_MESSAGES[error.code] if isinstance(error, WorkerFailure) else type(error).__name__
        print("Rig audit failed: " + message, file=sys.stderr)
        raise SystemExit(2)
