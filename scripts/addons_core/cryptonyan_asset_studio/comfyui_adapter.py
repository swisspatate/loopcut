# SPDX-License-Identifier: GPL-3.0-or-later
"""Local ComfyUI HTTP adapter with durable receipts and bounded PNG collection.

Only an explicitly hash-approved API workflow is submitted. No model/node installation,
global interrupt, automatic retry, or inference about the licence of generated outputs.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Literal, Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import uuid

from .materials import MAX_IMAGE_BYTES, png_info
from .storage import OwnerLock, safe_path, write_json


@dataclass(frozen=True)
class GeneratedAsset:
    path: str
    sha256: str
    workflow_sha256: str
    model_sha256: tuple[str, ...]
    model_licenses: tuple[str, ...]  # Required provenance; unknown licenses block distribution.
    attribution: str


class ComfyUIAdapter(Protocol):
    """A deployment supplies the endpoint and approved workflow digest explicitly."""
    def submit_workflow(self, workflow: dict, *, seed: int, timeout_seconds: float) -> str: ...
    def poll_status(self, identity: str) -> Literal["queued", "running", "succeeded", "failed", "cancelled", "unknown"]: ...
    def cancel(self, identity: str) -> None: ...
    def collect_assets(self, identity: str, destination: str) -> tuple[GeneratedAsset, ...]: ...


def workflow_digest(workflow):
    return hashlib.sha256(json.dumps(workflow, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class ComfyError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ComfyError("ComfyUI redirects are disabled")


class LocalHTTP:
    def __init__(self, endpoint):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1") or
                parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ComfyError("Use an explicit loopback HTTP endpoint, e.g. http://127.0.0.1:8188")
        if parsed.port is None:
            raise ComfyError("An explicit ComfyUI port is required")
        self.endpoint = endpoint.rstrip("/")
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def __call__(self, method, path, payload=None, *, limit=8 * 1024 * 1024, timeout=10):
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        request = Request(self.endpoint + path, data=body, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                data = response.read(limit + 1)
        except Exception:
            raise ComfyError("ComfyUI request failed; submission may have been accepted, do not blindly retry") from None
        if len(data) > limit:
            raise ComfyError("ComfyUI response exceeds the byte budget")
        return data


def validate_config(config):
    if set(config) != {"endpoint", "workflow_sha256", "seed_inputs", "models"}:
        raise ComfyError("Invalid ComfyUI configuration fields")
    LocalHTTP(config["endpoint"])
    if not re.fullmatch(r"[a-f0-9]{64}", config["workflow_sha256"]):
        raise ComfyError("Invalid approved workflow digest")
    if not isinstance(config["seed_inputs"], list) or not config["seed_inputs"]:
        raise ComfyError("Declare the workflow's seed inputs")
    for binding in config["seed_inputs"]:
        if not isinstance(binding, list) or len(binding) != 2 or any(not isinstance(v, str) or not v for v in binding):
            raise ComfyError("Seed bindings must be [node_id, input_name] pairs")
    if not isinstance(config["models"], list) or len(config["models"]) > 32:
        raise ComfyError("Invalid model declarations")
    for model in config["models"]:
        if (set(model) != {"name", "sha256", "license", "attribution"} or
                any(not isinstance(v, str) or len(v) > 4096 for v in model.values()) or
                not re.fullmatch(r"[a-f0-9]{64}", model["sha256"])):
            raise ComfyError("Invalid model declaration")


class ComfyUIClient:
    """One owner per private job directory. Receipts survive CLI process restarts."""
    def __init__(self, config, workspace, *, transport=None):
        validate_config(config)
        http = LocalHTTP(config["endpoint"])
        self.config = json.loads(json.dumps(config))
        self.transport = transport or http
        self.root = Path(workspace).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = OwnerLock(safe_path(self.root, "comfy.lock"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.lock.close()

    def _json(self, method, path, payload=None):
        raw = self.transport(method, path, payload)
        try:
            result = json.loads(raw)
        except (ValueError, TypeError):
            raise ComfyError("Invalid ComfyUI JSON response") from None
        if not isinstance(result, dict):
            raise ComfyError("Invalid ComfyUI response structure")
        return result

    def _path(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9-]{36}", identity) or str(uuid.UUID(identity)) != identity:
            raise ComfyError("Invalid prompt identity")
        return safe_path(self.root, identity + ".json")

    def _job(self, identity):
        path = self._path(identity)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ComfyError("Invalid job receipt size")
        job = json.loads(path.read_text(encoding="utf-8-sig"))
        if job["endpoint"] != self.config["endpoint"] or job["prompt_id"] != identity:
            raise ComfyError("Job belongs to a different endpoint")
        return job

    def submit_workflow(self, workflow, *, seed, timeout_seconds=600):
        if type(seed) is not int or not 0 <= seed < 2**64 or type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
            raise ComfyError("Invalid seed or wait budget")
        if not isinstance(workflow, dict) or not workflow or len(json.dumps(workflow)) > 1024 * 1024 or workflow_digest(workflow) != self.config["workflow_sha256"]:
            raise ComfyError("Workflow does not match the approved API workflow hash")
        submitted = json.loads(json.dumps(workflow))
        for node, name in self.config["seed_inputs"]:
            if node not in submitted or type(submitted[node].get("inputs", {}).get(name)) is not int:
                raise ComfyError("Seed binding does not refer to a literal integer")
            submitted[node]["inputs"][name] = seed
        identity = str(uuid.uuid4())
        job = {"schema": "cryptonyan.comfy-job/1", "prompt_id": identity, "endpoint": self.config["endpoint"],
               "workflow_sha256": workflow_digest(submitted), "approved_workflow_sha256": self.config["workflow_sha256"],
               "workflow": submitted, "seed": seed, "models_declared": self.config["models"],
               "model_provenance_verified": False, "distribution_approved": False,
               "wait_budget_seconds": timeout_seconds, "submission": "uncertain"}
        write_json(self._path(identity), job)
        result = self._json("POST", "/prompt", {"prompt": submitted, "client_id": identity, "prompt_id": identity})
        if result.get("prompt_id") != identity or result.get("error") or result.get("node_errors"):
            raise ComfyError("Submission not confirmed; inspect the uncertain receipt and ComfyUI queue")
        job["submission"] = "accepted"
        write_json(self._path(identity), job)
        return identity

    def poll_status(self, identity):
        self._job(identity)
        history = self._json("GET", "/history/" + identity).get(identity)
        if history:
            status = history.get("status", {})
            messages = status.get("messages", [])
            if any(isinstance(m, list) and m and m[0] == "execution_interrupted" for m in messages):
                return "cancelled"
            if status.get("status_str") == "error":
                return "failed"
            if status.get("completed") is True and status.get("status_str") == "success":
                return "succeeded"
        queue = self._json("GET", "/queue")
        for key, state in (("queue_running", "running"), ("queue_pending", "queued")):
            if any(isinstance(row, list) and len(row) > 1 and row[1] == identity for row in queue.get(key, [])):
                return state
        # Missing/evicted history or a queue race cannot prove success or cancellation.
        return "unknown"

    def cancel(self, identity):
        job = self._job(identity)
        if self.poll_status(identity) != "queued":
            raise ComfyError("Only queued prompts can be removed; cancel a running prompt in ComfyUI")
        self.transport("POST", "/queue", {"delete": [identity]})
        job["queue_removal_requested"] = True
        write_json(self._path(identity), job)
        # Never call /interrupt: older servers ignore prompt_id and interrupt other work.

    def collect_assets(self, identity, destination):
        job = self._job(identity)
        history = self._json("GET", "/history/" + identity).get(identity, {})
        status = history.get("status", {})
        if status.get("completed") is not True or status.get("status_str") != "success":
            raise ComfyError("Only completed successful prompts can be collected")
        outputs = history.get("outputs", {})
        descriptors = [(node, index, item) for node, output in outputs.items()
                       for index, item in enumerate(output.get("images", []))]
        if not descriptors or len(descriptors) > 16:
            raise ComfyError("Expected 1 to 16 PNG outputs")
        prepared, total = [], 0
        for node, index, item in descriptors:
            filename, subfolder = item.get("filename", ""), item.get("subfolder", "")
            if item.get("type") != "output" or not isinstance(filename, str) or "/" in filename or not filename.lower().endswith(".png"):
                raise ComfyError("Only saved PNG outputs are supported")
            safe_path(self.root, filename)
            if not isinstance(subfolder, str) or len(subfolder) > 4096:
                raise ComfyError("Invalid output subfolder")
            # ComfyUI on Windows returns native separators. Normalize only this
            # descriptor field, then retain all clean-relative-path checks.
            subfolder = subfolder.replace("\\", "/")
            if subfolder:
                safe_path(self.root, subfolder)
            query = urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
            payload = self.transport("GET", "/view?" + query, limit=MAX_IMAGE_BYTES)
            total += len(payload)
            if total > 128 * 1024 * 1024:
                raise ComfyError("Collection exceeds total byte budget")
            info = png_info(payload)
            prepared.append((payload, {"file": f"image-{len(prepared):02d}.png", "node": node,
                                      "output_index": index, "sha256": hashlib.sha256(payload).hexdigest(), **info}))
        destination = Path(destination)
        destination.mkdir(exist_ok=False)
        assets = []
        for payload, item in prepared:
            path = destination / item["file"]
            path.write_bytes(payload)
            assets.append(GeneratedAsset(str(path), item["sha256"], job["workflow_sha256"],
                          tuple(m["sha256"] for m in job["models_declared"]),
                          tuple(m["license"] for m in job["models_declared"]),
                          "\n".join(m["attribution"] for m in job["models_declared"])))
        write_json(destination / "generation.json", {**job, "outputs": [item for _, item in prepared]})
        return tuple(assets)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit local ComfyUI jobs; no model or custom-node installation")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("workflow", type=Path)
    submit.add_argument("--seed", required=True, type=int)
    submit.add_argument("--timeout", type=float, default=600)
    for name in ("status", "cancel", "collect", "wait"):
        command = commands.add_parser(name)
        command.add_argument("prompt_id")
        if name == "collect":
            command.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    with ComfyUIClient(json.loads(args.config.read_text(encoding="utf-8-sig")), args.workspace) as client:
        if args.command == "submit":
            result = {"prompt_id": client.submit_workflow(json.loads(args.workflow.read_text(encoding="utf-8-sig")),
                       seed=args.seed, timeout_seconds=args.timeout)}
        elif args.command == "collect":
            result = {"assets": [a.__dict__ for a in client.collect_assets(args.prompt_id, args.destination)]}
        elif args.command == "cancel":
            client.cancel(args.prompt_id)
            result = {"queue_removal_requested": True, "status": client.poll_status(args.prompt_id)}
        else:
            deadline = time.monotonic() + client._job(args.prompt_id)["wait_budget_seconds"]
            while True:
                status = client.poll_status(args.prompt_id)
                if args.command != "wait" or status not in ("queued", "running") or time.monotonic() >= deadline:
                    break
                time.sleep(1)
            result = {"status": status}
            if args.command == "wait" and status != "succeeded":
                print(json.dumps(result))
                return 1
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error) if isinstance(error, ComfyError) else "Invalid local ComfyUI configuration, receipt or output")
        raise SystemExit(2)
