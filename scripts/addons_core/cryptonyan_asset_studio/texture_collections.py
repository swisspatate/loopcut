# SPDX-License-Identifier: GPL-3.0-or-later
"""Durable, explicitly stepped texture collections for existing project assets.

One TextureService owner serializes calls. Plans are immutable; request receipts,
not an in-memory cursor, determine progress. No worker, GPU scheduler or scene edit.
"""
import copy
import hashlib
import re

from .comfy_profiles import _identifier, _read, MAX_REQUESTS
from .comfy_preflight import validate_parameters
from .comfyui_adapter import workflow_digest
from .storage import digest, safe_path, write_json

MAX_COLLECTIONS = 32
MAX_ITEMS = 16
MAX_SOURCE_BYTES = 1024 * 1024 * 1024


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", value):
        raise ValueError("Collection/item IDs need 1-40 lowercase ASCII letters, digits, dash or underscore")
    return value


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError("Collection text is empty, oversized or contains NUL")


def validate_spec(spec):
    if (not isinstance(spec, dict) or set(spec) != {"schema", "collection_id", "profile", "style", "seed", "items"}
            or spec["schema"] != "cryptonyan.texture-collection/1"):
        raise ValueError("Invalid texture collection specification")
    _id(spec["collection_id"])
    _identifier(spec["profile"])
    _text(spec["style"], 1024)
    if type(spec["seed"]) is not int or not 0 <= spec["seed"] < 2**32:
        raise ValueError("Collection seed must be an unsigned 32-bit integer")
    if not isinstance(spec["items"], list) or not 1 <= len(spec["items"]) <= MAX_ITEMS:
        raise ValueError("A collection needs 1-16 explicit items")
    seen = set()
    for item in spec["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "target", "surface", "description"}:
            raise ValueError("Each item needs id, target, surface and description")
        if _id(item["id"]) in seen:
            raise ValueError("Duplicate collection item ID")
        seen.add(item["id"])
        _text(item["target"], 1024)
        _text(item["surface"], 256)
        _text(item["description"], 1024)
    return copy.deepcopy(spec)


def requests_for(spec):
    result = []
    for item in spec["items"]:
        identity = hashlib.sha256((spec["collection_id"] + "/" + item["id"]).encode()).hexdigest()[:32]
        # Item order and collection ID do not change its seed; item ID and base seed do.
        seed = int(hashlib.sha256(f'{spec["seed"]}/{item["id"]}'.encode()).hexdigest()[:8], 16)
        prompt = spec["style"] + "\n\n" + item["description"]
        validate_parameters(prompt, seed)
        result.append({"id": item["id"], "request": {"request_id": "col-" + identity, "target": item["target"],
                       "surface": item["surface"], "profile": spec["profile"], "prompt": prompt, "seed": seed}})
    return result


class TextureCollections:
    def __init__(self, project):
        if project.textures is None:
            raise ValueError("Texture collections require an existing project and configured texture service")
        self.project, self.textures = project, project.textures
        self.root = safe_path(self.textures.root, "collections")

    def _folder(self, identity):
        return safe_path(self.root, "collection-" + _id(identity))

    def _contract(self, profile):
        selected = self.textures.profiles.get(profile)
        if selected is None:
            raise ValueError("Collection profile is unavailable; configure an executable texture profile")
        if workflow_digest(selected["template"]) != selected["workflow_sha256"]:
            raise ValueError("Collection profile template no longer matches its approved hash")
        return {"endpoint": self.textures.endpoint,
                "profile": {k: copy.deepcopy(v) for k, v in selected.items() if k not in {"template", "workflow", "description"}}}

    def _sources(self, requests):
        snapshots, total = {}, 0
        for item in requests:
            target = item["request"]["target"]
            if target not in snapshots:
                # Check aggregate budget before reading/hashing the next asset.
                total += self.project._asset(target)["bytes"]
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("Collection source files exceed the 1 GiB budget")
                snapshots[target] = self.project._snapshot(target)
        return snapshots

    def plan(self, specification):
        spec = validate_spec(specification)
        folder = self._folder(spec["collection_id"])
        if folder.exists():
            plan = self._load(spec["collection_id"])
            if plan["specification"] != spec:
                raise ValueError("Collection ID already used with a different specification")
            return self._planned(plan)  # Recovery does not require the current catalog or unchanged sources.
        items = requests_for(spec)
        contract = self._contract(spec["profile"])
        project_identity = self.project._project_identity()
        snapshots = self._sources(items)
        for item in items:
            item["source"] = snapshots[item["request"]["target"]]
            request_id = item["request"]["request_id"]
            if self.textures._folder(request_id).exists() or self.project._receipt(request_id).exists():
                raise ValueError("A derived request ID is already owned outside this collection")
        if sum(1 for _ in self.textures.requests.iterdir()) + len(items) > MAX_REQUESTS:
            raise ValueError("Insufficient texture workspace capacity for this collection")
        if self.project._project_identity() != project_identity:
            raise ValueError("Project descriptor changed while planning")
        plan = {"schema": "cryptonyan.texture-collection-plan/1", "specification": spec,
                "project_identity": project_identity, "contract": contract, "items": items}
        self.root.mkdir(exist_ok=True)
        if sum(1 for _ in self.root.iterdir()) >= MAX_COLLECTIONS:
            raise ValueError("Collection workspace capacity reached")
        folder.mkdir()  # A crash here leaves an incomplete plan requiring inspection, never silent reuse.
        write_json(safe_path(folder, "plan.json"), {"plan": plan, "sha256": workflow_digest(plan)})
        return self._planned(plan)

    def _planned(self, plan):
        return {"plan_file": str(safe_path(self._folder(plan["specification"]["collection_id"]), "plan.json")),
                "plan_sha256": workflow_digest(plan), "plan": plan, "submission_performed": False,
                "applied_to_game": False, "visual_consistency_verified": False}

    def _load(self, identity):
        record = _read(safe_path(self._folder(identity), "plan.json"))
        plan = record["plan"]
        if record["sha256"] != workflow_digest(plan) or plan["schema"] != "cryptonyan.texture-collection-plan/1":
            raise ValueError("Collection plan integrity failed")
        spec = validate_spec(plan["specification"])
        if spec["collection_id"] != identity or plan["project_identity"] != self.project._project_identity():
            raise ValueError("Collection belongs to another identity, project or changed descriptor")
        if [{k: v for k, v in item.items() if k != "source"} for item in plan["items"]] != requests_for(spec):
            raise ValueError("Collection request derivation mismatch")
        return plan

    def _verify_sources(self, plan):
        if self.project._project_identity() != plan["project_identity"]:
            raise ValueError("Collection project descriptor changed")
        snapshots = self._sources(plan["items"])
        if any(snapshots[item["request"]["target"]] != item["source"] for item in plan["items"]):
            raise ValueError("A collection source changed; inspect existing candidates before continuing")
        if self.project._project_identity() != plan["project_identity"]:
            raise ValueError("Collection project descriptor changed")

    def _intent(self, plan, item):
        folder = self._folder(plan["specification"]["collection_id"])
        path = safe_path(folder, "item-" + item["id"] + ".intent.json")
        value = {"plan_sha256": workflow_digest(plan), "request_id": item["request"]["request_id"]}
        if path.exists() and _read(path) != value:
            raise ValueError("Collection submission intent mismatch")
        return path, value

    def _state(self, plan, item):
        request = item["request"]
        request_id = request["request_id"]
        intent, _ = self._intent(plan, item)
        folder, binding = self.textures._folder(request_id), self.project._receipt(request_id)
        candidate = safe_path(self.project.bindings, request_id + ".candidate.json")
        row = {"id": item["id"], "request_id": request_id, "target": request["target"], "seed": request["seed"]}
        if not intent.exists():
            if folder.exists() or binding.exists() or candidate.exists():
                raise ValueError("Collection request has no owned submission intent")
            return {**row, "state": "planned"}
        if binding.exists():
            owned = _read(binding)
            if owned != {"schema": "cryptonyan.asset-texture-request/1", "request": request,
                         "project_identity": plan["project_identity"], "source": item["source"]}:
                raise ValueError("Collection asset binding mismatch")
        if not folder.exists():
            if candidate.exists():
                raise ValueError("Collection candidate has no request receipt")
            return {**row, "state": "prepared"}
        if not binding.exists():
            raise ValueError("Collection request has no asset binding")
        try:
            _, record = self.textures._record(request_id)
            summary = self.textures._summary(request_id)
        except (ValueError, OSError, KeyError, TypeError):
            return {**row, "state": "incomplete", "manual_inspection_required": True}
        contract = plan["contract"]
        profile = contract["profile"]
        if (record["request"] != {k: v for k, v in request.items() if k not in {"target", "surface"}}
                or record["template_sha256"] != profile["workflow_sha256"] or record["outputs"] != profile["outputs"]
                or record.get("references", []) != profile.get("reference_inputs", [])
                or record["config"]["endpoint"] != contract["endpoint"]
                or record["config"]["models"] != profile["models"]
                or record["config"]["seed_inputs"] != profile["seed_inputs"]):
            raise ValueError("Collection texture receipt mismatch")
        state = "collected" if candidate.is_file() and summary["collected"] else "submitted"
        return {**row, "state": state, "submission": summary["submission"], "prompt_id": summary["prompt_id"]}

    def status(self, collection_id):
        plan = self._load(collection_id)
        rows = [self._state(plan, item) for item in plan["items"]]
        index = safe_path(self._folder(collection_id), "index.json")
        return {"collection_id": collection_id, "plan_sha256": workflow_digest(plan), "items": rows,
                "index_file": str(index) if index.exists() else None, "network_polled": False,
                "artifacts_verified": False, "applied_to_game": False}

    def listing(self):
        result = []
        if self.root.exists():
            folders = sorted(self.root.iterdir())
            if len(folders) > MAX_COLLECTIONS:
                raise ValueError("Collection workspace exceeds capacity")
            for folder in folders:
                identity = folder.name.removeprefix("collection-")
                try:
                    status = self.status(identity)
                    result.append({"collection_id": identity, "items": len(status["items"]),
                                   "collected": sum(i["state"] == "collected" for i in status["items"])})
                except (ValueError, OSError, KeyError, TypeError):
                    result.append({"collection_id": identity[:40], "manual_inspection_required": True})
        return {"collections": result, "capacity": MAX_COLLECTIONS}

    def advance(self, collection_id):
        plan = self._load(collection_id)
        self._verify_sources(plan)
        for item in plan["items"]:
            row = self._state(plan, item)
            if row["state"] == "collected":
                self._candidate(plan, item)  # Verify prior output bytes before extending the collection.
                continue
            if row["state"] == "incomplete":
                return {"action": "manual_inspection_required", "item": row, "submission_performed": False}
            if row["state"] == "submitted":
                status = self.textures.status(row["request_id"])
                return {"action": "collect" if status["status"] == "succeeded" else "wait_or_inspect",
                        "item": row, "status": status, "submission_performed": False}
            if self._contract(plan["specification"]["profile"]) != plan["contract"]:
                raise ValueError("Collection profile or endpoint changed; no new requests may be submitted")
            request = item["request"]
            diagnostic = self.textures.preflight(request["profile"], request["prompt"], request["seed"])
            if diagnostic["status"] != "compatible":
                return {"action": "preflight_blocked", "item": row, "diagnostic": diagnostic, "submission_performed": False}
            self._verify_sources(plan)
            if self._contract(request["profile"]) != plan["contract"]:
                raise ValueError("Collection profile changed during preflight")
            intent, value = self._intent(plan, item)
            if not intent.exists():
                write_json(intent, value)  # Persist before calling any submission layer.
            result = self.project.texture_submit(**request)
            self._verify_sources(plan)
            return {"action": "submitted", "item": self._state(plan, item), "result": result,
                    "submission_performed": True}
        return {"action": "complete", "submission_performed": False, "index_file": self._publish_index(plan)}

    def collect(self, collection_id):
        plan = self._load(collection_id)
        self._verify_sources(plan)
        for item in plan["items"]:
            row = self._state(plan, item)
            if row["state"] == "collected":
                continue
            if row["state"] != "submitted":
                return {"action": "advance_or_inspect", "item": row}
            candidate = self._candidate(plan, item)
            self._verify_sources(plan)
            complete = all(self._state(plan, entry)["state"] == "collected" for entry in plan["items"])
            return {"action": "collected", "item": row["id"], "candidate": candidate,
                    "index_file": self._publish_index(plan) if complete else None}
        return {"action": "complete", "index_file": self._publish_index(plan)}

    def _candidate(self, plan, item):
        request_id = item["request"]["request_id"]
        path = safe_path(self.project.bindings, request_id + ".candidate.json")
        if not path.exists():
            return self.project.texture_collect(request_id)
        result = self.textures._result(self.textures._folder(request_id))
        expected = {"schema": "cryptonyan.asset-texture-candidate/1", "target": item["source"],
                    "surface": item["request"]["surface"], "texture": result, "project_identity": plan["project_identity"],
                    "surface_verified": False, "applied_to_game": False, "requires_local_visual_review": True}
        if _read(path) != expected:
            raise ValueError("Collection candidate integrity failed; existing file is retained")
        return {**expected, "candidate_manifest": str(path)}

    def _publish_index(self, plan):
        entries = []
        for item in plan["items"]:
            if self._state(plan, item)["state"] != "collected":
                raise ValueError("Cannot publish an incomplete collection index")
            candidate = self._candidate(plan, item)
            path = safe_path(self.project.bindings, item["request"]["request_id"] + ".candidate.json")
            entries.append({"id": item["id"], "request_id": item["request"]["request_id"], "source": item["source"],
                            "seed": item["request"]["seed"], "surface": item["request"]["surface"],
                            "candidate": path.relative_to(self.textures.root).as_posix(), "candidate_sha256": digest(path),
                            "material_manifest": candidate["texture"]["material_manifest"]})
        self._verify_sources(plan)
        index = {"schema": "cryptonyan.texture-collection-index/1", "plan_sha256": workflow_digest(plan),
                 "items": entries, "applied_to_game": False, "visual_consistency_verified": False,
                 "model_provenance_verified": False, "distribution_approved": False}
        path = safe_path(self._folder(plan["specification"]["collection_id"]), "index.json")
        if path.exists():
            if _read(path) != index:
                raise ValueError("Collection index integrity failed; existing file is retained")
        else:
            write_json(path, index)
        return str(path)


def main(argv=None):
    import argparse
    import json
    from .comfy_profiles import TextureService
    from .game_project import GameProject
    parser = argparse.ArgumentParser(description="Explicitly stepped ComfyUI collections for existing game assets")
    parser.add_argument("--project", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--workspace", required=True, help="Existing texture workspace, not the parent MCP workspace")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan").add_argument("specification")
    commands.add_parser("list")
    for name in ("status", "advance", "collect"):
        commands.add_parser(name).add_argument("collection_id")
    args = parser.parse_args(argv)
    from pathlib import Path
    project = GameProject(args.project)
    workspace = Path(args.workspace).resolve()
    if workspace.is_relative_to(project.root) or project.root.is_relative_to(workspace):
        raise ValueError("Texture workspace and game project must be separate directories")
    with TextureService(args.catalog, workspace) as textures:
        collections = TextureCollections(GameProject(args.project, textures))
        if args.command == "plan":
            result = collections.plan(_read(Path(args.specification), 65536))
        elif args.command == "list":
            result = collections.listing()
        else:
            result = getattr(collections, args.command)(args.collection_id)
        print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        import sys
        print("Collection operation failed; inspect its plan, owned receipts and local service state.", file=sys.stderr)
        raise SystemExit(2)
