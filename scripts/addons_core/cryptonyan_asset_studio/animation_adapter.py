# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared quadruped convention; arbitrary input-rig adaptation remains a contract.

cat_rig implements a generated weighted blockout and baked GLB clips using this
convention. It does not implement general retargeting or auto-rig imported meshes.
"""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class CatRigConvention:
    topology: Literal["quadruped"] = "quadruped"
    root_bone: str = "root"
    pelvis_bone: str = "pelvis"
    foot_bones: tuple[str, ...] = ("paw_front.L", "paw_front.R", "paw_back.L", "paw_back.R")
    spine_chain: tuple[str, ...] = ("spine.01", "spine.02", "neck", "head")
    tail_chain: tuple[str, ...] = ("tail.01", "tail.02", "tail.03")
    root_motion: bool = False


class AnimationAdapter(Protocol):
    def validate_cat_rig(self, asset: str, convention: CatRigConvention) -> dict: ...
    def export_unreal_animation(self, asset: str, clips: tuple[str, ...], destination: str) -> dict: ...
