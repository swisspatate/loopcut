# SPDX-License-Identifier: GPL-3.0-or-later
"""Operator-approved ComfyUI profiles for agents; reuse the local HTTP adapter.

The operator owns the catalog and private workspace. Agents select a profile and
change only its declared prompt/seed literals, never graphs, models or output paths.
"""
import copy
import json
from pathlib import Path
import re
import shutil
import tempfile

from .comfyui_adapter import ComfyError, ComfyUIClient, LocalHTTP, validate_config, workflow_digest
from .materials import CHANNELS, load_material, pack_material
from .storage import OwnerLock, digest, safe_path, write_json
from .comfy_preflight import preflight, validate_parameters
from .comfy_references import validate_references

MAX_REQUESTS = 256


def _read(path, limit=2 * 1024 * 1024):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ComfyError("Invalid or oversized profile/receipt file")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value):
        raise ComfyError("Use a 1-64 character alphanumeric, dash or underscore identifier")
    return value


def _bindings(workflow, bindings, kind):
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 16:
        raise ComfyError("Declare 1-16 literal prompt/seed bindings")
    seen = set()
    for pair in bindings:
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(v, str) or not v for v in pair):
            raise ComfyError("Bindings must be [node_id, input_name] pairs")
        node, name = pair
        if tuple(pair) in seen or type(workflow.get(node, {}).get("inputs", {}).get(name)) is not kind:
            raise ComfyError("Duplicate binding or wrong literal input type")
        seen.add(tuple(pair))


def load_catalog(path):
    path = Path(path)
    catalog = _read(path)
    if (not isinstance(catalog, dict) or not {"schema", "endpoint", "profiles"} <= set(catalog) <= {"schema", "endpoint", "profiles", "input_root"}
            or catalog["schema"] != "cryptonyan.comfy-profiles/1"
            or not isinstance(catalog["profiles"], list) or len(catalog["profiles"]) > 32):
        raise ComfyError("Invalid ComfyUI profile catalog")
    LocalHTTP(catalog["endpoint"])
    profiles, total = {}, 0
    for profile in catalog["profiles"]:
        if not isinstance(profile, dict) or not {"id", "description", "workflow", "workflow_sha256", "prompt_inputs", "seed_inputs", "models", "outputs"} <= set(profile) <= {
                "id", "description", "workflow", "workflow_sha256", "prompt_inputs", "seed_inputs", "models", "outputs", "reference_inputs"}:
            raise ComfyError("Invalid ComfyUI profile fields")
        identity = _identifier(profile["id"])
        if identity in profiles or not isinstance(profile["description"], str) or not 1 <= len(profile["description"]) <= 1024:
            raise ComfyError("Duplicate profile or invalid description")
        source = safe_path(path.parent, profile["workflow"])
        workflow = _read(source, 1024 * 1024)
        total += source.stat().st_size
        if total > 8 * 1024 * 1024:
            raise ComfyError("Profile workflows exceed the 8 MiB catalog budget")
        if not isinstance(workflow, dict) or not workflow or workflow_digest(workflow) != profile["workflow_sha256"]:
            raise ComfyError("Profile workflow does not match its approved hash")
        for node in workflow.values():
            if not isinstance(node, dict) or not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
                raise ComfyError("Export the workflow in ComfyUI API format")
        _bindings(workflow, profile["prompt_inputs"], str)
        _bindings(workflow, profile["seed_inputs"], int)
        outputs = profile["outputs"]
        if not isinstance(outputs, dict) or "base_color" not in outputs or not set(outputs) <= CHANNELS.keys():
            raise ComfyError("Map base_color and optional supported PBR outputs explicitly")
        seen = set()
        for binding in outputs.values():
            if (not isinstance(binding, list) or len(binding) != 2 or not isinstance(binding[0], str)
                    or binding[0] not in workflow or type(binding[1]) is not int or not 0 <= binding[1] < 16
                    or tuple(binding) in seen):
                raise ComfyError("Outputs need distinct [node_id, image_index] bindings")
            seen.add(tuple(binding))
        # Validate adapter configuration without opening a workspace or a connection.
        config = {"endpoint": catalog["endpoint"], "workflow_sha256": profile["workflow_sha256"],
                  "seed_inputs": profile["seed_inputs"], "models": profile["models"]}
        validate_config(config)
        profiles[identity] = {**copy.deepcopy(profile), "template": workflow}
        if profile.get("reference_inputs"):
            profiles[identity]["input_root"] = catalog.get("input_root")
        validate_references(profiles[identity])
    return catalog["endpoint"], profiles


class TextureService:
    """Single-owner durable request IDs; repeated submissions never enqueue twice.

    This is a synchronous MCP service, not a thread-safe public Python API. Only
    submission, polling and bounded collection block; GPU inference runs in ComfyUI.
    """
    def __init__(self, catalog, workspace, *, transport=None):
        self.endpoint, self.profiles = load_catalog(catalog)
        self.transport = transport
        self.root = Path(workspace).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.requests = safe_path(self.root, "requests")
        self.requests.mkdir(exist_ok=True)
        self.lock = OwnerLock(safe_path(self.root, "profiles.lock"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.lock.close()

    def catalog(self):
        return {"profiles": [{"id": p["id"], "description": p["description"],
                              "template_sha256": p["workflow_sha256"], "models_declared": p["models"],
                              "references": p.get("reference_inputs", []),
                              "channels": list(p["outputs"]), "parameters": ["prompt", "seed"]}
                             for p in self.profiles.values()],
                "model_provenance_verified": False, "distribution_approved": False}

    def _folder(self, request_id):
        return safe_path(self.requests, _identifier(request_id))

    def preflight(self, profile, prompt, seed):
        selected = self.profiles.get(_identifier(profile))
        if selected is None:
            raise ComfyError("Unknown texture profile; list configured profiles first")
        validate_references(selected)
        return preflight(selected, self.endpoint, prompt, seed, transport=self.transport)

    def _record(self, request_id):
        folder = self._folder(request_id)
        record = _read(safe_path(folder, "request.json"))
        if record["request"]["request_id"] != request_id:
            raise ComfyError("Request receipt identity mismatch")
        return folder, record

    def _client(self, folder, record):
        return ComfyUIClient(record["config"], safe_path(folder, "http"), transport=self.transport)

    def _summary(self, request_id):
        folder, record = self._record(request_id)
        receipts = list(safe_path(folder, "http").glob("*.json"))
        if len(receipts) > 1:
            raise ComfyError("Ambiguous local request receipts; inspect workspace")
        job = _read(safe_path(folder, "http/" + receipts[0].name)) if receipts else {}
        return {"request_id": request_id, "profile": record["request"]["profile"],
                "seed": record["request"]["seed"], "prompt_id": job.get("prompt_id"),
                "submission": job.get("submission", "uncertain"),
                "collected": safe_path(folder, "result/texture.json").is_file()}

    def jobs(self):
        result = []
        for path in sorted(self.requests.iterdir()):
            if len(result) >= MAX_REQUESTS:
                raise ComfyError("Workspace exceeds request capacity")
            try:
                result.append(self._summary(path.name))
            except (ValueError, OSError, KeyError, TypeError):
                result.append({"request_id": path.name, "submission": "incomplete", "manual_inspection_required": True})
        return {"requests": result, "capacity": MAX_REQUESTS}

    def submit(self, profile, prompt, seed, request_id):
        folder = self._folder(request_id)
        validate_parameters(prompt, seed)
        _identifier(profile)
        request = {"request_id": request_id, "profile": profile, "prompt": prompt, "seed": seed}
        if folder.exists():
            _, record = self._record(request_id)
            if record["request"] != request:
                raise ComfyError("Request ID already used with different parameters")
            return self._summary(request_id)  # No network, even after an uncertain POST or catalog change.
        if profile not in self.profiles:
            raise ComfyError("Unknown texture profile; list configured profiles first")
        if sum(1 for _ in self.requests.iterdir()) >= MAX_REQUESTS:
            raise ComfyError("Workspace request capacity reached; archive it before using a new workspace")
        selected = self.profiles[profile]
        validate_references(selected)
        workflow = copy.deepcopy(selected["template"])
        for node, name in selected["prompt_inputs"]:
            workflow[node]["inputs"][name] = prompt
        config = {"endpoint": self.endpoint, "workflow_sha256": workflow_digest(workflow),
                  "seed_inputs": selected["seed_inputs"], "models": selected["models"]}
        folder.mkdir(mode=0o700)
        record = {"schema": "cryptonyan.texture-request/1", "request": request, "config": config,
                  "template_sha256": selected["workflow_sha256"], "outputs": selected["outputs"],
                  "references": selected.get("reference_inputs", [])}
        write_json(folder / "request.json", record)
        with self._client(folder, record) as client:
            try:
                client.submit_workflow(workflow, seed=seed)
            except (ComfyError, OSError):
                # Receipt was persisted before POST. Never resubmit automatically.
                return {**self._summary(request_id), "manual_inspection_required": True}
        return self._summary(request_id)

    def status(self, request_id):
        folder, record = self._record(request_id)
        summary = self._summary(request_id)
        if summary["prompt_id"] is None:
            return {**summary, "status": "unknown", "manual_inspection_required": True}
        with self._client(folder, record) as client:
            return {**summary, "status": client.poll_status(summary["prompt_id"])}

    def cancel(self, request_id):
        folder, record = self._record(request_id)
        summary = self._summary(request_id)
        if summary["prompt_id"] is None:
            raise ComfyError("No prompt receipt; inspect ComfyUI manually")
        with self._client(folder, record) as client:
            client.cancel(summary["prompt_id"])
        return {**summary, "queue_removal_requested": True, "cancellation_confirmed": False}

    def _result(self, folder):
        destination = safe_path(folder, "result")
        receipt = _read(safe_path(destination, "texture.json"))
        for relative, expected in receipt["files"].items():
            if digest(safe_path(destination, relative)) != expected:
                raise ComfyError("Collected texture integrity failed")
        material = load_material(safe_path(destination, "material/material.json"))
        return {"request_id": receipt["request_id"], "profile": receipt["profile"],
                "material_manifest": str(destination / "material/material.json"),
                "generation_receipt": str(destination / "images/generation.json"),
                "texture_receipt": str(destination / "texture.json"), "channels": list(material["channels"]),
                "files": receipt["files"], "model_provenance_verified": False, "distribution_approved": False}

    def collect(self, request_id):
        folder, record = self._record(request_id)
        destination = safe_path(folder, "result")
        if destination.exists():
            return self._result(folder)  # Re-verify bytes; no downloads or overwrites.
        summary = self._summary(request_id)
        if summary["prompt_id"] is None:
            raise ComfyError("No prompt receipt; inspect ComfyUI manually")
        staging = Path(tempfile.mkdtemp(prefix=".collect-", dir=folder))
        try:
            with self._client(folder, record) as client:
                client.collect_assets(summary["prompt_id"], staging / "images")
            generation = _read(staging / "images/generation.json")
            outputs = {(item["node"], item["output_index"]): item for item in generation["outputs"]}
            channels = {}
            for role, binding in record["outputs"].items():
                item = outputs.get(tuple(binding))
                if item is None:
                    raise ComfyError("Generation is missing a declared channel output")
                if digest(safe_path(staging / "images", item["file"])) != item["sha256"]:
                    raise ComfyError("Generated image integrity failed")
                channels[role] = item["file"]
            pack_material(staging / "images", channels, staging / "material")
            files = {p.relative_to(staging).as_posix(): digest(p) for p in sorted(staging.rglob("*")) if p.is_file()}
            write_json(staging / "texture.json", {"schema": "cryptonyan.texture-result/1",
                       "request_id": request_id, "profile": record["request"]["profile"],
                       "template_sha256": record["template_sha256"], "outputs": record["outputs"], "files": files,
                       "references": record.get("references", [])})
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return self._result(folder)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Validate approved ComfyUI profiles offline; no GPU submission")
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args(argv)
    endpoint, profiles = load_catalog(args.catalog)
    print(json.dumps({"valid": True, "endpoint": endpoint, "profiles": list(profiles),
                      "server_availability_checked": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        import sys
        print("Invalid catalog, workflow approval hash, bindings or model declarations.", file=sys.stderr)
        raise SystemExit(2)
