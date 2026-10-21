# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only animation diagnostics, in metres/seconds and quaternion WXYZ.

No Blender import: traces from any evaluated sampler can use the same checks.
Contacts are declarations, not inferred from a low paw or a keyframe name.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import threading
import time

from .executors import BudgetExpired, ExecutionContext, WorkerFailure, WORKER_MESSAGES, run_process
from .storage import digest, write_json


LIMITS = {"loop_position_m": 0.02, "loop_rotation_deg": 5.0,
          "root_drift_m": 0.02, "root_rotation_deg": 5.0,
          "speed_m_s": 15.0, "acceleration_m_s2": 200.0,
          "angular_speed_deg_s": 720.0, "contact_speed_m_s": 0.10}
MAX_JSON = 32 * 1024 * 1024


def number(value, low=0, high=1e6):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError("Expected a finite number within bounds")
    return value


def name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid animation or bone name")
    return value


def exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Missing or unknown fields")


def parse_settings(value):
    exact(value, ("root", "bones", "loop", "motion", "contact_space", "contacts"), ("thresholds",))
    root = name(value["root"])
    bones = value["bones"]
    if not isinstance(bones, list) or not 1 <= len(bones) <= 64:
        raise ValueError("Select 1 to 64 non-root bones")
    bones = [name(b) for b in bones]
    if len(set(bones)) != len(bones) or root in bones:
        raise ValueError("Bone selection must be unique and exclude root")
    if type(value["loop"]) is not bool or value["motion"] not in ("in_place", "root_motion"):
        raise ValueError("Invalid loop or motion declaration")
    if value["contact_space"] not in ("unknown", "world"):
        raise ValueError("Declare whether the sampled trajectory includes world movement")
    thresholds = value.get("thresholds", {})
    exact(thresholds, (), LIMITS)
    thresholds = {**LIMITS, **{k: number(v, 0, 1e6) for k, v in thresholds.items()}}
    contacts = value["contacts"]
    if not isinstance(contacts, list) or len(contacts) > 128:
        raise ValueError("Too many contact windows")
    parsed = []
    for contact in contacts:
        exact(contact, ("bone", "start_s", "end_s"))
        bone = name(contact["bone"])
        start, end = number(contact["start_s"], 0, 600), number(contact["end_s"], 0, 600)
        if bone not in bones or start >= end:
            raise ValueError("Invalid contact window")
        if any(p["bone"] == bone and start < p["end_s"] and end > p["start_s"] for p in parsed):
            raise ValueError("Overlapping contact windows")
        parsed.append({"bone": bone, "start_s": start, "end_s": end})
    return {**value, "bones": bones, "thresholds": thresholds,
            "contacts": sorted(parsed, key=lambda c: (c["start_s"], c["bone"]))}


def vector(value, count):
    if not isinstance(value, list) or len(value) != count:
        raise ValueError("Invalid vector")
    return [number(v, -1e6, 1e6) for v in value]


def subtract(a, b):
    return [x - y for x, y in zip(a, b)]


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def conjugate(q):
    return [q[0], -q[1], -q[2], -q[3]]


def multiply(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]


def angle(a, b):
    return math.degrees(2 * math.acos(min(1.0, abs(sum(x*y for x, y in zip(a, b))))))


def relative(pose, root):
    inverse = conjugate(root["rotation"])
    delta = subtract(pose["position"], root["position"])
    return {"position": multiply(multiply(inverse, [0, *delta]), root["rotation"])[1:],
            "rotation": multiply(inverse, pose["rotation"])}


def parse_trace(value, settings):
    exact(value, ("schema", "clip", "samples"), ("provenance", "rig", "space"))
    if value["schema"] != "cryptonyan.animation-trace/1":
        raise ValueError("Unsupported animation trace")
    if value.get("space", "world") not in ("world", "component"):
        raise ValueError("Unsupported pose coordinate space")
    if value.get("space") == "component" and settings["contact_space"] == "world":
        raise ValueError("Component-space poses cannot establish world contacts")
    name(value["clip"])
    samples = value["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= 2001:
        raise ValueError("Expected 2 to 2001 samples")
    expected = {settings["root"], *settings["bones"]}
    previous = -1
    parsed = []
    for sample in samples:
        exact(sample, ("time_s", "poses"))
        t = number(sample["time_s"], 0, 600)
        if (previous == -1 and t != 0) or (previous != -1 and t - previous < 1e-6):
            raise ValueError("Sample times must start at zero and strictly increase")
        exact(sample["poses"], expected)
        poses = {}
        for bone, pose in sample["poses"].items():
            exact(pose, ("position", "rotation"))
            p, q = vector(pose["position"], 3), vector(pose["rotation"], 4)
            length = norm(q)
            if abs(length - 1) > 1e-3:
                raise ValueError("Quaternion must have unit length (WXYZ)")
            poses[bone] = {"position": p, "rotation": [v/length for v in q]}
        parsed.append({"time_s": t, "poses": poses})
        previous = t
    for contact in settings["contacts"]:
        if contact["end_s"] > previous:
            raise ValueError("Contact window extends beyond clip")
    return parsed


def audit_trace(trace, settings):
    """Return numerical findings and unapproved effect timing candidates; never repair."""
    settings = parse_settings(settings)
    samples = parse_trace(trace, settings)
    root, limits = settings["root"], settings["thresholds"]
    times = [s["time_s"] for s in samples]
    findings, metrics = [], {}

    def check(code, bone, measured, threshold, time_s=None):
        if measured > threshold:
            findings.append({"code": code, "bone": bone, "measured": measured,
                             "threshold": threshold, "time_s": time_s, "severity": "warning"})

    roots = [s["poses"][root] for s in samples]
    root_travel = sum(norm(subtract(b["position"], a["position"])) for a, b in zip(roots, roots[1:]))
    root_excursion = max(norm(subtract(p["position"], roots[0]["position"])) for p in roots)
    root_rotation = max(angle(p["rotation"], roots[0]["rotation"]) for p in roots)
    if settings["motion"] == "in_place":
        check("root_drift", root, root_excursion, limits["root_drift_m"])
        check("root_rotation", root, root_rotation, limits["root_rotation_deg"])
    for bone in [root, *settings["bones"]]:
        # Root world trajectory; other bones in the moving root's rigid coordinate frame.
        poses = roots if bone == root else [relative(s["poses"][bone], s["poses"][root]) for s in samples]
        speeds, angular, velocities, midpoints = [], [], [], []
        for i in range(1, len(samples)):
            dt = times[i] - times[i-1]
            velocity = [v/dt for v in subtract(poses[i]["position"], poses[i-1]["position"])]
            velocities.append(velocity)
            midpoints.append((times[i] + times[i-1]) / 2)
            speeds.append(norm(velocity))
            angular.append(angle(poses[i]["rotation"], poses[i-1]["rotation"]) / dt)
        acceleration = [norm(subtract(velocities[i], velocities[i-1])) / (midpoints[i]-midpoints[i-1])
                        for i in range(1, len(velocities))]
        metric = {"space": trace.get("space", "world") if bone == root else "root_relative",
                  "max_speed_m_s": max(speeds), "max_angular_speed_deg_s": max(angular),
                  "max_acceleration_m_s2": max(acceleration, default=None)}
        for code, values, key, offset in (("speed_spike", speeds, "speed_m_s", 1),
                                          ("angular_spike", angular, "angular_speed_deg_s", 1),
                                          ("acceleration_spike", acceleration, "acceleration_m_s2", 2)):
            if values:
                peak = max(values)
                check(code, bone, peak, limits[key], times[values.index(peak) + offset])
        if settings["loop"] and bone != root:
            distance = norm(subtract(poses[-1]["position"], poses[0]["position"]))
            rotation = angle(poses[-1]["rotation"], poses[0]["rotation"])
            metric.update(loop_position_m=distance, loop_rotation_deg=rotation)
            check("loop_position", bone, distance, limits["loop_position_m"])
            check("loop_rotation", bone, rotation, limits["loop_rotation_deg"])
        metrics[bone] = metric
    contacts, events = [], []
    for index, contact in enumerate(settings["contacts"]):
        bone, start, end = contact["bone"], contact["start_s"], contact["end_s"]
        indices = [i for i, t in enumerate(times) if start <= t <= end]
        status, speed = "not_assessed_unknown_world_motion", None
        if settings["contact_space"] == "world":
            status = "not_assessed_insufficient_samples"
            # Both declared boundaries must be sampled: never silently ignore touchdown/liftoff.
            if len(indices) >= 2 and abs(times[indices[0]]-start) < 1e-6 and abs(times[indices[-1]]-end) < 1e-6:
                speed = max(norm(subtract(samples[b]["poses"][bone]["position"],
                                          samples[a]["poses"][bone]["position"])) / (times[b]-times[a])
                            for a, b in zip(indices, indices[1:]))
                status = "sliding" if speed > limits["contact_speed_m_s"] else "within_threshold"
                check("contact_sliding", bone, speed, limits["contact_speed_m_s"], start)
        contacts.append({**contact, "status": status, "max_speed_m_s": speed})
        events.append({"id": f"contact-{index:03d}", "kind": "contact_start", "bone": bone,
                       "time_s": start, "origin": "declared_contact_window",
                       "contact_status": status, "approved": False})
    identity = hashlib.sha256(json.dumps({"trace": trace, "settings": settings}, sort_keys=True,
                                        allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    return {"schema": "cryptonyan.animation-audit/1", "identity": identity, "clip": trace["clip"],
            "status": "issues_found" if findings else "no_findings_within_scope", "read_only": True,
            "provenance": trace.get("provenance"), "rig": trace.get("rig"),
            "settings": settings, "duration_s": times[-1], "sample_count": len(samples),
            "root": {"travel_m": root_travel, "excursion_m": root_excursion,
                     "net_displacement_m": subtract(roots[-1]["position"], roots[0]["position"]),
                     "max_rotation_deg": root_rotation},
            "bones": metrics, "contacts": contacts, "findings": findings,
            "effect_candidates": {"schema": "cryptonyan.animation-events/1", "events": events,
                                  "requires_review": True, "applied_to_engine": False},
            "coverage": {"loop_pose": settings["loop"], "loop_velocity": False,
                         "acceleration": len(samples) >= 3, "skin_weights": False,
                         "unreal_runtime": False, "automatic_repair": False},
            "limitations": ["Sampled poses only; sub-sample motion may be missed.",
                            "Contacts measure selected bone origins, not sole surfaces or terrain collision.",
                            "Root-relative checks remove root translation/rotation, not scale.",
                            "No gait, deformation, retargeting or visual quality certification."]}


def read_json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError("Missing or oversized JSON input")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("JSON input grew beyond budget")
    return json.loads(raw.decode("utf-8"))


def parse_capture(value):
    exact(value, ("armature", "action", "start_frame", "end_frame", "step_frames", "settings"), ("action_slot",))
    name(value["armature"])
    name(value["action"])
    if "action_slot" in value:
        name(value["action_slot"])
    for key in ("start_frame", "end_frame", "step_frames"):
        number(value[key], 1 if key == "step_frames" else -100000, 100000)
        if type(value[key]) is not int:
            raise ValueError("Frame selection must use integers")
    start, end, step = value["start_frame"], value["end_frame"], value["step_frames"]
    if end <= start or (end-start) % step or (end-start)//step + 1 > 2001:
        raise ValueError("Invalid sampling window; include both endpoints, at most 2001 samples")
    return {**value, "settings": parse_settings(value["settings"])}


def capture_blender(source, specification, output, blender, timeout=120):
    """Audit a self-contained blend snapshot in a fresh worker; output must not exist."""
    specification = parse_capture(specification)
    number(timeout, 1, 600)
    source, output, blender = Path(source).resolve(), Path(output).resolve(), Path(blender).resolve()
    if source.suffix.lower() != ".blend" or not source.is_file() or not 1 <= source.stat().st_size <= 512*1024*1024:
        raise ValueError("Expected a local .blend file of at most 512 MiB")
    if not blender.is_file():
        raise ValueError("Blender executable missing")
    before = digest(source)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    snapshot = output / "source.blend"
    shutil.copyfile(source, snapshot)
    if digest(snapshot) != before or digest(source) != before:
        raise ValueError("Source changed during snapshot")
    write_json(output / "request.json", specification)
    context = ExecutionContext(output, output, ("source.blend",), threading.Event(), time.monotonic()+timeout)
    worker = Path(__file__).with_name("animation_worker.py")
    run_process([str(blender), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                 "--python-exit-code", "1", "--python", str(worker), "--", str(output / "request.json")], context)
    if digest(source) != before or digest(snapshot) != before:
        raise ValueError("Source changed during audit")
    trace = read_json(output / "trace.json")
    trace["provenance"] = {"source_sha256": before, "sampler": "blender_evaluated",
                           "blender": trace.get("provenance", {}).get("blender"),
                           "capture": specification}
    report = audit_trace(trace, specification["settings"])
    write_json(output / "trace.json", trace)
    write_json(output / "audit.json", report)
    write_json(output / "events.json", {**report["effect_candidates"], "audit_identity": report["identity"],
                                        "clip": trace["clip"]})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Animation Doctor; no asset or effect mutation")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="Sample a self-contained Blender rig/action and audit it")
    capture.add_argument("source", type=Path)
    capture.add_argument("specification", type=Path)
    capture.add_argument("--blender", required=True, type=Path)
    capture.add_argument("--timeout", type=int, default=120)
    offline = sub.add_parser("audit", help="Audit a normalized evaluated trace")
    offline.add_argument("trace", type=Path)
    offline.add_argument("settings", type=Path)
    for command in (capture, offline):
        command.add_argument("--output", required=True, type=Path, help="New directory, never overwritten")
    args = parser.parse_args(argv)
    if args.command == "capture":
        report = capture_blender(args.source, read_json(args.specification), args.output, args.blender, args.timeout)
    else:
        trace = read_json(args.trace)
        report = audit_trace(trace, read_json(args.settings))
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        write_json(args.output / "audit.json", report)
        write_json(args.output / "events.json", {**report["effect_candidates"], "audit_identity": report["identity"],
                                                "clip": trace["clip"]})
    print(json.dumps({"status": report["status"], "findings": len(report["findings"]),
                      "output": str(args.output.resolve())}))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, WorkerFailure, BudgetExpired) as error:
        detail = WORKER_MESSAGES[error.code] if isinstance(error, WorkerFailure) else (
            "Blender timeout exceeded" if isinstance(error, BudgetExpired) else
            "check input schema, new output directory and Blender executable")
        print("Animation audit failed: " + detail, file=sys.stderr)
        raise SystemExit(2)
