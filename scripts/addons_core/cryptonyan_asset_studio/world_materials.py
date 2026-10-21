# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit biome/module PBR assignments, portable identities and texture budgets."""
import copy
from pathlib import Path

from .materials import load_material
from .procedural_level_builder import _hash
from .storage import digest, safe_path
from .world_geometry import validate_plan

MAX_TEXTURE_BYTES = 64 * 1024 * 1024
# Blender typically holds four float channels per pixel: at most 256 MiB for
# these decoded image buffers, excluding scene/renderer/temporary overhead.
MAX_TEXTURE_PIXELS = 16 * 1024 * 1024


def plan_materials(recipe, source_root, world):
    validate_plan(world)
    if (not isinstance(recipe, dict) or set(recipe) != {"schema", "bindings"} or
            recipe["schema"] != "cryptonyan.world-materials/1" or
            not isinstance(recipe["bindings"], list) or not 1 <= len(recipe["bindings"]) <= 8):
        raise ValueError("Require 1 to 8 explicit world material bindings")
    required = {(a["biome"], world["modules"][a["module"]]["kit"]) for a in world["actors"]}
    bindings, seen = [], set()
    root = Path(source_root).resolve(strict=True)
    for binding in recipe["bindings"]:
        if not isinstance(binding, dict) or set(binding) != {"biome", "kit", "material"}:
            raise ValueError("Binding requires biome, kit and material")
        if any(not isinstance(binding[k], str) for k in binding):
            raise ValueError("Binding fields must be strings")
        pair = binding["biome"], binding["kit"]
        if pair not in required or pair in seen:
            raise ValueError("Unknown or duplicate biome/module binding")
        safe_path(root, binding["material"])
        seen.add(pair)
        bindings.append(copy.deepcopy(binding))
    if seen != required:
        raise ValueError("Every used biome/module pair requires a material")
    # Reordering equivalent assignments must not change appearance identity.
    normalized = {"schema": recipe["schema"], "bindings": sorted(bindings, key=lambda b: (b["biome"], b["kit"]))}
    inputs, materials = {}, {}
    pixels = 0

    def bind(relative):
        path = safe_path(root, relative)
        if relative not in inputs:
            size = path.stat().st_size
            if not path.is_file() or sum(i["bytes"] for i in inputs.values())+size > MAX_TEXTURE_BYTES:
                raise ValueError("World texture byte budget exceeded")
            inputs[relative] = {"bytes": size, "sha256": digest(path)}
        return path

    for relative in sorted({b["material"] for b in bindings}):
        manifest = bind(relative)
        material = load_material(manifest)
        for channel in material["channels"].values():
            image = (Path(relative).parent / channel["file"]).as_posix()
            bind(image)
            if inputs[image]["sha256"] != channel["sha256"]:
                raise ValueError("World texture changed during planning")
            # Count each decoded image per material. Two distinct manifests may
            # share disk bytes but instantiate separate Blender images.
            pixels += channel["width"]*channel["height"]
            if pixels > MAX_TEXTURE_PIXELS:
                raise ValueError("World decoded texture pixel budget exceeded")
        if digest(manifest) != inputs[relative]["sha256"]:
            raise ValueError("World material changed during planning")
        materials[relative] = material
    result = {"schema": "cryptonyan.world-appearance/1", "world_id": world["world_id"],
              "recipe": normalized, "materials": materials, "inputs": inputs,
              "texture_pixels": pixels, "engine_validated": False}
    return {**result, "appearance_id": _hash(result)}


def validate_appearance(appearance, source_root, world):
    if not isinstance(appearance, dict) or "recipe" not in appearance:
        raise ValueError("Invalid world appearance")
    if appearance != plan_materials(appearance["recipe"], source_root, world):
        raise ValueError("World appearance differs from its bound textures")
    return appearance


def material_for(appearance, world, actor):
    kit = world["modules"][actor["module"]]["kit"]
    return next(b["material"] for b in appearance["recipe"]["bindings"] if b["biome"] == actor["biome"] and b["kit"] == kit)
