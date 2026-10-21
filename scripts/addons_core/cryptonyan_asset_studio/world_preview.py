# SPDX-License-Identifier: GPL-3.0-or-later
"""Build an isolated, source-preserving Blender preview of connected runner kits."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

from .executors import BlenderExecutor, ExecutionContext, run_process
from .runner_kit import read_json
from .storage import digest, safe_path, write_json
from .world_assembly import plan_world
from .world_geometry import analyze_world
from .world_materials import plan_materials, validate_appearance


def preview_placement(actor):
    x, y, z = actor["origin_cm"]
    result = {"origin_m": [x/100, -y/100, z/100]}
    if actor["amplitude_cm"]:
        result["motion"] = {"kind": "triangle_lift", "axis": "z", "fps": 30,
                            "amplitude_m": actor["amplitude_cm"]/100,
                            "period_frames": round(actor["period_seconds"]*30),
                            "phase_frames": round(actor["phase_seconds"]*30)}
    return result


def preview_window(plan):
    periods = [round(a["period_seconds"]*30) for a in plan["actors"] if a["amplitude_cm"]]
    duration = 2 * max(periods, default=120)
    return {"fps": 30, "frame_start": 1, "frame_end": duration+1,
            "whole_world_loop": all(duration % p == 0 for p in periods)}


def validate_preview(root, *, source_root=None):
    root = Path(root).resolve(strict=True)
    plan = read_json(safe_path(root, "world-plan.json"))
    qa = analyze_world(plan)
    if not qa["geometry_passed"] or read_json(safe_path(root, "geometry.json")) != qa:
        raise ValueError("World geometry report differs or failed")
    catalog = read_json(safe_path(root, "preview.json"))
    fields = {"schema", "world_id", "window", "files", "sources", "engine_validated"}
    files = {"world-plan.json", "geometry.json", "world-preview.blend"}
    appearance = None
    if catalog.get("schema") == "cryptonyan.world-preview/2":
        fields.add("appearance_id")
        appearance = validate_appearance(read_json(safe_path(root, "appearance.json")), safe_path(root, "textures"), plan)
        files.update("textures/"+p for p in appearance["inputs"])
        files.add("appearance.json")
        if catalog.get("appearance_id") != appearance["appearance_id"]:
            raise ValueError("Preview appearance identity differs")
    if (set(catalog) != fields or
            catalog["schema"] not in ("cryptonyan.world-preview/1", "cryptonyan.world-preview/2") or catalog["world_id"] != plan["world_id"] or
            catalog["window"] != preview_window(plan) or catalog["engine_validated"] is not False or
            set(catalog["files"]) != files or
            set(catalog["sources"]) != set(plan["modules"])):
        raise ValueError("Invalid preview catalog")
    for key, module in plan["modules"].items():
        # Portable receipts record source hashes; build revalidates their kit catalogs.
        source = catalog["sources"][key]
        if (set(source) != {"kit", "catalog_sha256", "sha256"} or source["kit"] != module["kit"] or
                source["catalog_sha256"] != module["catalog_sha256"] or
                not isinstance(source["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
            raise ValueError("Preview source binding differs")
    for name, spec in catalog["files"].items():
        path = safe_path(root, name)
        if set(spec) != {"bytes", "sha256"} or path.stat().st_size != spec["bytes"] or digest(path) != spec["sha256"]:
            raise ValueError("Preview artifact integrity failed")
    if source_root is not None:
        source_root = Path(source_root).resolve(strict=True)
        if plan_world(plan["recipe"], source_root) != plan:
            raise ValueError("Preview no longer matches source kits")
        for source in catalog["sources"].values():
            if digest(safe_path(source_root, source["kit"]+"/modules.blend")) != source["sha256"]:
                raise ValueError("Preview source hash differs")
        if appearance is not None:
            validate_appearance(appearance, source_root, plan)
    return catalog


def build_preview(recipe, source_root, destination, *, blender=None, timeout_seconds=120, materials=None):
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid preview timeout")
    root = Path(source_root).resolve(strict=True)
    destination = Path(destination).resolve()
    # No artifacts are written into input kits, even when only requesting QA.
    if destination == root or root in destination.parents:
        raise ValueError("Preview destination must be outside the source root")
    plan = plan_world(recipe, root)
    qa = analyze_world(plan)
    appearance = plan_materials(materials, root, plan) if materials is not None else None
    executor = BlenderExecutor(blender) if blender is not None and qa["geometry_passed"] else None
    destination.mkdir(exist_ok=False)
    write_json(destination / "world-plan.json", plan)
    write_json(destination / "geometry.json", qa)
    if appearance is not None:
        write_json(destination / "appearance.json", appearance)
    result = {"world_id": plan["world_id"], "geometry_passed": qa["geometry_passed"],
              "built": False, "engine_validated": False, "directory": str(destination)}
    if appearance is not None:
        result["appearance_id"] = appearance["appearance_id"]
    if executor is None:
        return result
    if appearance is not None:
        textures = destination / "textures"
        textures.mkdir()
        for relative, spec in appearance["inputs"].items():
            target = safe_path(textures, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(root, relative), target)
            if target.stat().st_size != spec["bytes"] or digest(target) != spec["sha256"]:
                raise ValueError("Texture changed during snapshot")
        validate_appearance(appearance, textures, plan)
        validate_appearance(appearance, root, plan)
    sources = {}
    with tempfile.TemporaryDirectory(prefix=".world-", dir=destination) as temp:
        runtime = Path(temp).resolve()
        snapshots, total = {}, 0
        for key, module in plan["modules"].items():
            source = safe_path(root, module["kit"] + "/modules.blend")
            total += source.stat().st_size
            if total > 512*1024*1024:
                raise ValueError("World snapshot budget exceeded")
            before = digest(source)
            snapshot = runtime / (key + ".blend")
            shutil.copyfile(source, snapshot)
            if snapshot.stat().st_size > 512*1024*1024 or digest(snapshot) != before or digest(source) != before:
                raise ValueError("Source changed during snapshot")
            sources[key] = {"kit": module["kit"], "catalog_sha256": module["catalog_sha256"], "sha256": before}
            snapshots[key] = {"file": snapshot.name, "sha256": before}
        if plan_world(recipe, root) != plan:
            raise ValueError("World changed during snapshot")
        request = runtime / "request.json"
        write_json(request, {"bundle": str(destination), "plan_sha256": digest(destination / "world-plan.json"),
                             "snapshots": snapshots,
                             "appearance_sha256": digest(destination / "appearance.json") if appearance is not None else None})
        context = ExecutionContext(runtime, runtime, (), threading.Event(), time.monotonic()+timeout_seconds)
        command = executor.command(request)
        command[command.index("--python")+1] = str(Path(__file__).with_name("world_worker.py"))
        run_process(command, context)
    if plan_world(recipe, root) != plan or read_json(destination / "world-plan.json") != plan or read_json(destination / "geometry.json") != qa:
        raise ValueError("World changed during preview build")
    files = ["world-plan.json", "geometry.json", "world-preview.blend"]
    if appearance is not None:
        if read_json(destination / "appearance.json") != appearance:
            raise ValueError("Appearance changed during preview build")
        validate_appearance(appearance, root, plan)
        validate_appearance(appearance, destination / "textures", plan)
        files += ["appearance.json"] + ["textures/"+p for p in appearance["inputs"]]
    catalog = {"schema": "cryptonyan.world-preview/1", "world_id": plan["world_id"],
               "window": preview_window(plan), "engine_validated": False, "sources": sources,
               "files": {name: {"bytes": safe_path(destination, name).stat().st_size,
                                  "sha256": digest(safe_path(destination, name))} for name in files}}
    if appearance is not None:
        catalog.update(schema="cryptonyan.world-preview/2", appearance_id=appearance["appearance_id"])
    write_json(destination / "preview.json", catalog)
    try:
        validate_preview(destination, source_root=root)
    except Exception:
        # This new catalog belongs to this attempt; failed final validation must
        # not leave a success receipt, even if sources changed at the last moment.
        (destination / "preview.json").unlink()
        raise
    return {**result, "built": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Connected-world geometry checks and Blender preview")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = commands.add_parser(name)
        command.add_argument("recipe", type=Path)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--destination", type=Path, required=True)
        command.add_argument("--materials", type=Path, help="Explicit biome/module material assignments")
        if name == "build":
            command.add_argument("--blender", type=Path, required=True)
            command.add_argument("--timeout", type=float, default=120)
    check = commands.add_parser("check")
    check.add_argument("bundle", type=Path)
    check.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    if args.command == "check":
        result = validate_preview(args.bundle, source_root=args.source)
    else:
        result = build_preview(read_json(args.recipe), args.source, args.destination,
                               blender=getattr(args, "blender", None), timeout_seconds=getattr(args, "timeout", 120),
                               materials=read_json(args.materials) if args.materials is not None else None)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if args.command == "check" or result["geometry_passed"] else 1


if __name__ == "__main__":
    from .executors import WorkerFailure, BudgetExpired, WORKER_MESSAGES
    try:
        raise SystemExit(main())
    except WorkerFailure as error:
        print(WORKER_MESSAGES[error.code])
        raise SystemExit(2)
    except BudgetExpired:
        print("World preview timed out; inspect the partial output and choose a new destination")
        raise SystemExit(2)
    except (ValueError, OSError, KeyError, TypeError):
        print("World preview failed; check inputs, executable and new destination")
        raise SystemExit(2)
