# SPDX-License-Identifier: GPL-3.0-or-later
"""Fit an already modelled garment near a closed body proxy, on an isolated copy."""
import argparse
import json
from pathlib import Path
import shutil
import threading
import time

from .animation_doctor import exact, name, number, parse_capture, read_json
from .creative_director import integer
from .executors import ExecutionContext, run_process
from .storage import digest, write_json


def specification(value):
    exact(value, ("body", "garment", "clearance_m", "max_distance_m", "max_influences", "capture", "uv_size"))
    name(value["body"]); name(value["garment"])
    capture = parse_capture(value["capture"])
    if len({value["body"], value["garment"], capture["armature"]}) != 3:
        raise ValueError("Body, garment and armature must be distinct")
    number(value["clearance_m"], .0001, .05); number(value["max_distance_m"], .001, .5)
    if value["clearance_m"] >= value["max_distance_m"]:
        raise ValueError("Clearance must be smaller than the fit distance budget")
    integer(value["max_influences"], 1, 8); integer(value["uv_size"], 32, 512)
    if (capture["end_frame"]-capture["start_frame"])//capture["step_frames"]+1 > 120:
        raise ValueError("Garment preview allows at most 120 sampled frames")
    return {**value, "capture": capture}


def run(source, spec, output, blender, timeout=120):
    spec = specification(spec); number(timeout, 1, 600)
    source, output, binary = Path(source).resolve(), Path(output).resolve(), Path(blender).resolve()
    if source.suffix.lower() != ".blend" or not 1 <= source.stat().st_size <= 512*1024*1024 or not binary.is_file():
        raise ValueError("Require a bounded .blend and Blender executable")
    before = digest(source)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copyfile(source, output / "source.blend")
    if digest(output / "source.blend") != before:
        raise ValueError("Source changed during copy")
    write_json(output / "request.json", spec)
    receipt = {"status": "running", "candidate": None, "source_sha256": before, "visual_quality_validated": False}
    try:
        context = ExecutionContext(output, output, ("source.blend",), threading.Event(), time.monotonic()+timeout)
        run_process([str(binary), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                     "--python-exit-code", "1", "--python", str(Path(__file__).with_name("garment_worker.py")),
                     "--", str(output / "request.json")], context)
        if digest(source) != before or digest(output / "source.blend") != before:
            raise ValueError("Source changed during fitting")
        report = read_json(output / "garment.json")
        receipt.update(status="candidate_created_review_required", report=report,
                       candidate={"file": "candidate.blend", "sha256": digest(output / "candidate.blend")})
        return receipt
    except Exception as error:
        receipt.update(status="failed", error=type(error).__name__)
        raise
    finally:
        write_json(output / "result.json", receipt)


def main(argv=None):
    p = argparse.ArgumentParser(description="Fit and weight a garment copy, export UV masks and inspect sampled poses")
    p.add_argument("source", type=Path); p.add_argument("specification", type=Path)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--blender", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args(argv)
    result = run(args.source, read_json(args.specification), args.output, args.blender, args.timeout)
    print(json.dumps(result)); return 1 if result["report"]["penetrating_samples"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
