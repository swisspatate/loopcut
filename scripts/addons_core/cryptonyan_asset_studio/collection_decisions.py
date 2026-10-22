# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable editorial feedback on verified collection galleries, without adoption."""
import json

from .collection_review import CollectionReview
from .comfy_profiles import _read
from .comfyui_adapter import workflow_digest
from .storage import digest, safe_path, write_json
from .texture_collections import _id

MAX_DECISIONS = 128
RECORD_LIMIT = 256*1024
SOURCES = ("agent_recommendation", "user_reported")
CHOICES = ("keep", "revise", "discard")


def validate_feedback(value):
    if not isinstance(value, dict) or set(value) != {"source", "supersedes", "items"}:
        raise ValueError("Feedback requires source, supersedes and items only")
    if value["source"] not in SOURCES:
        raise ValueError("Feedback source must distinguish agent recommendation from reported user choice")
    if value["supersedes"] is not None: _id(value["supersedes"])
    if not isinstance(value["items"], list) or not 1 <= len(value["items"]) <= 16:
        raise ValueError("Feedback requires 1-16 selected items")
    seen = set()
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) != {"item_id", "choice", "notes"}:
            raise ValueError("Feedback items require item_id, choice and notes only")
        identity = _id(item["item_id"])
        if identity in seen or item["choice"] not in CHOICES:
            raise ValueError("Feedback item IDs must be unique and choices keep, revise or discard")
        if not isinstance(item["notes"], str) or len(item["notes"]) > 1024:
            raise ValueError("Feedback notes must be text up to 1024 characters")
        seen.add(identity)
    return value


class CollectionDecisions:
    def __init__(self, collections):
        self.reviews = CollectionReview(collections)
        self.root = safe_path(collections.textures.root, "collection-decisions")

    def folder(self, review_id):
        return safe_path(self.root, "review-"+_id(review_id))

    def _context(self, collection_id, review_id):
        _id(collection_id); _id(review_id)
        folder, record, _ = self.reviews.verified(collection_id, review_id)
        return record["capture"], digest(safe_path(folder, "review.json"))

    def _record(self, request, capture, review_sha):
        feedback = validate_feedback(request["feedback"])
        selected = {item["id"]: item for item in capture["items"]}
        pins = []
        for entry in feedback["items"]:
            item = selected.get(entry["item_id"])
            if item is None or item["state"] != "collected":
                raise ValueError("Feedback requires items collected in this exact gallery snapshot")
            pins.append({**{key: item[key] for key in ("id", "request_id", "target", "surface", "origin")},
                         "channels": item["inspection"]["channels"]})
        record = dict(schema="cryptonyan.collection-decision/1", request=request,
                    request_sha256=workflow_digest(request), review_sha256=review_sha,
                    plan_sha256=capture["plan_sha256"], selections=pins,
                    human_approval_verified=False, visual_quality_validated=False,
                    adoption_authorized=False, applied_to_game=False, network_performed=False)
        # write_json may translate newlines on Windows. Bound the larger encoding
        # before reserving an ID, rather than publishing an unreadable receipt.
        if len((json.dumps(record, indent=2, allow_nan=False)+"\n").replace("\n", "\r\n").encode("utf-8")) > RECORD_LIMIT:
            raise ValueError("Feedback receipt exceeds its byte limit")
        return record

    def _records(self, collection_id, review_id, capture, review_sha):
        folder = self.folder(review_id); records = {}
        paths = list(folder.iterdir()) if folder.exists() else []
        if len(paths) > MAX_DECISIONS: raise ValueError("Review feedback capacity exceeded")
        for path in sorted(paths):
            safe_path(folder, path.name)
            identity = _id(path.name.removeprefix("decision-"))
            if path.name != "decision-"+identity or not path.is_dir():
                raise ValueError("Unexpected review feedback entry")
            files = list(path.iterdir())
            if {p.name for p in files} != {"request.json", "decision.json"}:
                raise ValueError("Feedback incomplete or changed; inspect locally, never overwrite or resume")
            request = _read(safe_path(path, "request.json"), RECORD_LIMIT)
            record = _read(safe_path(path, "decision.json"), RECORD_LIMIT)
            if (not isinstance(request, dict) or set(request) != {"collection_id", "review_id", "decision_id", "feedback"}
                    or request["collection_id"] != collection_id or request["review_id"] != review_id
                    or request["decision_id"] != identity or record != self._record(request, capture, review_sha)):
                raise ValueError("Feedback identity, gallery, origin or content changed")
            records[identity] = record
        replaced = set()
        for identity, record in records.items():
            feedback = record["request"]["feedback"]; prior = feedback["supersedes"]
            if prior is not None:
                old = records.get(prior)
                if (prior == identity or old is None or prior in replaced or
                        old["request"]["feedback"]["source"] != feedback["source"] or
                        {i["item_id"] for i in old["request"]["feedback"]["items"]} !=
                        {i["item_id"] for i in feedback["items"]}):
                    raise ValueError("Feedback replacement must name one matching predecessor without forks")
                replaced.add(prior)
        for identity in records:
            visited = set(); current = identity
            while current is not None:
                if current in visited: raise ValueError("Feedback replacement cycle refused")
                visited.add(current); current = records[current]["request"]["feedback"]["supersedes"]
        return records, replaced

    def _summary(self, record, replaced):
        request = record["request"]
        return dict(decision_id=request["decision_id"], source=request["feedback"]["source"],
                    supersedes=request["feedback"]["supersedes"], superseded=request["decision_id"] in replaced,
                    items=[{key: i[key] for key in ("item_id", "choice")} for i in request["feedback"]["items"]],
                    decision_sha256=workflow_digest(record))

    def _unchanged(self, collection_id, review_id, context, records):
        if (self._context(collection_id, review_id) != context or
                self._records(collection_id, review_id, *context)[0] != records):
            raise ValueError("Gallery or feedback changed during read")

    def listing(self, collection_id, review_id):
        context = self._context(collection_id, review_id)
        records, replaced = self._records(collection_id, review_id, *context)
        self._unchanged(collection_id, review_id, context, records)
        return dict(collection_id=collection_id, review_id=review_id,
                    decisions=[self._summary(r, replaced) for r in records.values()],
                    target_freshness_validated=True, human_approval_verified=False,
                    adoption_authorized=False, network_performed=False, applied_to_game=False,
                    selection_policy="Explicit replacements only; independent records may conflict; no automatic adoption")

    def read(self, collection_id, review_id, decision_id):
        _id(decision_id); context = self._context(collection_id, review_id)
        records, replaced = self._records(collection_id, review_id, *context)
        if decision_id not in records: raise ValueError("Feedback decision ID not found")
        result = dict(record=records[decision_id], **self._summary(records[decision_id], replaced),
                      target_freshness_validated=True)
        self._unchanged(collection_id, review_id, context, records)
        return result

    def create(self, collection_id, review_id, decision_id, feedback):
        _id(decision_id); validate_feedback(feedback)
        request = dict(collection_id=collection_id, review_id=review_id, decision_id=decision_id, feedback=feedback)
        context = self._context(collection_id, review_id)
        records, replaced = self._records(collection_id, review_id, *context)
        if decision_id in records:
            if records[decision_id]["request"] != request:
                raise ValueError("Feedback decision ID already belongs to different arguments")
            return self.read(collection_id, review_id, decision_id)
        if len(records) >= MAX_DECISIONS: raise ValueError("Review feedback capacity reached")
        prior = feedback["supersedes"]
        if prior is not None:
            old = records.get(prior)
            if (old is None or prior in replaced or old["request"]["feedback"]["source"] != feedback["source"] or
                    {i["item_id"] for i in old["request"]["feedback"]["items"]} != {i["item_id"] for i in feedback["items"]}):
                raise ValueError("Replacement requires an active predecessor with the same source and item IDs")
        record = self._record(request, *context)
        folder = self.folder(review_id)
        destination = safe_path(folder, "decision-"+decision_id)
        self.root.mkdir(exist_ok=True, mode=0o700); folder.mkdir(exist_ok=True, mode=0o700)
        destination.mkdir(mode=0o700)
        write_json(destination/"request.json", request)
        if self._context(collection_id, review_id) != context:
            raise ValueError("Gallery changed during feedback creation; inspect the incomplete decision locally")
        write_json(destination/"decision.json", record)
        return self.read(collection_id, review_id, decision_id)
