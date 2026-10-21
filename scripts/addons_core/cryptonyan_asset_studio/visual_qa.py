# SPDX-License-Identifier: GPL-3.0-or-later
"""Future adapter to Loopcut inspection.py/jobs.py. Never fabricate aesthetic scores."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class CaptureSpec:
    scene_sha256: str
    cameras: tuple[str, ...]
    frames: tuple[int, ...]
    purpose: Literal["geometry", "materials", "final_lighting"]
    seed: int
    engine: str
    resolution: tuple[int, int]
    samples: int
    color_management: str


class VisualQA(Protocol):
    def capture(self, scene: str, spec: CaptureSpec, destination: str) -> dict:
        """Return image hashes, Blender version and actual settings; refuse stale scene hashes."""
        ...

    def compare(self, before: dict, after: dict) -> dict:
        """Report comparable capture conditions and measured differences, not aesthetic pass/fail."""
        ...
