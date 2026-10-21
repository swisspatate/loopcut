# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable cyclic lift contract. Epoch t=0 is Blender frame 1 at 30 fps."""
import hashlib
import math

from .schema import integer, keys

FPS = 30


def normalize_extensions(data):
    from .procedural_level_builder import _number
    heights = data.get("side_heights_m", [-0.6, 0.6])
    if not isinstance(heights, list) or len(heights) != 2:
        raise ValueError("Require heights for lanes -1 and +1")
    heights = [_number(v, -5, 5) for v in heights]
    motion = {"amplitude_m": 0.5, "period_frames": 120, "probability": 0.35}
    keys(data.get("motion", {}), motion)
    motion.update(data.get("motion", {}))
    motion["amplitude_m"] = _number(motion["amplitude_m"], 0.05, 3)
    motion["probability"] = _number(motion["probability"], 0, 1)
    integer(motion["period_frames"], "period_frames", 24, 600)
    if motion["period_frames"] % 4:
        raise ValueError("Motion period must be divisible by four")
    return {"side_heights_m": heights, "motion": motion}


def decorate_placements(placements, recipe):
    """Keep entry, exit and the centre route static; optional side routes vary."""
    for item in placements:
        if item["lane"] == 0 or item["row"] in (0, recipe["rows"] - 1):
            continue
        item["origin_m"][2] = recipe["side_heights_m"][0 if item["lane"] == -1 else 1]
        draw = hashlib.sha256(f'{recipe["seed"]}:motion:{item["id"]}'.encode("ascii")).digest()
        if int.from_bytes(draw[:8], "big") / 2**64 < recipe["motion"]["probability"]:
            item["motion"] = {"kind": "triangle_lift", "axis": "z", "fps": FPS,
                              "amplitude_m": recipe["motion"]["amplitude_m"],
                              "period_frames": recipe["motion"]["period_frames"],
                              "phase_frames": int.from_bytes(draw[8:16], "big") % recipe["motion"]["period_frames"]}


def position_at(placement, seconds):
    """Unbounded repeating piecewise-linear motion; no simulation or frame state."""
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or abs(seconds) > 1e9:
        raise ValueError("Invalid motion time")
    position = list(placement["origin_m"])
    motion = placement.get("motion")
    if motion:
        phase = ((seconds * motion["fps"] + motion["phase_frames"]) % motion["period_frames"]) / motion["period_frames"]
        wave = 1 - 4 * abs(phase - 0.25) if phase < 0.75 else 4 * phase - 4
        position[2] += motion["amplitude_m"] * wave
    return position


def motion_tracks(layout):
    """Explicit UE coordinates; a contract for a Blueprint adapter, not an importer."""
    from .procedural_level_builder import validate_layout
    validate_layout(layout)
    tracks = []
    for item in layout["placements"]:
        if "motion" not in item:
            continue
        motion = item["motion"]
        x, y, z = item["origin_m"]
        tracks.append({"id": item["id"], "origin_unreal_cm": [100*x, -100*y, 100*z],
                       "kind": motion["kind"], "axis": "z", "amplitude_cm": 100 * motion["amplitude_m"],
                       "period_seconds": motion["period_frames"] / FPS,
                       "phase_seconds": motion["phase_frames"] / FPS})
    return {"schema": "cryptonyan.motion-tracks/1", "layout_id": layout["layout_id"],
            "epoch": "level_start_seconds_zero_blender_frame_one", "fps": FPS,
            "wave": "triangle: phase 0=0, 0.25=+1, 0.5=0, 0.75=-1, 1=0",
            "engine_validated": False, "tracks": tracks}


def animate_preview(obj, placement, scene):
    """Bake two exact cycles with linear keys; no script drivers or auto-execution."""
    from loopcut.scene_context import _fcurves
    motion = placement.get("motion")
    if not motion:
        return
    period = motion["period_frames"]
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, 2 * period + 1
    for offset in range(2 * period + 1):
        if offset in (0, 2 * period) or (offset + motion["phase_frames"]) % (period // 4) == 0:
            obj.location = position_at(placement, offset / FPS)
            obj.keyframe_insert(data_path="location", index=2, frame=offset + 1)
    # Reuse Loopcut's legacy/slotted-action compatibility helper. API insertion does
    # not reliably honor the UI's interpolation preference, so set keys explicitly.
    curves = _fcurves(obj)
    if len(curves) != 1 or curves[0].data_path != "location" or curves[0].array_index != 2:
        raise ValueError("Unexpected lift animation channels")
    for key in curves[0].keyframe_points:
        key.interpolation = "LINEAR"
    curves[0].update()
    obj["cryptonyan_motion"] = "triangle_lift; preview has two cycles; frame 1 = t0"
