# SPDX-License-Identifier: GPL-3.0-or-later
"""Transport-neutral executor seam. No Codex Cloud API or implicit model calls."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Protocol

from .schema import Mission
from .storage import safe_path, write_json


class Cancelled(Exception):
    pass


class BudgetExpired(Exception):
    pass


WORKER_MESSAGES = {
    "codex_protocol": "codex_protocol: invalid or unsupported local app-server response",
    "codex_unresponsive": "codex_unresponsive: app-server exited or stopped responding",
    "codex_request_rejected": "codex_request_rejected: check installed CLI compatibility and local configuration",
    "codex_auth_required": "codex_auth_required: sign in with your existing ChatGPT account using the local Codex CLI",
    "codex_permissions": "codex_permissions: app-server did not honor read-only, no-approval permissions",
    "codex_turn_failed": "codex_turn_failed: local Codex turn did not complete successfully",
    "codex_no_audit": "codex_no_audit: Codex finished without calling the required worker",
    "codex_tool_budget": "codex_tool_budget: repeated audit tool call budget exhausted",
    "worker_failed": "worker_failed: subprocess exited unsuccessfully",
    "target_not_found": "target_not_found: requested object is absent from an input scene",
    "complexity_budget": "complexity_budget: mesh or scene exceeds Asset Doctor limits",
    "invalid_asset": "invalid_asset: check fixture schema, geometry values and input file integrity",
    "runtime_missing": "runtime_missing: Blender or required Loopcut Python module is unavailable",
    "missing_dependency": "missing_dependency: required input or local dependency cannot be found",
    "blender_error": "blender_error: headless scene loading or inspection failed",
}


class WorkerFailure(Exception):
    """Permanent worker failure. Only an allowlisted error code may be persisted."""
    def __init__(self, *args, code="worker_failed"):
        super().__init__(*args)
        self.code = code if code in WORKER_MESSAGES else "worker_failed"


class RetryableFailure(WorkerFailure):
    pass


@dataclass(frozen=True)
class ExecutionContext:
    folder: Path
    output: Path
    snapshots: tuple[str, ...]
    cancelled: threading.Event
    deadline: float

    def checkpoint(self):
        if self.cancelled.is_set():
            raise Cancelled()
        if time.monotonic() >= self.deadline:
            raise BudgetExpired()


class CodexExecutor(Protocol):
    """Contract for mock, Blender and authenticated Codex dispatch.

    Own only context.output; read snapshots; never merge or access live scene state.
    Implement cancellation/deadline checks and stop all child work before returning.
    """
    name: str

    def execute(self, mission: Mission, context: ExecutionContext) -> list[str]: ...


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def run_process(command, context, popen=subprocess.Popen):
    context.checkpoint()
    temp = safe_path(context.output, "tmp")
    temp.mkdir()
    # No model/API credential inheritance, no unbounded stdout/stderr log files.
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "HOME",
                                     "USERPROFILE", "LANG", "LD_LIBRARY_PATH") if k in os.environ}
    env.update(TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp), PYTHONNOUSERSITE="1",
               BLENDER_USER_CONFIG=str(temp), BLENDER_USER_SCRIPTS=str(temp), BLENDER_USER_EXTENSIONS=str(temp))
    options = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    process = popen(command, cwd=context.output, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
    try:
        while process.poll() is None:
            context.checkpoint()
            context.cancelled.wait(min(0.05, max(0, context.deadline - time.monotonic())))
        context.checkpoint()
        if process.returncode:
            code = "worker_failed"
            error_file = safe_path(context.output, "worker_error.json")
            if error_file.is_file() and error_file.stat().st_size <= 4096:
                try:
                    code = json.loads(error_file.read_text(encoding="utf-8")).get("code", code)
                except (ValueError, AttributeError):
                    pass
            raise WorkerFailure(code=code)
    finally:
        stop_process(process)


class _ProcessExecutor:
    mode = "fixture"

    def command(self, request):
        return [sys.executable, str(Path(__file__).with_name("doctor_worker.py")), "--", str(request)]

    def execute(self, mission, context):
        suffix = ".json" if self.mode == "fixture" else ".blend"
        if any(Path(name).suffix.lower() != suffix for name in context.snapshots):
            raise ValueError("Input extension does not match configured executor")
        if self.mode == "fixture" and mission.constraints.repair_copy:
            raise ValueError("Fixture executor supports audit only")
        request = safe_path(context.output, "request.json")
        write_json(request, {"mission": mission.json(), "mode": self.mode,
                            "snapshots": [str(safe_path(context.folder, name)) for name in context.snapshots]})
        run_process(self.command(request), context)
        outputs = ["quality.json"]
        outputs += [f"repaired-{i}.blend" for i in range(len(context.snapshots))
                    if safe_path(context.output, f"repaired-{i}.blend").exists()]
        return outputs


class MockCodexExecutor(_ProcessExecutor):
    """A deterministic Claude -> mock Codex -> isolated Python worker path, not an LLM."""
    name = "mock_codex"


class BlenderExecutor(_ProcessExecutor):
    """Direct headless worker dispatch; this does not invoke the Codex model."""
    name = "blender_headless"
    mode = "blender"

    def __init__(self, binary):
        self.binary = str(Path(binary).resolve(strict=True))
        if not Path(self.binary).is_file():
            raise ValueError("Blender executable must be a file")

    def command(self, request):
        return [self.binary, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                "--python-exit-code", "1", "--python", str(Path(__file__).with_name("doctor_worker.py")),
                "--", str(request)]
