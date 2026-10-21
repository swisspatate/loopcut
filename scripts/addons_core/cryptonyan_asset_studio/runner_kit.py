# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit runner planning and isolated Blender kit builds; no editor/network access."""
import argparse
import json
import math
from pathlib import Path
import tempfile
import threading
import time

from .executors import BlenderExecutor, ExecutionContext, run_process
from .procedural_level_builder import build_layout, analyze_layout, points_csv, preview_svg, scan_seeds, validate_layout
from .publication import asset_name, load_package
from .storage import digest, safe_path, write_json


def _read_text(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Invalid runner input file or size")
    return path.read_text(encoding="utf-8-sig")


def read_json(path):
    return json.loads(_read_text(path))


def build_bundle(recipe, destination, *, blender=None, timeout_seconds=120):
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid runner build timeout")
    layout = build_layout(recipe)
    analysis = analyze_layout(layout)
    # Validate the explicit executable before creating output directories.
    executor = BlenderExecutor(blender) if blender is not None and analysis["model_passed"] else None
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    destination = destination.resolve()
    write_json(destination / "layout.json", layout)
    write_json(destination / "analysis.json", analysis)
    (destination / "pcg-points.csv").write_text(points_csv(layout), encoding="utf-8", newline="")
    (destination / "preview.svg").write_text(preview_svg(layout), encoding="utf-8", newline="")
    result = {"layout_id": layout["layout_id"], "model_passed": analysis["model_passed"],
              "engine_validated": False, "built": False, "directory": str(destination)}
    if executor is not None:
        with tempfile.TemporaryDirectory(prefix=".runner-", dir=destination) as temp:
            runtime = Path(temp).resolve()
            request = runtime / "request.json"
            write_json(request, {"bundle": str(destination), "layout_sha256": digest(destination / "layout.json")})
            context = ExecutionContext(runtime, runtime, (), threading.Event(), time.monotonic() + timeout_seconds)
            command = executor.command(request)
            command[command.index("--python") + 1] = str(Path(__file__).with_name("runner_worker.py"))
            run_process(command, context)
        validate_bundle(destination)
        result["built"] = True
    return result


def validate_bundle(root):
    root = Path(root).resolve()
    layout = validate_layout(read_json(safe_path(root, "layout.json")))
    analysis = read_json(safe_path(root, "analysis.json"))
    if analysis != analyze_layout(layout) or not analysis["model_passed"]:
        raise ValueError("Runner analysis is stale or did not pass")
    if _read_text(safe_path(root, "pcg-points.csv")) != points_csv(layout):
        raise ValueError("Runner point table differs from layout")
    if _read_text(safe_path(root, "preview.svg")) != preview_svg(layout):
        raise ValueError("Runner preview differs from layout")
    catalog = read_json(safe_path(root, "kit.json"))
    if (set(catalog) != {"schema", "layout_id", "module", "files", "engine_validated"} or
            catalog["schema"] != "cryptonyan.runner-kit/1" or catalog["layout_id"] != layout["layout_id"] or
            catalog["module"] != layout["module"] or catalog["engine_validated"] is not False):
        raise ValueError("Invalid runner kit catalog")
    expected = {"layout.json", "analysis.json", "pcg-points.csv", "preview.svg", "modules.blend", "preview.blend",
                "publication/manifest.json", "publication/quality.json", "publication/" + asset_name("RunnerPlatform") + ".glb"}
    if not isinstance(catalog["files"], dict) or set(catalog["files"]) != expected:
        raise ValueError("Runner kit artifact set differs")
    for relative, item in catalog["files"].items():
        path = safe_path(root, relative)
        if set(item) != {"sha256", "bytes"} or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Runner kit artifact integrity failed")
    package = load_package(safe_path(root, "publication/manifest.json"))
    length, width, thickness = layout["module"]["size_m"]
    expected_bounds = [[0, -width / 2, -thickness], [length, width / 2, 0]]
    if (package["source"]["sha256"] != digest(safe_path(root, "modules.blend")) or
            package["source"]["object"] != "RunnerPlatform" or package["asset"]["triangles"] != 12 or
            any(abs(a - b) > 1e-5 for va, vb in zip(package["asset"]["bounds_blender_m"], expected_bounds) for a, b in zip(va, vb))):
        raise ValueError("Published module does not match the kit dimensions, pivot or source")
    return catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic three-lane runner planning and Blender module kits")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = commands.add_parser(name)
        command.add_argument("recipe", type=Path)
        command.add_argument("--destination", required=True, type=Path)
        if name == "build":
            command.add_argument("--blender", required=True, type=Path)
            command.add_argument("--timeout", type=float, default=120)
    check = commands.add_parser("check")
    check.add_argument("bundle", type=Path)
    scan = commands.add_parser("scan")
    scan.add_argument("recipe", type=Path)
    scan.add_argument("--first-seed", type=int, default=0)
    scan.add_argument("--count", type=int, default=32)
    scan.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "scan":
        result = scan_seeds(read_json(args.recipe), first_seed=args.first_seed, count=args.count)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"report": str(args.report), "failure_seeds": result["failure_seeds"], "engine_validated": False}))
        return 0 if result["all_model_passed"] else 1
    if args.command == "check":
        result = validate_bundle(args.bundle)
    else:
        result = build_bundle(read_json(args.recipe), args.destination,
                              blender=getattr(args, "blender", None), timeout_seconds=getattr(args, "timeout", 120))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if args.command == "check" or result["model_passed"] else 1


if __name__ == "__main__":
    from .executors import WorkerFailure, BudgetExpired, WORKER_MESSAGES
    try:
        raise SystemExit(main())
    except WorkerFailure as error:
        print(WORKER_MESSAGES[error.code])
        raise SystemExit(2)
    except BudgetExpired:
        print("Runner build timed out; inspect the partial destination and choose a fresh one")
        raise SystemExit(2)
    except (ValueError, OSError, KeyError, TypeError):
        print("Runner operation failed; check recipe, input integrity, executable and new destination")
        raise SystemExit(2)
