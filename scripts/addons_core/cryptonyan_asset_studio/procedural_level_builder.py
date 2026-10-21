# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic runner layouts and conservative analytical static-route checks."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class RunnerSegment:
    identity: str
    lane: Literal[-1, 0, 1]
    branch: Literal["upper", "lower", "ground"]
    kind: Literal["run", "jump", "portal", "moving_platform", "three_way_choice"]
    next_segments: tuple[str, ...]
    length_m: float


@dataclass(frozen=True)
class MovementEnvelope:
    speed_m_s: float
    jump_speed_m_s: float
    gravity_m_s2: float
    lane_change_seconds: float
    capsule_radius_m: float


class ProceduralLevelBuilder(Protocol):
    def build(self, seed: int, segments: tuple[RunnerSegment, ...]) -> dict: ...
    def validate_survivability(self, level: dict, movement: MovementEnvelope) -> dict:
        """Must report reachable choices, landing windows, moving-platform phases and failure seeds."""
        ...


import copy
import csv
import hashlib
import io
import json
import math

from .schema import integer, keys

RECIPE_SCHEMA = "cryptonyan.runner-recipe/1"
LAYOUT_SCHEMA = "cryptonyan.runner-layout/1"
DEFAULT_RECIPE = {
    "schema": RECIPE_SCHEMA, "seed": 42, "rows": 8,
    "platform": {"length_m": 12.0, "width_m": 3.0, "thickness_m": 0.5},
    "gap_choices_m": [0.0, 1.0, 2.0], "side_lane_probability": 0.7,
    "movement": {"speed_m_s": 8.0, "jump_speed_m_s": 5.0, "gravity_m_s2": 9.81,
                 "lane_change_seconds": 0.35, "capsule_radius_m": 0.35,
                 "landing_margin_m": 0.15, "min_launch_window_seconds": 0.1,
                 "recovery_seconds": 0.1}}


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Runner parameter is outside its finite numeric bounds")
    return float(value)


def normalize_recipe(data):
    if isinstance(data, dict) and data.get("schema") == "cryptonyan.runner-recipe/2":
        from .runner_motion import normalize_extensions
        extensions = normalize_extensions(data)
        base = {k: v for k, v in data.items() if k not in extensions and k != "schema"}
        return {**normalize_recipe(base), "schema": data["schema"], **extensions}
    keys(data, DEFAULT_RECIPE)
    result = copy.deepcopy(DEFAULT_RECIPE)
    for field, value in data.items():
        if field in ("platform", "movement"):
            keys(value, result[field])
            result[field].update(value)
        else:
            result[field] = copy.deepcopy(value)
    if result["schema"] != RECIPE_SCHEMA:
        raise ValueError("Unsupported runner recipe")
    integer(result["seed"], "seed", 0, 2**32 - 1)
    integer(result["rows"], "rows", 2, 32)
    for field, bounds in {"length_m": (4, 50), "width_m": (1, 10), "thickness_m": (0.1, 3)}.items():
        result["platform"][field] = _number(result["platform"][field], *bounds)
    result["side_lane_probability"] = _number(result["side_lane_probability"], 0, 1)
    gaps = result["gap_choices_m"]
    if not isinstance(gaps, list) or not 1 <= len(gaps) <= 16:
        raise ValueError("Require 1 to 16 gap choices")
    result["gap_choices_m"] = [_number(v, 0, 20) for v in gaps]
    if len(set(result["gap_choices_m"])) != len(gaps):
        raise ValueError("Duplicate gap choices")
    for field, bounds in {"speed_m_s": (1, 40), "jump_speed_m_s": (1, 20), "gravity_m_s2": (1, 40),
                          "lane_change_seconds": (0.05, 3), "capsule_radius_m": (0.05, 1),
                          "landing_margin_m": (0.01, 1), "min_launch_window_seconds": (0.01, 1),
                          "recovery_seconds": (0, 2)}.items():
        result["movement"][field] = _number(result["movement"][field], *bounds)
    return result


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def build_layout(recipe):
    """SHA-256 draws avoid relying on random-library version-specific sequences."""
    config = normalize_recipe(recipe)
    counter = 0

    def draw():
        nonlocal counter
        value = int.from_bytes(hashlib.sha256(f"{config['seed']}:{counter}".encode("ascii")).digest()[:8], "big")
        counter += 1
        return value

    length, width = config["platform"]["length_m"], config["platform"]["width_m"]
    placements, x = [], 0.0
    for row in range(config["rows"]):
        if row:
            x += length + config["gap_choices_m"][draw() % len(config["gap_choices_m"])]
        for lane in (-1, 0, 1):
            # Ground centre lane is always present; movement checks can still reject gaps.
            present = lane == 0 or draw() / 2**64 < config["side_lane_probability"]
            if present:
                placements.append({"id": f"R{row:02d}_L{lane + 1}", "row": row, "lane": lane,
                                   "module": "RunnerPlatform", "origin_m": [x, lane * width, 0.0]})
    module = {"id": "RunnerPlatform", "size_m": [length, width, config["platform"]["thickness_m"]],
              "pivot": "entry_surface_center", "entry_m": [0.0, 0.0, 0.0], "exit_m": [length, 0.0, 0.0],
              "entry_normal": [-1, 0, 0], "exit_normal": [1, 0, 0]}
    schema = LAYOUT_SCHEMA
    if config["schema"] == "cryptonyan.runner-recipe/2":
        from .runner_motion import decorate_placements
        decorate_placements(placements, config)
        schema = "cryptonyan.runner-layout/2"
    layout = {"schema": schema, "recipe": config, "module": module, "placements": placements}
    return {**layout, "layout_id": _hash(layout)}


def validate_layout(layout):
    """Reject edits/tampering rather than silently analysing a different generated route."""
    if not isinstance(layout, dict) or _hash(layout) != _hash(build_layout(layout.get("recipe", {}))):
        raise ValueError("Layout differs from its canonical recipe; regenerate after editing the recipe")
    return layout


def _transition(source, target, earliest_x, recipe):
    movement, platform = recipe["movement"], recipe["platform"]
    radius = movement["capsule_radius_m"] + movement["landing_margin_m"]
    length, speed = platform["length_m"], movement["speed_m_s"]
    source_x, target_x = source["origin_m"][0], target["origin_m"][0]
    # Moving branches are available for review, never certified by the static solver.
    if "motion" in source or "motion" in target:
        return None
    dz = target["origin_m"][2] - source["origin_m"][2]
    lane_delta = abs(source["lane"] - target["lane"])
    if target["row"] != source["row"] + 1 or lane_delta > 1:
        return None
    if platform["width_m"] <= 2 * radius or length <= 2 * radius:
        return None
    if dz == 0 and lane_delta == 0 and math.isclose(source_x + length, target_x, abs_tol=1e-8, rel_tol=0):
        return {"kind": "run", "from": source["id"], "to": target["id"],
                "landing_x_m": target_x + radius, "travel_seconds": (target_x + radius - earliest_x) / speed}
    velocity, gravity = movement["jump_speed_m_s"], movement["gravity_m_s2"]
    discriminant = velocity**2 - 2 * gravity * dz
    if discriminant <= 0:
        return None
    # Preserve v1 floating-point evaluation for every existing flat recipe.
    flight = 2 * velocity / gravity if dz == 0 else (velocity + math.sqrt(discriminant)) / gravity
    if lane_delta * movement["lane_change_seconds"] > flight:
        return None
    distance = speed * flight
    low = max(source_x + radius, earliest_x + speed * movement["recovery_seconds"], target_x + radius - distance)
    high = min(source_x + length - radius, target_x + length - radius - distance)
    if dz > 0:
        # Clear the elevated leading face before the capsule overlaps it in X.
        ascending_time = (velocity - math.sqrt(discriminant)) / gravity
        high = min(high, target_x - radius - speed * ascending_time)
    window = (high - low) / speed
    if window + 1e-12 < movement["min_launch_window_seconds"]:
        return None
    return {"kind": "jump", "from": source["id"], "to": target["id"],
            "launch_interval_x_m": [low, high], "launch_window_seconds": window,
            "chosen_launch_x_m": low, "landing_x_m": low + distance,
            "flight_seconds": flight, "horizontal_distance_m": distance,
            "peak_height_m": movement["jump_speed_m_s"]**2 / (2 * movement["gravity_m_s2"])}


def analyze_layout(layout):
    """Propagate earliest landing positions, not just pairwise graph connectivity.

    On an obstacle-free static platform the runner can reach any later safe X, so the
    earliest arrival dominates later ones. Each jump adds a configurable ground recovery
    distance and a minimum launch window. This is a model, not a game simulation.
    """
    validate_layout(layout)
    recipe = layout["recipe"]
    movement = recipe["movement"]
    safe = movement["capsule_radius_m"] + movement["landing_margin_m"]
    start = next(p for p in layout["placements"] if p["row"] == 0 and p["lane"] == 0)
    dimensions_ok = recipe["platform"]["width_m"] > 2 * safe and recipe["platform"]["length_m"] > 2 * safe
    reached = {start["id"]: safe} if dimensions_ok else {}
    previous, accepted, rejected = {}, [], []
    rows = [[p for p in layout["placements"] if p["row"] == row] for row in range(recipe["rows"])]
    for sources, targets in zip(rows, rows[1:]):
        for source in sources:
            if source["id"] not in reached:
                continue
            for target in targets:
                edge = _transition(source, target, reached[source["id"]], recipe)
                if edge is None:
                    reason = "dynamic_branch_requires_engine_validation" if "motion" in source or "motion" in target else "outside_movement_envelope"
                    rejected.append({"from": source["id"], "to": target["id"], "reason": reason})
                    continue
                accepted.append(edge)
                if edge["landing_x_m"] < reached.get(target["id"], math.inf):
                    reached[target["id"]] = edge["landing_x_m"]
                    previous[target["id"]] = edge
    goals = sorted(p["id"] for p in rows[-1] if p["id"] in reached)
    witness = []
    if goals:
        cursor = goals[0]
        while cursor != start["id"]:
            edge = previous[cursor]
            witness.append(edge)
            cursor = edge["from"]
        witness.reverse()
    outgoing = {edge["from"] for edge in accepted}
    last_ids = {p["id"] for p in rows[-1]}
    result = {"schema": "cryptonyan.runner-analysis/1", "layout_id": layout["layout_id"],
            "model_passed": bool(goals), "engine_validated": False, "start": start["id"],
            "reachable_goals": goals, "witness": witness, "accepted_edges": accepted, "rejected_edges": rejected,
            "reachable_arrival_x_m": reached,
            "unreachable": [p["id"] for p in layout["placements"] if p["id"] not in reached],
            "dead_ends": sorted(set(reached) - outgoing - last_ids),
            "first_blocked_row": next((i for i, row in enumerate(rows) if not any(p["id"] in reached for p in row)), None),
            "failure_seeds": [] if goals else [recipe["seed"]],
            "assumptions": ["flat_static_platforms", "constant_forward_speed", "ballistic_same_height_jump",
                            "adjacent_lane_air_control", "no_obstacles_or_ceiling", "instant_jump_velocity",
                            "no_frame_quantization_or_input_latency_beyond_configured_windows"]}
    if recipe["schema"] == "cryptonyan.runner-recipe/2":
        result.update(schema="cryptonyan.runner-analysis/2", dynamics_validated=False,
                      dynamic_platforms=[p["id"] for p in layout["placements"] if "motion" in p])
        result["assumptions"][:3] = ["static_route_only_moving_branches_excluded", "constant_forward_speed",
                                     "descending_ballistic_landing_with_elevated_leading_face_clearance"]
    return result


def points_csv(layout):
    """Neutral CSV for explicit Unreal/PCG mapping, not a native PCGEx asset."""
    validate_layout(layout)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", "module", "row", "lane", "x_cm", "y_cm", "z_cm", "yaw_deg",
                     "scale_x", "scale_y", "scale_z", "exit_x_cm", "exit_y_cm", "exit_z_cm"])
    length = layout["module"]["size_m"][0]
    for item in layout["placements"]:
        x, y, z = item["origin_m"]
        writer.writerow([item["id"], item["module"], item["row"], item["lane"],
                         x * 100, -y * 100, z * 100, 0, 1, 1, 1, (x + length) * 100, -y * 100, z * 100])
    return output.getvalue()


def preview_svg(layout):
    """Portable top-down review; lines show a model witness, not simulated motion."""
    report = analyze_layout(layout)
    length, width, _ = layout["module"]["size_m"]
    scale, padding = 10, 24
    xmax = max(p["origin_m"][0] for p in layout["placements"]) + length
    size_x, size_y = xmax * scale + 2 * padding, width * 3 * scale + 2 * padding
    witness_ids = {edge[key] for edge in report["witness"] for key in ("from", "to")}
    placements = {p["id"]: p for p in layout["placements"]}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size_x:g} {size_y:g}" width="1200" role="img">',
             '<title>CryptoNyan runner: +X right; Blender lanes -1, 0, +1 top to bottom</title>',
             '<desc>Green: model witness; blue: reachable; orange: dead end; grey: unreachable. Lines are not motion simulation.</desc>',
             f'<rect width="{size_x:g}" height="{size_y:g}" fill="#111827"/>']
    if layout["schema"] == "cryptonyan.runner-layout/2":
        parts.insert(3, '<desc>Grey moving platforms are unverified dynamic branches, excluded from the static route model.</desc>')
    for item in layout["placements"]:
        identity = item["id"]
        color = "#22c55e" if identity in witness_ids else "#f59e0b" if identity in report["dead_ends"] else "#38bdf8" if identity in report["reachable_arrival_x_m"] else "#64748b"
        x, y = padding + item["origin_m"][0] * scale, padding + (item["lane"] + 1) * width * scale
        parts += [f'<rect x="{x:g}" y="{y:g}" width="{length * scale:g}" height="{width * scale:g}" fill="{color}" stroke="#111827"/>',
                  f'<text x="{x+2:g}" y="{y+8:g}" font-size="6" font-family="sans-serif" fill="#111827">{identity}</text>']
        if layout["schema"] == "cryptonyan.runner-layout/2":
            label = f'z={item["origin_m"][2]:g}m' + (' moving' if "motion" in item else '')
            parts.append(f'<text x="{x+2:g}" y="{y+17:g}" font-size="6" font-family="sans-serif" fill="#111827">{label}</text>')
    for edge in report["witness"]:
        source, target = placements[edge["from"]], placements[edge["to"]]
        x1 = padding + edge.get("chosen_launch_x_m", source["origin_m"][0] + length) * scale
        x2 = padding + edge["landing_x_m"] * scale
        y1, y2 = [padding + (p["lane"] + 1.5) * width * scale for p in (source, target)]
        parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="#a855f7" stroke-width="2"/>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def scan_seeds(recipe, *, first_seed=0, count=32):
    """Bounded regression sweep; retain failing seeds without running Blender."""
    integer(count, "count", 1, 256)
    integer(first_seed, "first_seed", 0, 2**32 - count)
    normalized = normalize_recipe(recipe)
    rows = []
    for seed in range(first_seed, first_seed + count):
        layout = build_layout({**normalized, "seed": seed})
        analysis = analyze_layout(layout)
        rows.append({"seed": seed, "layout_id": layout["layout_id"], "model_passed": analysis["model_passed"],
                     "first_blocked_row": analysis["first_blocked_row"], "dead_ends": analysis["dead_ends"]})
    return {"schema": "cryptonyan.runner-scan/1", "recipe": normalized, "first_seed": first_seed, "count": count,
            "engine_validated": False, "all_model_passed": all(row["model_passed"] for row in rows),
            "failure_seeds": [row["seed"] for row in rows if not row["model_passed"]], "results": rows}
