# SPDX-License-Identifier: GPL-3.0-or-later
"""Planned ComfyUI contract; no HTTP implementation or workflow/model downloads."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class GeneratedAsset:
    path: str
    sha256: str
    workflow_sha256: str
    model_sha256: tuple[str, ...]
    model_licenses: tuple[str, ...]  # Required provenance; unknown licenses block distribution.
    attribution: str


class ComfyUIAdapter(Protocol):
    """Workflow allowlist, explicit endpoint/auth, timeout and cancellation required before implementation."""
    def submit_workflow(self, workflow: dict, *, seed: int, timeout_seconds: float) -> str: ...
    def poll_status(self, identity: str) -> Literal["queued", "running", "succeeded", "failed", "cancelled"]: ...
    def cancel(self, identity: str) -> None: ...
    def collect_assets(self, identity: str, destination: str) -> tuple[GeneratedAsset, ...]: ...
