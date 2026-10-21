# SPDX-License-Identifier: GPL-3.0-or-later
"""python -m cryptonyan_asset_studio --help"""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
import uuid

from .bridge import MissionBridge
from .executors import BlenderExecutor, BudgetExpired, ExecutionContext, MockCodexExecutor, WorkerFailure, WORKER_MESSAGES
from .mcp_stdio import serve
from .storage import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="CryptoNyan mission bridge (local, explicit execution)")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--executor", choices=("mock", "blender", "codex"), default="mock")
    parser.add_argument("--blender", type=Path, help="Explicit Blender executable for headless dispatch")
    parser.add_argument("--codex", type=Path, help="Explicit Codex executable for authenticated local app-server")
    parser.add_argument("--codex-home", type=Path, help="Existing Codex sign-in profile; defaults to normal CLI profile")
    parser.add_argument("--codex-model", help="Optional model name; otherwise use the user's Codex configuration")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--comfy-profiles", type=Path, help="Optional reviewed ComfyUI profile catalog for MCP texture tools")
    parser.add_argument("--game-project", type=Path, help="Optional existing Unreal project for read-only inventory and asset-bound texture candidates")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Serve MCP on stdin/stdout until EOF; no network listener")
    commands.add_parser("probe-codex", help="Check app-server handshake/sign-in metadata without calling a model")
    run = commands.add_parser("run", help="Submit a mission JSON, wait, print its task and quality report")
    run.add_argument("mission", type=Path)
    publish = commands.add_parser("publish", help="Audit and package one static mesh for Unreal review; does not launch Unreal")
    publish.add_argument("input", help=".blend path relative to asset-root")
    publish.add_argument("--object", required=True, dest="target_object")
    publish.add_argument("--max-triangles", type=int, default=100000)
    batch = commands.add_parser("batch", help="Audit .json fixtures or .blend files directly in asset-root")
    batch.add_argument("--repair-copy", action="store_true")
    show = commands.add_parser("show", help="Read a persistent task without launching an executor")
    show.add_argument("task_id")
    args = parser.parse_args(argv)
    if args.game_project is not None:
        if args.command != "serve":
            parser.error("--game-project is supported by serve; use the game_project module for offline inventory")
        project_root, workspace_root = args.game_project.resolve(), args.workspace.resolve()
        if workspace_root.is_relative_to(project_root) or project_root.is_relative_to(workspace_root):
            parser.error("Game project and workspace must be separate directories")
        from .game_project import GameProject
        project = GameProject(project_root)
    else:
        project = None
    if args.command == "show":
        print(json.dumps(Store(args.workspace).get(args.task_id), indent=2))
        return 0
    if args.command == "probe-codex" or args.executor == "codex":
        if args.codex is None:
            parser.error("--codex is required for the local Codex adapter")
        from .codex_executor import CodexAppServerExecutor
    if args.command == "probe-codex":
        args.workspace.mkdir(parents=True, exist_ok=True)
        output = args.workspace.resolve() / ("probe-" + uuid.uuid4().hex)
        output.mkdir(mode=0o700)
        context = ExecutionContext(output, output, (), threading.Event(), time.monotonic() + 20)
        executor = CodexAppServerExecutor(args.codex, MockCodexExecutor(), codex_home=args.codex_home)
        result = executor.probe(context)
        print(json.dumps(result, indent=2))
        return 0 if result["chatgpt_authenticated"] else 1
    if args.asset_root is None or args.executor in ("blender", "codex") and args.blender is None:
        parser.error("--asset-root and (for blender/codex) --blender are required")
    executor = BlenderExecutor(args.blender) if args.executor in ("blender", "codex") else MockCodexExecutor()
    if args.executor == "codex":
        executor = CodexAppServerExecutor(args.codex, executor, codex_home=args.codex_home, model=args.codex_model)
    with MissionBridge(args.workspace, args.asset_root, executor, max_workers=args.workers) as bridge:
        if args.command == "serve":
            if args.comfy_profiles is None:
                serve(bridge, sys.stdin, sys.stdout, project=project)
            else:
                from .comfy_profiles import TextureService
                from .storage import safe_path
                with TextureService(args.comfy_profiles, safe_path(args.workspace, "textures")) as textures:
                    if project is not None:
                        project = GameProject(args.game_project, textures)
                    serve(bridge, sys.stdin, sys.stdout, textures, project)
            return 0
        if args.command == "publish":
            if args.executor == "mock":
                parser.error("publish requires --executor blender or codex")
            payloads = [{"type": "asset_publish", "inputs": [args.input], "target_assets": [args.target_object],
                         "success_criteria": {"max_triangles": args.max_triangles}}]
        elif args.command == "run":
            payloads = [json.loads(args.mission.read_text(encoding="utf-8"))]
        else:
            suffix = ".blend" if args.executor in ("blender", "codex") else ".json"
            payloads = [{"inputs": [p.name], "constraints": {"repair_copy": args.repair_copy}}
                        for p in sorted(args.asset_root.iterdir()) if p.is_file() and p.suffix.lower() == suffix]
            if not payloads:
                raise ValueError("No matching input files")
        # Queue in bounded groups; a large directory must not exhaust pending slots.
        results = []
        for start in range(0, len(payloads), 32):
            tasks = [bridge.submit(payload) for payload in payloads[start:start + 32]]
            for task in tasks:
                final = bridge.wait(task["id"])
                results.append(bridge.result(task["id"]) if final["state"] == "succeeded" else {"task": final})
        print(json.dumps(results, indent=2, allow_nan=False))
        return 0 if all(r["task"]["state"] == "succeeded" and r["task"]["quality_passed"] for r in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WorkerFailure as error:
        print(WORKER_MESSAGES[error.code], file=sys.stderr)
        raise SystemExit(2)
    except BudgetExpired:
        print("Codex probe timed out; check local app-server startup.", file=sys.stderr)
        raise SystemExit(2)
    except (ValueError, OSError, RuntimeError):
        print("Operation failed: check mission JSON, workspace, input paths and executor configuration.", file=sys.stderr)
        raise SystemExit(2)
