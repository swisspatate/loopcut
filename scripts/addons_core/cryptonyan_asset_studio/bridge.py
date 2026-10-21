# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent mission queue with one owning process and bounded, isolated execution."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import threading
import time
import uuid

from .executors import BudgetExpired, Cancelled, ExecutionContext, RetryableFailure, WorkerFailure, WORKER_MESSAGES
from .schema import Mission, State, TERMINAL, TaskRecord, integer, now
from .storage import OwnerLock, Store, digest, safe_path

ERRORS = {BudgetExpired: "timeout: total execution budget exhausted",
          WorkerFailure: "worker_failed: subprocess exited unsuccessfully",
          RetryableFailure: "retry_exhausted: transient worker failure",
          ValueError: "invalid_worker_result_or_input: check schema, complexity budget and executor input type"}


class MissionBridge:
    def __init__(self, root, asset_root, executor, *, max_workers=2, max_pending=128):
        integer(max_workers, "max_workers", 1, 8)
        integer(max_pending, "max_pending", 1, 1024)
        self.store = Store(root)
        self.asset_root = Path(asset_root).resolve(strict=True)
        if not self.asset_root.is_dir() or self.store.root == self.asset_root or self.store.root.is_relative_to(self.asset_root):
            raise ValueError("Use a workspace outside the input asset root")
        self.owner = OwnerLock(safe_path(self.store.root, "owner.lock"))
        self.executor, self.max_pending = executor, max_pending
        self.lock = threading.RLock()
        self.cancel_events, self.futures = {}, {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cryptonyan")
        try:
            # A dead service is never silently retried; the user may revise the immutable mission.
            records = self.store.all()
            if any(r["state"] == State.QUEUED and r["executor"] != executor.name for r in records):
                raise RuntimeError("Queued missions require their original executor")
            for record in records:
                state = State(record["state"])
                if state == State.RUNNING:
                    self.store.update(record["id"], state=State.FAILED, error="interrupted: service restarted", finished_at=now())
                elif state == State.CANCELLING:
                    self.store.update(record["id"], state=State.CANCELLED, finished_at=now())
                elif state == State.QUEUED:
                    self._schedule(record["id"])
        except BaseException:
            self.close()
            raise

    def _schedule(self, identity):
        self.cancel_events[identity] = threading.Event()
        self.futures[identity] = self.pool.submit(self._run, identity)

    def submit(self, payload, *, revision_of=None):
        mission = Mission.parse(payload)
        with self.lock:
            if self.closed:
                raise RuntimeError("Mission service is closed")
            if sum(State(r["state"]) not in TERMINAL for r in self.store.all()) >= self.max_pending:
                raise ValueError("Queue capacity reached")
            paths = [safe_path(self.asset_root, name) for name in mission.inputs]
            if any(not p.is_file() or p.suffix.lower() not in (".blend", ".json") for p in paths):
                raise ValueError("Inputs must be existing .blend or .json files under asset_root")
            if sum(p.stat().st_size for p in paths) > 512 * 1024 * 1024:
                raise ValueError("Input snapshot budget exceeds 512 MiB")
            identity = uuid.uuid4().hex
            folder = self.store.folder(identity)
            folder.mkdir(mode=0o700)
            snapshots = []
            try:
                for i, path in enumerate(paths):
                    before = digest(path)
                    filename = f"source-{i}{path.suffix.lower()}"
                    target = safe_path(folder, filename)
                    shutil.copyfile(path, target)
                    if before != digest(target) or before != digest(path):
                        raise ValueError("Source changed while snapshotting; retry after saving")
                    snapshots.append({"path": filename, "sha256": before})
                record: TaskRecord = {"schema": "cryptonyan.task/1", "id": identity, "mission": mission.json(),
                          "revision_of": revision_of, "executor": self.executor.name,
                          "ownership": {"scope": "job_directory", "merge_policy": "manual_review_only"},
                          "state": State.QUEUED.value, "attempts": 0, "created_at": now(), "updated_at": now(),
                          "started_at": None, "finished_at": None, "error": None,
                          "snapshots": snapshots, "artifacts": [], "quality_passed": None}
                self.store.create(record)
            except BaseException:
                shutil.rmtree(folder)
                raise
            self._schedule(identity)
            return record

    def query(self, identity):
        return self.store.get(identity)

    def cancel(self, identity):
        with self.lock:
            record = self.query(identity)
            state = State(record["state"])
            if state in TERMINAL or state == State.CANCELLING:
                return record
            self.cancel_events[identity].set()
            target = State.CANCELLED if state == State.QUEUED else State.CANCELLING
            return self.store.update(identity, state=target, **({"finished_at": now()} if target == State.CANCELLED else {}))

    def revise(self, identity, payload):
        with self.lock:
            if State(self.query(identity)["state"]) not in TERMINAL:
                raise ValueError("Cancel and await completion before revising an active task")
            return self.submit(payload, revision_of=identity)

    def result(self, identity):
        record = self.query(identity)
        if State(record["state"]) != State.SUCCEEDED:
            raise ValueError("Task has no completed result")
        for artifact in record["artifacts"]:
            path = safe_path(self.store.folder(identity), artifact["path"])
            if not path.is_file() or digest(path) != artifact["sha256"]:
                raise ValueError("Artifact missing or changed since completion")
        quality = next(a for a in record["artifacts"] if a["path"].endswith("/quality.json"))
        result = {"task": record, "quality": json.loads(safe_path(self.store.folder(identity), quality["path"]).read_text(encoding="utf-8"))}
        if record["mission"]["type"] == "asset_publish" and record["quality_passed"]:
            from .publication import load_package
            result["publication"] = load_package(safe_path(self.store.folder(identity), quality["path"]).parent / "manifest.json")
        return result

    def _run(self, identity):
        try:
            with self.lock:
                record = self.query(identity)
                if record["state"] == State.CANCELLED:
                    return
                self.store.update(identity, state=State.RUNNING, started_at=now())
            mission = Mission.parse(record["mission"])
            deadline = time.monotonic() + mission.constraints.timeout_seconds
            for attempt in range(1, mission.constraints.max_attempts + 1):
                self.store.update(identity, attempts=attempt)
                folder = self.store.folder(identity)
                output = safe_path(folder, f"attempt-{attempt}")
                output.mkdir()
                context = ExecutionContext(folder, output, tuple(s["path"] for s in record["snapshots"]),
                                           self.cancel_events[identity], deadline)
                context.checkpoint()
                for snapshot in record["snapshots"]:
                    if digest(safe_path(folder, snapshot["path"])) != snapshot["sha256"]:
                        raise ValueError("Snapshot changed")
                try:
                    names = self.executor.execute(mission, context)
                    context.checkpoint()
                    if not isinstance(names, list) or "quality.json" not in names or len(names) != len(set(names)):
                        raise ValueError("Missing quality report or duplicate artifacts")
                    artifacts = []
                    for name in names:
                        path = safe_path(output, name)
                        if not path.is_file():
                            raise ValueError("Missing artifact")
                        artifacts.append({"path": path.relative_to(folder).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size})
                    quality_path = safe_path(output, "quality.json")
                    if quality_path.stat().st_size > 32 * 1024 * 1024:
                        raise ValueError("Quality report exceeds 32 MiB budget")
                    quality = json.loads(quality_path.read_text(encoding="utf-8"))
                    if quality.get("schema") != "cryptonyan.quality-batch/1" or type(quality.get("passed")) is not bool or not quality.get("reports"):
                        raise ValueError("Invalid quality report")
                    reports = quality["reports"]
                    if not isinstance(reports, list) or len(reports) != len(record["snapshots"]) or any(
                        not isinstance(r, dict) or r.get("schema") != "cryptonyan.asset-doctor/1" or
                        type(r.get("passed")) is not bool or not isinstance(r.get("objects"), list) for r in reports):
                        raise ValueError("Invalid per-asset reports")
                    if quality["passed"] != all(r["passed"] for r in reports):
                        raise ValueError("Inconsistent quality status")
                    if mission.type == "asset_publish":
                        from .publication import load_package
                        if quality["passed"]:
                            package = load_package(output / "manifest.json")
                            if (set(names) - {"codex-dispatch.json"} != {"quality.json", "manifest.json", package["asset"]["file"]} or
                                    package["source"]["sha256"] != record["snapshots"][0]["sha256"] or
                                    package["source"]["object"] != mission.target_assets[0]):
                                raise ValueError("Publication does not match mission or artifacts")
                        elif set(names) - {"codex-dispatch.json"} != {"quality.json"}:
                            raise ValueError("Failed quality gate must not publish assets")
                    with self.lock:
                        context.checkpoint()
                        self.store.update(identity, state=State.SUCCEEDED, artifacts=artifacts,
                                          quality_passed=quality["passed"], finished_at=now())
                    return
                except RetryableFailure:
                    if attempt == mission.constraints.max_attempts:
                        raise
                    context.cancelled.wait(min(0.1 * attempt, max(0, deadline - time.monotonic())))
                    context.checkpoint()
        except Exception as error:
            with self.lock:
                state = State(self.query(identity)["state"])
                if state in TERMINAL:
                    return
                if state == State.CANCELLING or isinstance(error, Cancelled):
                    if state != State.CANCELLING:
                        self.store.update(identity, state=State.CANCELLING)
                    self.store.update(identity, state=State.CANCELLED, finished_at=now())
                else:
                    message = ERRORS.get(type(error), "executor_error: see executor contract and local setup")
                    if isinstance(error, WorkerFailure) and not isinstance(error, RetryableFailure):
                        message = WORKER_MESSAGES[error.code]
                    self.store.update(identity, state=State.FAILED, finished_at=now(),
                                      error=message)

    def wait(self, identity, timeout=None):
        self.futures[identity].result(timeout=timeout)
        return self.query(identity)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for identity in list(self.cancel_events):
                self.cancel(identity)
        self.pool.shutdown(wait=True)
        self.owner.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
