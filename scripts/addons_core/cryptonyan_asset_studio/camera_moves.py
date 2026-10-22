# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic look-at camera presets in Unreal metres, shared with Creative Director."""
import argparse
import copy
import json
import math
from pathlib import Path
import threading
import time

from .animation_doctor import exact, number, read_json
from .creative_director import identifier, integer, vector, rows, recipe as director_recipe
from .executors import ExecutionContext, run_process
from .image_workshop import identity
from .storage import digest, safe_path, write_json

SCHEMA = "cryptonyan.camera-moves/1"


def _pair(value, low, high):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Expected two endpoints")
    return [number(v, low, high) for v in value]


def _distance_to_segment(point, start, end):
    delta = [b-a for a,b in zip(start,end)]
    norm = sum(v*v for v in delta)
    t = 0 if norm == 0 else max(0,min(1,sum((p-a)*d for p,a,d in zip(point,start,delta))/norm))
    return math.sqrt(sum((p-a-t*d)**2 for p,a,d in zip(point,start,delta)))


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "id", "fps", "destination", "shots"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported camera move recipe")
    identifier(value["id"]); integer(value["fps"], 1, 120)
    ids = set()
    for shot in rows(value["shots"], 16):
        if not isinstance(shot, dict): raise ValueError("Expected camera shot object")
        common = ("id", "frames", "samples", "easing", "move")
        if shot.get("move") == "line":
            exact(shot, (*common, "start_m", "end_m", "target_m"))
            for key in ("start_m", "end_m", "target_m"): shot[key] = vector(shot[key], -1000, 1000)
            if _distance_to_segment(shot["target_m"][:2], shot["start_m"][:2], shot["end_m"][:2]) < .01:
                raise ValueError("Line look-at passes a vertical singularity; offset target or path")
            if math.dist(shot["start_m"], shot["end_m"]) < .001:
                raise ValueError("Line move requires distinct endpoints")
        elif shot.get("move") == "orbit":
            exact(shot, (*common, "center_m", "radius_m", "azimuth_deg", "height_m"))
            shot["center_m"] = vector(shot["center_m"], -1000, 1000)
            number(shot["radius_m"], .05, 500)
            _pair(shot["azimuth_deg"], -720, 720); _pair(shot["height_m"], -500, 500)
            if abs(shot["azimuth_deg"][1]-shot["azimuth_deg"][0]) > 720:
                raise ValueError("Orbit exceeds two turns")
        else:
            raise ValueError("Choose line (dolly/truck/crane) or orbit")
        key = identifier(shot["id"]).casefold()
        if key in ids: raise ValueError("Duplicate camera shot")
        ids.add(key)
        frames = integer(shot["frames"], 2, 36000)
        samples = integer(shot["samples"], 2, min(128,frames))
        if shot["easing"] not in ("linear", "smoothstep"):
            raise ValueError("Unsupported easing")
        # Smoothstep's maximum slope is 1.5. Avoid >45-degree intervals even after easing.
        if shot["move"] == "orbit":
            sweep = abs(shot["azimuth_deg"][1]-shot["azimuth_deg"][0])
            if sweep * (1.5 if shot["easing"] == "smoothstep" else 1)/(samples-1) > 40:
                raise ValueError("Increase samples for the orbit sweep")
        times = [round(i*(frames-1)/(samples-1)) for i in range(samples)]
        if len(set(times)) != len(times): raise ValueError("Duplicate sampled frame")
    # The established director validator owns destination, total duration and key envelopes.
    _cinematic(value)
    return value


def _pose(shot, alpha):
    t = alpha if shot["easing"] == "linear" else alpha*alpha*(3-2*alpha)
    if shot["move"] == "line":
        position = [(1-t)*a+t*b for a,b in zip(shot["start_m"],shot["end_m"])]
        target = shot["target_m"]
    else:
        azimuth = math.radians((1-t)*shot["azimuth_deg"][0]+t*shot["azimuth_deg"][1])
        height = (1-t)*shot["height_m"][0]+t*shot["height_m"][1]
        position = [shot["center_m"][0]+shot["radius_m"]*math.cos(azimuth),
                    shot["center_m"][1]+shot["radius_m"]*math.sin(azimuth), shot["center_m"][2]+height]
        target = shot["center_m"]
    dx,dy,dz = [b-a for a,b in zip(position,target)]
    if math.hypot(dx,dy) < .01: raise ValueError("Vertical look-at singularity")
    pitch = math.degrees(math.atan2(dz,math.hypot(dx,dy)))
    yaw = math.degrees(math.atan2(dy,dx))
    return {"position_m": position, "rotation_rpy_deg": [0,pitch,yaw], "target_m": target}


def _cinematic(spec):
    shots = []
    for shot in spec["shots"]:
        frames, samples = shot["frames"], shot["samples"]
        keys = []
        for i in range(samples):
            frame = round(i*(frames-1)/(samples-1))
            pose = _pose(shot,frame/(frames-1))
            keys.append({"frame": frame,"position_m": pose["position_m"],"rotation_rpy_deg":pose["rotation_rpy_deg"]})
        # Large angle jumps are ambiguous under the director's shortest-angle interpolation.
        for a,b in zip(keys,keys[1:]):
            if abs((b["rotation_rpy_deg"][2]-a["rotation_rpy_deg"][2]+180)%360-180) > 60:
                raise ValueError("Increase camera samples for look-at angular motion")
        shots.append({"id":shot["id"],"frames":frames,"keys":keys})
    return director_recipe({"kind":"cinematic","destination":spec["destination"],"fps":spec["fps"],"shots":shots})


def program(value):
    spec = specification(value)
    result = {"schema":"cryptonyan.camera-program/1","recipe":spec,"cinematic":_cinematic(spec),
              "coordinate_system":"Unreal_X_forward_Y_right_Z_up_metres",
              "interpolation":"linear_between_sampled_keys","lens_policy":"Blender_50mm_Unreal_actor_defaults_review_required",
              "engine_validated":False}
    result["identity"] = identity(result)
    return result


def prepare(value, output):
    result = program(value)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/"camera-program.json",result)
    write_json(output/"cinematic.json",result["cinematic"])
    return result


def load_program(folder):
    folder = Path(folder)
    path = safe_path(folder,"camera-program.json")
    if path.stat().st_size > 1024*1024: raise ValueError("Camera program exceeds 1 MiB")
    data = read_json(path)
    if not isinstance(data,dict) or "recipe" not in data or data != program(data["recipe"]):
        raise ValueError("Camera program changed")
    if read_json(safe_path(folder,"cinematic.json")) != data["cinematic"]:
        raise ValueError("Director recipe changed")
    return data


def preview(bundle, output, blender, timeout=120):
    from .reference_board import _separate
    number(timeout,1,300)
    bundle,output = Path(bundle).resolve(),Path(output).resolve()
    _separate(bundle,output)
    data = load_program(bundle)
    binary = Path(blender).resolve(strict=True)
    if not binary.is_file(): raise ValueError("Blender executable unavailable")
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/"camera-program.json",data)
    write_json(output/"cinematic.json",data["cinematic"])
    receipt={"schema":"cryptonyan.camera-preview/1","program_identity":data["identity"],"status":"running",
             "engine_validated":False,"framing_validated":False}
    try:
        ctx=ExecutionContext(output,output,(),threading.Event(),time.monotonic()+timeout)
        run_process([str(binary),'--background','--factory-startup','--disable-autoexec','--threads','1',
                     '--python-exit-code','1','--python',str(Path(__file__).with_name('camera_worker.py')),'--',str(output)],ctx)
        if load_program(output)!=data or load_program(bundle)!=data: raise ValueError("Camera inputs changed during preview")
        report=read_json(safe_path(output,'camera-check.json'))
        expected=sum(len(s['keys']) for s in data['cinematic']['shots'])
        exact(report, ("program_identity", "checked_keys", "look_at_error_max"))
        if report["program_identity"] != data["identity"] or report["checked_keys"] != expected:
            raise ValueError("Invalid camera preview report")
        number(report['look_at_error_max'],0,1e-5)
        receipt.update(status='preview_created_review_required',artifacts={name:{"sha256":digest(safe_path(output,name)),"bytes":safe_path(output,name).stat().st_size}
                       for name in ('camera-preview.blend','camera-check.json')})
        return receipt
    except BaseException:
        receipt['status']='failed'
        raise
    finally: write_json(output/'operation.json',receipt)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('recipe',type=Path);prep.add_argument('--output',type=Path,required=True)
    check=sub.add_parser('check');check.add_argument('bundle',type=Path)
    prev=sub.add_parser('preview');prev.add_argument('bundle',type=Path);prev.add_argument('--output',type=Path,required=True);prev.add_argument('--blender',type=Path,required=True)
    a=parser.parse_args(argv)
    value=prepare(read_json(a.recipe),a.output) if a.command=='prepare' else load_program(a.bundle) if a.command=='check' else preview(a.bundle,a.output,a.blender)
    print(json.dumps(value,indent=2))


if __name__=='__main__':main()
