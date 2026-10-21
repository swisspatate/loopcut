# SPDX-License-Identifier: GPL-3.0-or-later
"""Axis-aligned cuboid QA. Swept boxes flag potential overlap, not collisions."""
import math
import re

from .procedural_level_builder import _hash, _number
from .world_assembly import normalize_world

EPSILON_CM = .001
MAX_FINDINGS = 256


def vector(value, low=-1e8, high=1e8):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("Expected three finite coordinates")
    return [_number(v, low, high) for v in value]


def validate_plan(plan):
    """Validate portable plan structure; provenance is checked against kits by build."""
    expected = {"schema", "recipe", "modules", "zones", "connections", "actors", "world_id",
                "static_centre_route_passed", "engine_validated", "dynamics_validated",
                "length_cm", "decorations_have_collision"}
    if (not isinstance(plan, dict) or set(plan) != expected or
            plan["schema"] != "cryptonyan.world-plan/1" or
            plan["world_id"] != _hash({k: v for k, v in plan.items() if k != "world_id"})):
        raise ValueError("Invalid or changed world plan")
    recipe = normalize_world(plan["recipe"])
    if any(plan[k] is not False for k in ("engine_validated", "dynamics_validated", "decorations_have_collision")):
        raise ValueError("Unsupported world validation claims")
    if plan["static_centre_route_passed"] is not True:
        raise ValueError("World requires a static centre route")
    _number(plan["length_cm"], 1, 1e8)
    modules = plan["modules"]
    if not isinstance(modules, dict) or not 1 <= len(modules) <= 8:
        raise ValueError("Invalid world modules")
    for key, module in modules.items():
        if not re.fullmatch(r"M[0-9]{2}", key):
            raise ValueError("Invalid module identifier")
        bounds = module["import"]["asset"]["bounds_blender_m"]
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("Invalid module bounds")
        lo, hi = (vector(v, -100, 100) for v in bounds)
        # Only the existing runner cuboid contract is supported, not arbitrary meshes.
        if (any(a >= b for a, b in zip(lo, hi)) or abs(lo[0]) > 1e-5 or abs(hi[2]) > 1e-5 or
                abs(lo[1]+hi[1]) > 1e-5 or module["import"]["asset"]["triangles"] != 12):
            raise ValueError("Unsupported runner module geometry")
    zones = plan["zones"]
    if not isinstance(zones, list) or len(zones) != len(recipe["zones"]):
        raise ValueError("Invalid zones")
    for index, zone in enumerate(zones):
        if (set(zone) != {"id", "module", "entry_cm", "exit_cm", "biome"} or
                zone["id"] != f"Z{index:02d}" or zone["module"] not in modules or
                zone["biome"] != recipe["zones"][index]["biome"] or
                modules[zone["module"]]["kit"] != recipe["zones"][index]["kit"]):
            raise ValueError("Invalid zone binding")
        vector(zone["entry_cm"])
        vector(zone["exit_cm"])
    actors = plan["actors"]
    if not isinstance(actors, list) or not 1 <= len(actors) <= 512:
        raise ValueError("World actor budget exceeded")
    seen = set()
    for item in actors:
        if set(item) != {"id", "module", "biome", "kind", "origin_cm", "scale", "collision",
                         "amplitude_cm", "period_seconds", "phase_seconds"}:
            raise ValueError("Invalid actor fields")
        match = re.fullmatch(r"Z([0-9]{2})_(R[0-9]{2}_L[012]|D[0-9]{2})", item["id"])
        if not match or int(match[1]) >= len(zones) or item["id"] in seen:
            raise ValueError("Invalid or duplicate actor identifier")
        seen.add(item["id"])
        zone = zones[int(match[1])]
        if item["module"] != zone["module"] or item["biome"] != zone["biome"]:
            raise ValueError("Actor zone binding differs")
        kind = "decoration" if match[2].startswith("D") else "platform"
        if item["kind"] != kind or item["collision"] is not (kind == "platform"):
            raise ValueError("Invalid actor kind or collision contract")
        vector(item["origin_cm"])
        vector(item["scale"], .0001, 100)
        amplitude = _number(item["amplitude_cm"], 0, 300)
        period = _number(item["period_seconds"], .8, 20)
        phase = _number(item["phase_seconds"], 0, period)
        if phase >= period or kind == "decoration" and amplitude:
            raise ValueError("Invalid motion phase or decoration motion")
        if amplitude and (not math.isclose(period*30, round(period*30), abs_tol=1e-7) or
                          round(period*30) % 4 or not math.isclose(phase*30, round(phase*30), abs_tol=1e-7)):
            raise ValueError("Motion must use the runner frame lattice")
    if not isinstance(plan["connections"], list) or len(plan["connections"]) > 7:
        raise ValueError("Invalid connection budget")
    return plan


def actor_bounds(plan, item, *, swept=False):
    lo, hi = plan["modules"][item["module"]]["import"]["asset"]["bounds_blender_m"]
    local = ([lo[0]*100, -hi[1]*100, lo[2]*100], [hi[0]*100, -lo[1]*100, hi[2]*100])
    result = [[p+s*v for p, s, v in zip(item["origin_cm"], item["scale"], corner)] for corner in local]
    if swept:
        result[0][2] -= item["amplitude_cm"]
        result[1][2] += item["amplitude_cm"]
    return result


def analyze_world(plan):
    validate_plan(plan)
    findings, counts = [], {"error": 0, "warning": 0}

    def record(code, severity, **evidence):
        counts[severity] += 1
        if len(findings) < MAX_FINDINGS:
            findings.append({"code": code, "severity": severity, **evidence})

    bounds = [actor_bounds(plan, a, swept=True) for a in plan["actors"]]
    for i, a in enumerate(plan["actors"]):
        for j in range(i+1, len(bounds)):
            b = plan["actors"][j]
            penetration = [min(bounds[i][1][k], bounds[j][1][k])-max(bounds[i][0][k], bounds[j][0][k]) for k in range(3)]
            if min(penetration) <= EPSILON_CM:
                continue
            visual = not (a["collision"] and b["collision"])
            moving = bool(a["amplitude_cm"] or b["amplitude_cm"])
            code = "visual_overlap" if visual else "potential_motion_overlap" if moving else "static_overlap"
            record(code, "warning" if visual or moving else "error", actors=[a["id"], b["id"]],
                   swept=moving, penetration_cm=penetration)

    def close(a, b):
        return len(a) == len(b) and all(abs(x-y) <= EPSILON_CM for x, y in zip(a, b))

    if len(plan["connections"]) != len(plan["zones"])-1:
        record("connection_count", "error")
    for index, (left, right) in enumerate(zip(plan["zones"], plan["zones"][1:])):
        connection = plan["connections"][index] if index < len(plan["connections"]) else {}
        width = 200 * plan["modules"][left["module"]]["import"]["asset"]["bounds_blender_m"][1][1]
        right_width = 200 * plan["modules"][right["module"]]["import"]["asset"]["bounds_blender_m"][1][1]
        expected = {"from_zone": left["id"], "to_zone": right["id"], "position_cm": right["entry_cm"],
                    "width_cm": width, "kind": "flush_ground_centre", "opposed_normals": [[1, 0, 0], [-1, 0, 0]]}
        # Bounds exported through Blender may carry float32 rounding.
        correct = set(connection) == set(expected)
        if correct:
            correct = (all(connection[k] == expected[k] for k in expected if k not in ("width_cm", "position_cm")) and
                       close(vector(connection["position_cm"]), right["entry_cm"]) and
                       abs(_number(connection["width_cm"], .001, 1e6)-width) <= EPSILON_CM)
        if not correct or abs(width-right_width) > EPSILON_CM or not close(left["exit_cm"], right["entry_cm"]):
            record("connection_mismatch", "error", zones=[left["id"], right["id"]])
    for zone in plan["zones"]:
        centre = [a for a in plan["actors"] if a["id"].startswith(zone["id"]+"_R") and a["id"].endswith("_L1")]
        centre.sort(key=lambda a: a["id"])
        if not centre:
            record("missing_centre_route", "error", zone=zone["id"])
            continue
        for item, socket, side in ((centre[0], zone["entry_cm"], 0), (centre[-1], zone["exit_cm"], 1)):
            lo, hi = actor_bounds(plan, item)
            point = [(lo, hi)[side][0], (lo[1]+hi[1])/2, hi[2]]
            expected_width = 200 * plan["modules"][zone["module"]]["import"]["asset"]["bounds_blender_m"][1][1]
            if (item["amplitude_cm"] or not close(point, socket) or
                    abs(hi[1]-lo[1]-expected_width) > EPSILON_CM or
                    abs(socket[1]) > EPSILON_CM or abs(socket[2]) > EPSILON_CM):
                record("socket_geometry_mismatch", "error", actor=item["id"], expected_cm=socket, actual_cm=point)
    if (not close(plan["zones"][0]["entry_cm"], [0, 0, 0]) or
            not close(plan["zones"][-1]["exit_cm"], [plan["length_cm"], 0, 0])):
        record("world_extent_mismatch", "error")
    return {"schema": "cryptonyan.world-geometry/1", "world_id": plan["world_id"],
            "geometry_passed": counts["error"] == 0, "counts": counts, "findings": findings,
            "findings_truncated": sum(counts.values()) > len(findings), "epsilon_cm": EPSILON_CM,
            "engine_validated": False, "dynamics_validated": False, "controller_validated": False}
