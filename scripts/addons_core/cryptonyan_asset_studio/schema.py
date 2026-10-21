# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict, versioned public mission contract; no provider credentials or executable code."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import re
from typing import TypedDict

SCHEMA = "cryptonyan.mission/1"


def now():
    return datetime.now(timezone.utc).isoformat()


class State(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL = {State.CANCELLED, State.SUCCEEDED, State.FAILED}
TRANSITIONS = {
    State.QUEUED: {State.RUNNING, State.CANCELLED},
    State.RUNNING: {State.CANCELLING, State.SUCCEEDED, State.FAILED},
    State.CANCELLING: {State.CANCELLED},
}


class ArtifactRecord(TypedDict):
    path: str
    sha256: str
    bytes: int


class SnapshotRecord(TypedDict):
    path: str
    sha256: str


class TaskRecord(TypedDict):
    schema: str
    id: str
    mission: dict
    revision_of: str | None
    executor: str
    ownership: dict[str, str]
    state: str
    attempts: int
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    snapshots: list[SnapshotRecord]
    artifacts: list[ArtifactRecord]
    quality_passed: bool | None


def transition(old, new):
    if State(new) not in TRANSITIONS.get(State(old), set()):
        raise ValueError(f"Invalid state transition: {old} -> {new}")


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def keys(data, allowed):
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise ValueError("Unknown fields or invalid object")


def strings(value, name, minimum=0, maximum=128):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"Invalid {name} list")
    if any(not isinstance(v, str) or not v or len(v) > 1024 or
           any(ord(c) < 32 for c in v) for v in value):
        raise ValueError(f"Invalid {name} entry")
    if len(set(value)) != len(value):
        raise ValueError(f"Duplicate {name} entries")
    return tuple(value)


@dataclass(frozen=True)
class Constraints:
    timeout_seconds: float = 120.0
    max_attempts: int = 1
    repair_copy: bool = False

    @classmethod
    def parse(cls, data):
        keys(data, cls.__dataclass_fields__)
        result = cls(**data)
        if type(result.timeout_seconds) not in (int, float) or not math.isfinite(result.timeout_seconds) or not 0.05 <= result.timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be finite and in [0.05, 3600]")
        integer(result.max_attempts, "max_attempts", 1, 3)
        if type(result.repair_copy) is not bool:
            raise ValueError("repair_copy must be boolean")
        return result


@dataclass(frozen=True)
class SuccessCriteria:
    max_triangles: int = 100000
    allow_warnings: bool = True

    @classmethod
    def parse(cls, data):
        keys(data, cls.__dataclass_fields__)
        result = cls(**data)
        integer(result.max_triangles, "max_triangles", 0, 10000000)
        if type(result.allow_warnings) is not bool:
            raise ValueError("allow_warnings must be boolean")
        return result


@dataclass(frozen=True)
class Mission:
    inputs: tuple[str, ...]
    target_assets: tuple[str, ...] = ()
    type: str = "asset_doctor"
    constraints: Constraints = field(default_factory=Constraints)
    success_criteria: SuccessCriteria = field(default_factory=SuccessCriteria)
    schema: str = SCHEMA

    @classmethod
    def parse(cls, data):
        keys(data, cls.__dataclass_fields__)
        if data.get("schema", SCHEMA) != SCHEMA or data.get("type", "asset_doctor") != "asset_doctor":
            raise ValueError("Unsupported schema or task type; only asset_doctor is implemented")
        return cls(inputs=strings(data.get("inputs"), "inputs", 1, 32),
                   target_assets=strings(data.get("target_assets", []), "target_assets"),
                   constraints=Constraints.parse(data.get("constraints", {})),
                   success_criteria=SuccessCriteria.parse(data.get("success_criteria", {})))

    def json(self):
        data = asdict(self)
        data["inputs"] = list(self.inputs)
        data["target_assets"] = list(self.target_assets)
        return data


def task_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid task ID")
    return value
