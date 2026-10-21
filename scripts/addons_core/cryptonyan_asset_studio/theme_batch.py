# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded asset x theme jobs using existing Material Doctor and static publisher."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

from .executors import BlenderExecutor, ExecutionContext, WorkerFailure, run_process
from .materials import load_material
from .procedural_level_builder import _hash
from .publication import load_package
from .runner_kit import read_json
from .storage import digest, safe_path, write_json

RECIPE_SCHEMA = "cryptonyan.theme-recipe/1"


def _entries(value, limit):
    if not isinstance(value, list) or not 1 <= len(value) <= limit:
        raise ValueError("Invalid batch entry count")
    identities = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", entry["id"]):
            raise ValueError("Use lowercase portable asset/theme identifiers")
        identities.append(entry["id"])
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate batch identifier")


def plan_batch(recipe, source_root):
    """Resolve explicit per-asset materials. Shared bundles are allowed; inference isn't."""
    if not isinstance(recipe, dict) or set(recipe) != {"schema", "assets", "themes"} or recipe["schema"] != RECIPE_SCHEMA:
        raise ValueError("Unsupported theme recipe")
    _entries(recipe["assets"], 16)
    _entries(recipe["themes"], 8)
    if len(recipe["assets"]) * len(recipe["themes"]) > 32:
        raise ValueError("Maximum 32 asset/theme outputs")
    root = Path(source_root).resolve(strict=True)
    inputs, sources, materials = {}, {}, {}

    def bind(relative):
        path = safe_path(root, relative)
        if relative not in inputs:
            size = path.stat().st_size
            if not path.is_file() or size > 512 * 1024 * 1024 or sum(v["bytes"] for v in inputs.values()) + size > 512 * 1024 * 1024:
                raise ValueError("Batch inputs exceed 512 MiB budget")
            inputs[relative] = {"sha256": digest(path), "bytes": size}
        return path

    for asset in recipe["assets"]:
        if (set(asset) != {"id", "source", "object"} or not isinstance(asset["object"], str) or
                not 1 <= len(asset["object"]) <= 255 or "\x00" in asset["object"]):
            raise ValueError("Require explicit asset source and object")
        path = bind(asset["source"])
        if path.suffix.lower() != ".blend":
            raise ValueError("Require .blend asset sources")
        sources[asset["id"]] = asset
    jobs = []
    for theme in recipe["themes"]:
        if set(theme) != {"id", "materials"} or not isinstance(theme["materials"], dict) or set(theme["materials"]) != set(sources):
            raise ValueError("Every theme must explicitly map every asset to a material bundle")
        for asset_id, asset in sources.items():
            relative = theme["materials"][asset_id]
            manifest_path = bind(relative)
            if relative not in materials:
                material = load_material(manifest_path)
                for channel in material["channels"].values():
                    image = (Path(relative).parent / channel["file"]).as_posix()
                    bind(image)
                    if inputs[image]["sha256"] != channel["sha256"]:
                        raise ValueError("Material changed during planning")
                if digest(manifest_path) != inputs[relative]["sha256"]:
                    raise ValueError("Material changed during planning")
                materials[relative] = material
            jobs.append({"id": f"J{len(jobs):03d}", "asset": asset_id, "theme": theme["id"],
                         "source": asset["source"], "object": asset["object"], "material": relative})
    plan = {"schema": "cryptonyan.theme-plan/1", "recipe": copy.deepcopy(recipe),
            "inputs": inputs, "materials": materials, "jobs": jobs}
    return {**plan, "plan_id": _hash(plan)}


def _job_files(folder, job):
    package = load_package(safe_path(folder, "manifest.json"))
    prepared = safe_path(folder, "asset.blend")
    if package["source"] != {"object": job["object"], "sha256": digest(prepared)}:
        raise ValueError("Publication is not bound to its prepared asset")
    return {name: {"sha256": digest(safe_path(folder, name)), "bytes": safe_path(folder, name).stat().st_size}
            for name in ("asset.blend", "manifest.json", "quality.json", package["asset"]["file"])}


def build_batch(recipe, source_root, destination, *, blender, timeout_seconds=600):
    """Snapshot once, run serial isolated workers, stop on failure and retain receipts."""
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid batch deadline")
    plan = plan_batch(recipe, source_root)
    executor = BlenderExecutor(blender)
    root = Path(destination)
    root.mkdir(exist_ok=False)
    root = root.resolve()
    write_json(root / "plan.json", plan)
    receipt = {"schema": "cryptonyan.theme-batch/1", "plan_id": plan["plan_id"], "passed": False,
               "engine_validated": False, "jobs": [{"id": j["id"], "status": "pending"} for j in plan["jobs"]]}
    write_json(root / "batch.json", receipt)
    deadline = time.monotonic() + timeout_seconds
    try:
        with tempfile.TemporaryDirectory(prefix=".themes-", dir=root) as temp:
            runtime = Path(temp).resolve()
            snapshots = runtime / "inputs"
            snapshots.mkdir()
            for relative, binding in plan["inputs"].items():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Batch snapshot deadline exceeded")
                source = safe_path(source_root, relative)
                target = safe_path(snapshots, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if target.stat().st_size != binding["bytes"] or digest(target) != binding["sha256"]:
                    raise ValueError("Batch input changed during snapshot")
            for job, status in zip(plan["jobs"], receipt["jobs"]):
                status["status"] = "running"
                write_json(root / "batch.json", receipt)
                folder = safe_path(root, job["id"])
                folder.mkdir()
                worker = runtime / job["id"]
                worker.mkdir()
                request = worker / "request.json"
                write_json(request, {"job": job, "snapshots": str(snapshots), "output": str(folder),
                                     "source_sha256": plan["inputs"][job["source"]]["sha256"],
                                     "material_sha256": plan["inputs"][job["material"]]["sha256"]})
                context = ExecutionContext(worker, worker, (), threading.Event(), deadline)
                command = executor.command(request)
                command[command.index("--python") + 1] = str(Path(__file__).with_name("theme_worker.py"))
                run_process(command, context)
                status.update(status="passed", files=_job_files(folder, job))
                write_json(root / "batch.json", receipt)
            if plan_batch(recipe, source_root) != plan:
                raise ValueError("Original batch inputs changed during build")
        receipt["passed"] = True
    except Exception as error:
        for status in receipt["jobs"]:
            if status["status"] == "running":
                status["status"] = "failed"
        receipt["error"] = error.code if isinstance(error, WorkerFailure) else type(error).__name__
        raise
    finally:
        write_json(root / "batch.json", receipt)
    return validate_batch(root)


def validate_batch(root):
    root = Path(root).resolve()
    plan = read_json(safe_path(root, "plan.json"))
    identity = plan.pop("plan_id")
    if identity != _hash(plan) or plan["schema"] != "cryptonyan.theme-plan/1":
        raise ValueError("Batch plan integrity failed")
    receipt = read_json(safe_path(root, "batch.json"))
    if (set(receipt) != {"schema", "plan_id", "passed", "engine_validated", "jobs"} or
            receipt["schema"] != "cryptonyan.theme-batch/1" or receipt["plan_id"] != identity or
            receipt["passed"] is not True or receipt["engine_validated"] is not False or
            not isinstance(receipt["jobs"], list) or len(receipt["jobs"]) != len(plan["jobs"]) or
            not 1 <= len(plan["jobs"]) <= 32):
        raise ValueError("Batch did not complete successfully")
    for index, (job, status) in enumerate(zip(plan["jobs"], receipt["jobs"])):
        if (job["id"] != f"J{index:03d}" or set(status) != {"id", "status", "files"} or
                status["id"] != job["id"] or status["status"] != "passed" or
                status["files"] != _job_files(safe_path(root, job["id"]), job)):
            raise ValueError("Batch artifact integrity failed")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan/apply explicit PBR themes to multiple static assets")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = commands.add_parser(name)
        command.add_argument("recipe", type=Path)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--destination", type=Path, required=True)
        if name == "build":
            command.add_argument("--blender", type=Path, required=True)
            command.add_argument("--timeout", type=float, default=600)
    check = commands.add_parser("check")
    check.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    if args.command == "check":
        result = validate_batch(args.bundle)
    elif args.command == "plan":
        result = plan_batch(read_json(args.recipe), args.source)
        with args.destination.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    else:
        result = build_batch(read_json(args.recipe), args.source, args.destination,
                             blender=args.blender, timeout_seconds=args.timeout)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    from .executors import BudgetExpired
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, WorkerFailure, BudgetExpired) as error:
        print("Theme operation failed: " + (error.code if isinstance(error, WorkerFailure) else type(error).__name__))
        raise SystemExit(2)
