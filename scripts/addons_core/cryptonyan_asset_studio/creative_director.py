# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, deterministic recipes for existing Unreal assets; no editor import."""
import argparse
import copy
import json
import math
from pathlib import Path
import re

from .animation_doctor import exact, name, number, read_json, audit_trace
from .game_project import GameProject
from .unreal_material_variants import _hash, _object_path, _file_state, _outside


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", value):
        raise ValueError("Expected a portable identifier")
    return value


def integer(value, low, high):
    if type(value) is not int:
        raise ValueError("Expected integer")
    return number(value, low, high)


def vector(value, low=-100000, high=100000):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("Expected three coordinates")
    return [number(v, low, high) for v in value]


def rows(value, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError("Invalid list size")
    return value


def destination(value):
    if not isinstance(value, str) or not re.fullmatch(r"/Game/CryptoNyan/DirectedReviews/[A-Za-z][A-Za-z0-9_]{0,47}", value):
        raise ValueError("Choose a new /Game/CryptoNyan/DirectedReviews/<Id> folder")
    return value


def recipe(value):
    value = copy.deepcopy(value)
    if not isinstance(value, dict):
        raise ValueError("Expected recipe object")
    kind = value.get("kind")
    if kind == "effects":
        exact(value, ("kind", "destination", "animation", "preview_mesh", "duration_s", "events"))
        value["animation"] = _object_path(value["animation"])
        value["preview_mesh"] = _object_path(value["preview_mesh"])
        duration = number(value["duration_s"], .001, 600)
        ids, triggers = set(), set()
        for event in rows(value["events"], 64):
            exact(event, ("id", "kind", "time_s", "socket", "niagara", "attached", "offset_m", "scale", "reviewed"),
                  ("origin",))
            identity = identifier(event["id"])
            if identity.casefold() in ids or event["kind"] not in ("contact", "dash", "landing", "impact", "cast"):
                raise ValueError("Duplicate ID or unsupported effect event")
            ids.add(identity.casefold())
            number(event["time_s"], 0, duration)
            # Endpoint notifies can fire again at a loop boundary: use [0,duration).
            if event["time_s"] >= duration or type(event["attached"]) is not bool or event["reviewed"] is not True:
                raise ValueError("Require reviewed events strictly before clip end")
            name(event["socket"])
            event["niagara"] = _object_path(event["niagara"])
            event["offset_m"] = vector(event["offset_m"], -10, 10)
            event["scale"] = vector(event["scale"], .01, 10)
            trigger = (round(event["time_s"], 6), event["socket"].casefold(), event["niagara"].casefold())
            if trigger in triggers:
                raise ValueError("Duplicate effect trigger")
            triggers.add(trigger)
            if "origin" in event:
                exact(event["origin"], ("audit_identity", "contact_id", "contact_status"))
                if not re.fullmatch(r"[0-9a-f]{64}", str(event["origin"]["audit_identity"])):
                    raise ValueError("Invalid audit identity")
                name(event["origin"]["contact_id"])
                if event["origin"]["contact_status"] != "within_threshold":
                    raise ValueError("Only measured clean contacts can be imported automatically")
        value["events"].sort(key=lambda e: (e["time_s"], e["id"]))
        primary = {value["animation"].casefold(), value["preview_mesh"].casefold()}
        if len(primary) != 2 or any(e["niagara"].casefold() in primary for e in value["events"]):
            raise ValueError("Source asset roles must be distinct")
    elif kind == "cinematic":
        exact(value, ("kind", "destination", "fps", "shots"))
        fps = integer(value["fps"], 1, 120)
        total, ids = 0, set()
        for shot in rows(value["shots"], 16):
            exact(shot, ("id", "frames", "keys"))
            identity = identifier(shot["id"])
            if identity.casefold() in ids:
                raise ValueError("Duplicate shot ID")
            ids.add(identity.casefold())
            frames = integer(shot["frames"], 2, 36000)
            total += frames
            last = -1
            for key in rows(shot["keys"], 128):
                exact(key, ("frame", "position_m", "rotation_rpy_deg"))
                frame = integer(key["frame"], 0, frames-1)
                if frame <= last:
                    raise ValueError("Camera keys must strictly increase")
                last = frame
                key["position_m"] = vector(key["position_m"])
                key["rotation_rpy_deg"] = vector(key["rotation_rpy_deg"], -360, 360)
            if shot["keys"][0]["frame"] != 0 or shot["keys"][-1]["frame"] != frames-1:
                raise ValueError("Camera keys must include first and last visible frames")
        if total / fps > 600:
            raise ValueError("Cinematic exceeds ten minutes")
    elif kind == "architecture":
        exact(value, ("kind", "destination", "target_level", "anchor_m", "yaw_deg", "modules", "rows"))
        if not isinstance(value["target_level"], str) or not re.fullmatch(r"/Game/CryptoNyan/ReviewMaps/[A-Za-z][A-Za-z0-9_]{0,47}", value["target_level"]):
            raise ValueError("Choose an explicit empty review map")
        value["anchor_m"] = vector(value["anchor_m"])
        number(value["yaw_deg"], -360, 360)
        modules = value["modules"]
        if not isinstance(modules, dict) or not 1 <= len(modules) <= 32:
            raise ValueError("Require 1 to 32 existing mesh modules")
        for key, path in modules.items():
            identifier(key)
            modules[key] = _object_path(path)
        count, ids = 0, set()
        for row in rows(value["rows"], 64):
            exact(row, ("id", "module", "count", "origin_m", "step_m", "yaw_deg", "scale"))
            identity = identifier(row["id"])
            if identity.casefold() in ids or not isinstance(row["module"], str) or row["module"] not in modules:
                raise ValueError("Duplicate row or missing module")
            ids.add(identity.casefold())
            count += integer(row["count"], 1, 256)
            row["origin_m"], row["step_m"] = vector(row["origin_m"]), vector(row["step_m"])
            number(row["yaw_deg"], -360, 360)
            row["scale"] = vector(row["scale"], .01, 100)
        if count > 256:
            raise ValueError("Architecture exceeds 256 actors")
    else:
        raise ValueError("Unsupported director recipe kind")
    destination(value["destination"])
    return value


def operations(spec):
    spec = recipe(spec)
    if spec["kind"] == "effects":
        return [{**event, "offset_cm": [v*100 for v in event["offset_m"]]} for event in spec["events"]]
    if spec["kind"] == "cinematic":
        result, start = [], 0
        for shot in spec["shots"]:
            keys, previous = [], None
            for key in shot["keys"]:
                rotation = key["rotation_rpy_deg"]
                if previous is not None:
                    rotation = [p + (v-p+180) % 360-180 for p, v in zip(previous, rotation)]
                keys.append({"frame": start+key["frame"], "position_cm": [v*100 for v in key["position_m"]],
                             "rotation_rpy_deg": rotation})
                previous = rotation
            result.append({"id": shot["id"], "start": start, "end": start+shot["frames"], "keys": keys})
            start += shot["frames"]
        return result
    result, seen = [], set()
    angle = math.radians(spec["yaw_deg"])
    for row in spec["rows"]:
        for i in range(row["count"]):
            x, y, z = [a+i*b for a, b in zip(row["origin_m"], row["step_m"])]
            local = [x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle), z]
            position = [number(a+b, -100000, 100000)*100 for a, b in zip(local, spec["anchor_m"])]
            signature = tuple(round(v, 3) for v in position)
            if signature in seen:
                raise ValueError("Coincident module origins; review the layout")
            seen.add(signature)
            result.append({"id": f"{row['id']}_{i:03d}", "mesh": spec["modules"][row["module"]],
                           "position_cm": position, "yaw_deg": spec["yaw_deg"]+row["yaw_deg"], "scale": row["scale"]})
    return result


def assets(spec):
    if spec["kind"] == "effects":
        return {spec["animation"]: "AnimSequence", spec["preview_mesh"]: "SkeletalMesh",
                **{e["niagara"]: "NiagaraSystem" for e in spec["events"]}}
    if spec["kind"] == "architecture":
        return {path: "StaticMesh" for path in spec["modules"].values()}
    return {}


def snapshots(project, paths):
    # Reuse the saved-package/sidecar budgets from the existing Unreal inspector.
    project._inspection_files, project._inspection_bytes = {}, 0
    return {path: _file_state(project, path) for path in sorted(paths)}


def make_plan(specification, project_root):
    spec = recipe(specification)
    project = GameProject(project_root)
    refs = assets(spec)
    if any(p.split(".")[0].startswith(spec["destination"]+"/") for p in refs):
        raise ValueError("Source cannot be inside candidate destination")
    result = {"schema": "cryptonyan.director-plan/1", "recipe": spec, "operations": operations(spec),
              "project_root": str(project.root), "project_identity": project._project_identity(),
              "sources": snapshots(project, refs), "source_classes": refs,
              "engine_validated": False, "dependency_scope": "explicit_assets_and_package_sidecars"}
    result["identity"] = _hash(result)
    return result


def load_plan(path):
    value = read_json(path)
    exact(value, ("schema", "recipe", "operations", "project_root", "project_identity", "sources", "source_classes",
                  "engine_validated", "dependency_scope", "identity"))
    if make_plan(value["recipe"], value["project_root"]) != value:
        raise ValueError("Plan, project or source packages changed; rebuild the plan")
    return value


def import_contacts(trace, settings, specification, bindings):
    """Recompute the audit; never trust a detached events.json's approval/status fields."""
    audit = audit_trace(trace, settings)
    spec = copy.deepcopy(specification)
    if spec.get("kind") != "effects" or spec.get("events") != []:
        raise ValueError("Contact import requires an empty effects recipe")
    number(spec.get("duration_s"), .001, 600)
    if abs(spec["duration_s"]-audit["duration_s"]) > 1e-6:
        raise ValueError("Clip duration differs from trace")
    candidates = {e["id"]: e for e in audit["effect_candidates"]["events"]}
    for binding in rows(bindings, 64):
        exact(binding, ("contact_id", "socket", "niagara", "attached", "offset_m", "scale", "reviewed"))
        name(binding["contact_id"])
        event = candidates.get(binding["contact_id"])
        if event is None or event["contact_status"] != "within_threshold":
            raise ValueError("Contact is absent, sliding or not assessed")
        spec["events"].append({k: v for k, v in binding.items() if k != "contact_id"})
        spec["events"][-1].update(id="Contact_"+event["id"].replace("-", "_"), kind="contact", time_s=event["time_s"],
                                  origin={"audit_identity": audit["identity"], "contact_id": event["id"],
                                          "contact_status": event["contact_status"]})
    return recipe(spec)


def write_new(path, value, project_root):
    path = _outside(path, GameProject(project_root))
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+"\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan effects, camera cuts or existing-mesh architecture offline")
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--contact-bindings", type=Path)
    args = parser.parse_args(argv)
    spec = read_json(args.recipe)
    optional = (args.trace, args.settings, args.contact_bindings)
    if any(optional):
        if not all(optional):
            parser.error("Contact import requires --trace, --settings and --contact-bindings")
        spec = import_contacts(read_json(args.trace), read_json(args.settings), spec, read_json(args.contact_bindings))
    result = make_plan(spec, args.project)
    write_new(args.output, result, args.project)
    print(json.dumps({"identity": result["identity"], "kind": spec["kind"], "operations": len(result["operations"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
