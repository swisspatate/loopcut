# SPDX-License-Identifier: GPL-3.0-or-later
"""Durable, bounded image selections for operator-declared ComfyUI reference slots.

The service owns these receipts. A completed preparation is an immutable snapshot,
not a claim that its sources remain fresh. New preflights/submissions recheck them.
"""
import copy
import hashlib
from pathlib import Path

from .comfyui_adapter import ComfyError, workflow_digest
from .comfy_references import prepare_profile, validate_reference_slots
from .materials import read_png
from .storage import digest, safe_path, write_json

MAX_PREPARATIONS = 256


class ReferencePreparations:
    def __init__(self, service):
        self.service = service
        self.root = safe_path(service.root, "reference-preparations")

    def folder(self, identity):
        from .comfy_profiles import _identifier
        return safe_path(self.root, _identifier(identity))

    def source(self, handle):
        if not isinstance(handle, str) or len(handle) > 1024 or ":" not in handle:
            raise ComfyError("Use an approved asset: or work: PNG handle")
        prefix, relative = handle.split(":", 1)
        root = {"asset": self.service.asset_root, "work": self.service.handle_root}.get(prefix)
        if root is None:
            raise ComfyError("Reference source root is not configured")
        return safe_path(root, relative)

    def input_root(self, profile):
        validate_reference_slots(profile)
        root = Path(profile.get("input_root") or "").resolve(strict=True)
        protected = [self.service.root, self.service.asset_root, self.service.project_root]
        for path in protected:
            if path is not None and (root.is_relative_to(path) or path.is_relative_to(root)):
                raise ComfyError("ComfyUI input must be separate from assets, game and texture receipts")
        return root

    def identity(self, profile):
        return workflow_digest({"endpoint": self.service.endpoint, "profile": profile})

    def snapshot(self, role, handle):
        data, info = read_png(self.source(handle))
        return dict(role=role, handle=handle, sha256=hashlib.sha256(data).hexdigest(),
                    width=info["width"], height=info["height"], bytes=len(data))

    def saved(self, preparation_id):
        from .comfy_profiles import _read
        folder = self.folder(preparation_id)
        if not safe_path(folder, "prepared.json").is_file():
            raise ComfyError("Preparation incomplete or missing; inspect locally, never restage this ID automatically")
        request = _read(safe_path(folder, "request.json"))
        record = _read(safe_path(folder, "prepared.json"))
        if (request.get("schema") != "cryptonyan.reference-selection/1" or
                record.get("schema") != "cryptonyan.reference-preparation/1" or
                request["request"]["preparation_id"] != preparation_id or
                record["preparation_id"] != preparation_id or
                record["profile"] != request["request"]["profile"] or
                record["request_sha256"] != workflow_digest(request["request"]) or
                {s["role"]: s["handle"] for s in record["sources"]} != request["request"]["references"] or
                set(record["files"]) != {"profile/profiles.json", "profile/workflow.json"}):
            raise ComfyError("Reference preparation receipt changed")
        for relative, sha in record["files"].items():
            path = safe_path(folder, relative)
            if path.stat().st_size > 2*1024*1024 or digest(path) != sha:
                raise ComfyError("Prepared profile integrity failed")
        return request["request"], record

    @staticmethod
    def summary(record):
        return {**{key: record[key] for key in ("preparation_id", "profile", "sources", "references")},
                "prepared": True, "source_freshness_validated": False, "network_performed": False,
                "gpu_execution_validated": False, "applied_to_game": False}

    def prepare(self, profile, preparation_id, references):
        from .comfy_profiles import _identifier, _read
        _identifier(profile)
        folder = self.folder(preparation_id)
        if (not isinstance(references, dict) or not 1 <= len(references) <= 3 or
                not set(references) <= {"reference", "uv", "mask"} or
                any(not isinstance(v, str) or len(v) > 1024 for v in references.values())):
            raise ComfyError("Map 1-3 declared reference roles to approved PNG handles")
        request = dict(profile=profile, preparation_id=preparation_id, references=references)
        if folder.exists():
            saved = _read(safe_path(folder, "request.json"))
            if saved.get("request") != request:
                raise ComfyError("Preparation ID already used with different parameters")
            return self.summary(self.saved(preparation_id)[1])
        selected = self.service.profiles.get(profile)
        if selected is None or not selected.get("reference_slots"):
            raise ComfyError("Select a profile with operator-declared reference slots")
        input_root = self.input_root(selected)
        if set(references) != {slot["role"] for slot in selected["reference_slots"]}:
            raise ComfyError("Supply exactly all declared reference roles")
        sources = [self.snapshot(slot["role"], references[slot["role"]]) for slot in selected["reference_slots"]]
        if sum(s["bytes"] for s in sources) > 64*1024*1024:
            raise ComfyError("Reference batch exceeds 64 MiB")
        self.root.mkdir(exist_ok=True, mode=0o700)
        if sum(1 for _ in self.root.iterdir()) >= MAX_PREPARATIONS:
            raise ComfyError("Reference preparation capacity reached")
        folder.mkdir(mode=0o700)
        write_json(folder/"request.json", {"schema": "cryptonyan.reference-selection/1", "request": request})
        specs = [dict(role=s["role"], binding=s["binding"], path=str(self.source(references[s["role"]])))
                 for s in selected["reference_slots"]]
        prepare_profile(selected, self.service.endpoint, specs, input_root, folder/"profile")
        derived = _read(safe_path(folder, "profile/profiles.json"))["profiles"][0]
        for source, ref in zip(sources, derived["reference_inputs"]):
            if source != self.snapshot(source["role"], source["handle"]) or source["sha256"] != ref["sha256"]:
                raise ComfyError("Reference source changed during preparation; inspect incomplete ID locally")
        record = dict(schema="cryptonyan.reference-preparation/1", preparation_id=preparation_id, profile=profile,
                      request_sha256=workflow_digest(request), profile_identity=self.identity(selected),
                      template_sha256=selected["workflow_sha256"], derived_template_sha256=derived["workflow_sha256"],
                      sources=sources, references=derived["reference_inputs"],
                      files={p: digest(safe_path(folder, p)) for p in ("profile/profiles.json", "profile/workflow.json")})
        write_json(folder/"prepared.json", record)
        return self.summary(record)

    def selected(self, preparation_id):
        from .comfy_profiles import load_catalog
        _, record = self.saved(preparation_id)
        approved = self.service.profiles.get(record["profile"])
        if approved is None or not approved.get("reference_slots") or self.identity(approved) != record["profile_identity"]:
            raise ComfyError("Reference preparation differs from the current approved profile")
        input_root = self.input_root(approved)
        for source in record["sources"]:
            if source != self.snapshot(source["role"], source["handle"]):
                raise ComfyError("Reference source changed since preparation")
        endpoint, profiles = load_catalog(self.folder(preparation_id)/"profile/profiles.json")
        selected = profiles[record["profile"]]
        # Verify that the prepared graph changes only operator-declared image literals.
        expected = copy.deepcopy(approved)
        expected.pop("reference_slots")
        for ref in record["references"]:
            expected["template"][ref["binding"][0]]["inputs"][ref["binding"][1]] = ref["file"]
        expected.update(reference_inputs=record["references"], workflow="workflow.json",
                        workflow_sha256=workflow_digest(expected["template"]), input_root=str(input_root))
        if (endpoint != self.service.endpoint or selected != expected or
                selected["workflow_sha256"] != record["derived_template_sha256"] or
                [(s["role"], s["sha256"]) for s in record["sources"]] !=
                [(r["role"], r["sha256"]) for r in record["references"]]):
            raise ComfyError("Prepared reference graph or provenance changed")
        return selected, record

    @staticmethod
    def provenance(record):
        return {key: record[key] for key in ("preparation_id", "profile", "profile_identity", "template_sha256",
                "derived_template_sha256", "sources", "references")}
