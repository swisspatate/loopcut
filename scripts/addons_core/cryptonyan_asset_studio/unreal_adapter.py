# SPDX-License-Identifier: GPL-3.0-or-later
"""Planned UE 5.8 editor bridge. No Unreal API compatibility has been established."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImportPlan:
    source_path: str
    source_sha256: str
    destination: str  # New /Game/CryptoNyan/Review/... package; never overwrite existing assets.
    asset_name: str
    material_slots: tuple[str, ...]
    lod_paths: tuple[str, ...]
    collision_policy: str
    sockets: tuple[str, ...]
    source_units: str = "meters"
    target_units: str = "centimeters"
    target_engine: str = "5.8"


class UnrealAdapter(Protocol):
    def plan_import(self, plan: ImportPlan) -> dict: ...
    def import_to_review_folder(self, plan: ImportPlan) -> str: ...
    def validate_in_editor(self, asset_path: str) -> dict: ...
