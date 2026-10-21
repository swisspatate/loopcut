# SPDX-License-Identifier: GPL-3.0-or-later
"""Planned runner/PCGEx contract; graph connectivity is not a playability proof."""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class RunnerSegment:
    identity: str
    lane: Literal[-1, 0, 1]
    branch: Literal["upper", "lower", "ground"]
    kind: Literal["run", "jump", "portal", "moving_platform", "three_way_choice"]
    next_segments: tuple[str, ...]
    length_m: float


@dataclass(frozen=True)
class MovementEnvelope:
    speed_m_s: float
    jump_speed_m_s: float
    gravity_m_s2: float
    lane_change_seconds: float
    capsule_radius_m: float


class ProceduralLevelBuilder(Protocol):
    def build(self, seed: int, segments: tuple[RunnerSegment, ...]) -> dict: ...
    def validate_survivability(self, level: dict, movement: MovementEnvelope) -> dict:
        """Must report reachable choices, landing windows, moving-platform phases and failure seeds."""
        ...
