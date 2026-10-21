# SPDX-License-Identifier: GPL-3.0-or-later
"""Connect audited runner kits at ground-centre sockets; prepare a bounded world plan."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from .procedural_level_builder import _hash, _number
from .runner_kit import read_json, validate_bundle
from .schema import integer
from .storage import safe_path
from .unreal_review import plan_import


def palette(value):
    if not isinstance(value, dict) or set(value) != {"color_linear", "roughness"}:
        raise ValueError("Biome requires linear RGB and roughness")
    rgb = value["color_linear"]
    if not isinstance(rgb, list) or len(rgb) != 3:
        raise ValueError("Biome color requires three channels")
    return {"color_linear": [_number(v, 0, 1) for v in rgb], "roughness": _number(value["roughness"], .05, 1)}


def normalize_world(recipe):
    if not isinstance(recipe, dict) or set(recipe) != {"schema", "seed", "biomes", "zones"} or recipe["schema"] != "cryptonyan.world-recipe/1":
        raise ValueError("Unsupported world recipe")
    integer(recipe["seed"], "seed", 0, 2**32 - 1)
    biomes = recipe["biomes"]
    if not isinstance(biomes, dict) or not 1 <= len(biomes) <= 8:
        raise ValueError("Require 1 to 8 biomes")
    if any(not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", k) for k in biomes):
        raise ValueError("Invalid biome identifier")
    normalized = {k: palette(v) for k, v in biomes.items()}
    zones = recipe["zones"]
    if not isinstance(zones, list) or not 1 <= len(zones) <= 8:
        raise ValueError("Require 1 to 8 zones")
    for zone in zones:
        if not isinstance(zone, dict) or set(zone) != {"kit", "biome", "decorations"} or zone["biome"] not in biomes:
            raise ValueError("Each zone requires a kit, known biome and decoration count")
        integer(zone["decorations"], "decorations", 0, 16)
        if not isinstance(zone["kit"], str):
            raise ValueError("Kit must be a relative path")
    return {**copy.deepcopy(recipe), "biomes": normalized}


def plan_world(recipe, source_root):
    recipe = normalize_world(recipe)
    root = Path(source_root).resolve(strict=True)
    kits, modules, actors, connections, zones = {}, {}, [], [], []
    offset, connector_width, movement = 0.0, None, None
    for index, zone in enumerate(recipe["zones"]):
        relative = zone["kit"]
        if relative not in kits:
            folder = safe_path(root, relative)
            catalog = validate_bundle(folder)
            layout = read_json(safe_path(folder, "layout.json"))
            analysis = read_json(safe_path(folder, "analysis.json"))
            imported = plan_import(safe_path(folder, "publication/manifest.json"))
            if not imported["automatic_apply_supported"]:
                raise ValueError("World modules require the validated constant-material import path")
            imported["source"] = (Path(relative) / "publication" / Path(imported["source"]).name).as_posix()
            identity = f"M{len(kits):02d}"
            kits[relative] = (identity, catalog, layout, analysis)
            modules[identity] = {"kit": relative, "catalog_sha256": _hash(catalog), "import": imported}
        identity, catalog, layout, analysis = kits[relative]
        length, width, thickness = layout["module"]["size_m"]
        if connector_width is not None and width != connector_width:
            raise ValueError("Incompatible connector widths; use matching lane widths")
        if movement is not None and movement != layout["recipe"]["movement"]:
            raise ValueError("Connected kits must use the same movement envelope")
        connector_width, movement = width, layout["recipe"]["movement"]
        last_row = layout["recipe"]["rows"] - 1
        centre_exit = next(p for p in layout["placements"] if p["row"] == last_row and p["lane"] == 0)
        if centre_exit["id"] not in analysis["reachable_goals"]:
            raise ValueError("Kit has no certified static route to its centre exit")
        zone_id = f"Z{index:02d}"
        if index:
            connections.append({"from_zone": f"Z{index-1:02d}", "to_zone": zone_id,
                                "position_cm": [offset * 100, 0, 0], "width_cm": width * 100,
                                "kind": "flush_ground_centre", "opposed_normals": [[1, 0, 0], [-1, 0, 0]]})
        for item in layout["placements"]:
            x, y, z = item["origin_m"]
            motion = item.get("motion", {})
            actors.append({"id": zone_id + "_" + item["id"], "module": identity, "biome": zone["biome"],
                           "kind": "platform", "origin_cm": [(offset+x)*100, -y*100, z*100],
                           "scale": [1.0, 1.0, 1.0], "collision": True,
                           "amplitude_cm": motion.get("amplitude_m", 0) * 100,
                           "period_seconds": motion.get("period_frames", 30) / 30,
                           "phase_seconds": motion.get("phase_frames", 0) / 30})
        span = centre_exit["origin_m"][0] + length
        for number in range(zone["decorations"]):
            draw = hashlib.sha256(f'{recipe["seed"]}:{index}:decor:{number}'.encode("ascii")).digest()
            x = int.from_bytes(draw[:4], "big") / 2**32 * max(0, span - .25)
            side = -1 if draw[4] & 1 else 1
            height = .5 + draw[5] / 255 * 2.5
            # Entire post lies outside all three lanes plus a 1m clear band.
            actors.append({"id": f"{zone_id}_D{number:02d}", "module": identity, "biome": zone["biome"],
                           "kind": "decoration", "origin_cm": [(offset+x)*100, side*(1.5*width+1.125)*100, height*100],
                           "scale": [.25/length, .25/width, height/thickness], "collision": False,
                           "amplitude_cm": 0.0, "period_seconds": 1.0, "phase_seconds": 0.0})
        zones.append({"id": zone_id, "module": identity, "entry_cm": [offset*100, 0, 0],
                      "exit_cm": [(offset+span)*100, 0, 0], "biome": zone["biome"]})
        offset += span
    if len(actors) > 512:
        raise ValueError("World exceeds 512 actors; split the recipe")
    result = {"schema": "cryptonyan.world-plan/1", "recipe": recipe, "modules": modules,
              "zones": zones, "connections": connections, "actors": actors,
              "static_centre_route_passed": True, "engine_validated": False, "dynamics_validated": False,
              "length_cm": offset*100, "decorations_have_collision": False}
    return {**result, "world_id": _hash(result)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Connect validated runner kits into a reproducible world plan")
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    result = plan_world(read_json(args.recipe), args.source)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"world_id": result["world_id"], "actors": len(result["actors"]), "engine_validated": False}))


if __name__ == "__main__":
    main()
