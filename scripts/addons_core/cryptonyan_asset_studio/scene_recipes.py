# SPDX-License-Identifier: GPL-3.0-or-later
"""Seeded level dressing and existing-character outfits using saved project assets."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re

from .animation_doctor import exact, name, number, read_json
from .creative_director import identifier, integer, rows, vector, snapshots, write_new
from .game_project import GameProject
from .unreal_material_variants import _hash, _object_path

MECHANISMS = ("gate", "breakable", "wind", "gravity", "ice", "beacon")
ELEMENTS = ("fire", "ice", "earth", "wind", "water", "electric")


class AssetClasses(dict):
    """A package cannot be used as two incompatible source classes."""
    def __setitem__(self, path, kind):
        if path in self and self[path] != kind:
            raise ValueError("Source asset used with incompatible classes")
        super().__setitem__(path, kind)

    def update(self, values):
        for path, kind in values.items():
            self[path] = kind


def optional_rows(value, maximum):
    if value == []:
        return []
    return rows(value, maximum)


def overlap(a, b):
    return all(a[0][i] < b[1][i] and a[1][i] > b[0][i] for i in range(3))


def bounds(position, half, yaw):
    c, s = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
    extent = [half[0]*c+half[1]*s, half[0]*s+half[1]*c, half[2]]
    return [[p-h for p, h in zip(position, extent)], [p+h for p, h in zip(position, extent)]]


def compile_level(value):
    exact(value, ("kind", "target_level", "seed", "theme", "modules", "themes", "clearances", "buildings", "landmarks", "scatter"), ("platforms",))
    integer(value["seed"], 0, 2**32-1)
    modules, themes, refs = value["modules"], value["themes"], AssetClasses()
    if not isinstance(modules, dict) or not 1 <= len(modules) <= 32 or not isinstance(themes, dict) or not 1 <= len(themes) <= 8:
        raise ValueError("Require 1-32 modules and 1-8 themes")
    for key, module in modules.items():
        identifier(key)
        exact(module, ("mesh", "half_m"))
        module["mesh"] = _object_path(module["mesh"])
        module["half_m"] = vector(module["half_m"], .001, 100)
        refs[module["mesh"]] = "StaticMesh"
    for key, theme in themes.items():
        identifier(key)
        exact(theme, ("sun_lux", "fog_density", "weather", "materials", "lights", "sound", "niagara"))
        number(theme["sun_lux"], 0, 120000)
        number(theme["fog_density"], 0, .1)
        if theme["weather"] not in ("clear", "rain", "snow", "ash") or not isinstance(theme["materials"], dict):
            raise ValueError("Invalid atmosphere")
        for module, material in theme["materials"].items():
            if module not in modules:
                raise ValueError("Unknown theme module")
            theme["materials"][module] = _object_path(material)
        for light in optional_rows(theme["lights"], 16):
            exact(light, ("position_m", "color", "intensity", "radius_m"))
            vector(light["position_m"])
            vector(light["color"], 0, 1)
            number(light["intensity"], 0, 100000)
            number(light["radius_m"], .1, 100)
        for field in ("sound", "niagara"):
            if theme[field] is not None:
                theme[field] = _object_path(theme[field])
    if value["theme"] not in themes:
        raise ValueError("Unknown theme")
    theme = themes[value["theme"]]
    refs.update({p: "MaterialInstanceConstant" for p in theme["materials"].values()})
    for field, kind in (("sound", "SoundWave"), ("niagara", "NiagaraSystem")):
        if theme[field]:
            refs[theme[field]] = kind
    clearance = []
    for box in optional_rows(value["clearances"], 64):
        exact(box, ("min_m", "max_m"))
        lo, hi = vector(box["min_m"]), vector(box["max_m"])
        if any(a >= b for a, b in zip(lo, hi)):
            raise ValueError("Invalid clearance volume")
        clearance.append([lo, hi])
    operations, occupied, ids = [], [], set()
    def unique(key):
        identifier(key)
        if key.casefold() in ids:
            raise ValueError("Duplicate placement ID")
        ids.add(key.casefold())
    def place(key, module, position, yaw=0, scale=None, structural=False):
        if module not in modules:
            raise ValueError("Unknown module")
        scale = scale or [1, 1, 1]
        position, scale = vector(position), vector(scale, .001, 1000)
        half = [h*s for h, s in zip(modules[module]["half_m"], scale)]
        box = bounds(position, half, yaw)
        if any(overlap(box, b) for b in clearance) or (not structural and any(overlap(box, b) for b in occupied)):
            return False
        if len(operations) >= 512:
            raise ValueError("Level exceeds 512 placements")
        unique(key)
        operations.append({"kind": "mesh", "id": key, "mesh": modules[module]["mesh"], "position_m": position,
                           "yaw_deg": yaw, "scale": scale, "material": theme["materials"].get(module), "declared_bounds": box})
        occupied.append(box)
        return True
    for building in optional_rows(value["buildings"], 16):
        exact(building, ("id", "origin_m", "grid", "cell_m", "floor", "wall", "roof"))
        key = identifier(building["id"])
        origin, cell = vector(building["origin_m"]), vector(building["cell_m"], 1, 20)
        grid = building["grid"]
        if not isinstance(grid, list) or len(grid) != 3:
            raise ValueError("Building grid needs X/Y/floor counts")
        nx, ny, floors = [integer(n, 1, 6) for n in grid]
        for module in (building["floor"], building["wall"], building["roof"]):
            if module not in modules:
                raise ValueError("Unknown building module")
        for z in range(floors+1):
            for x in range(nx):
                for y in range(ny):
                    module = building["roof"] if z == floors else building["floor"]
                    half = modules[module]["half_m"]
                    pos = [origin[0]+(x+.5)*cell[0], origin[1]+(y+.5)*cell[1], origin[2]+z*cell[2]-half[2]]
                    if not place(f"{key}_F{z}_{x}_{y}", module, pos, scale=[cell[0]/(2*half[0]), cell[1]/(2*half[1]), 1], structural=True):
                        raise ValueError("Building intersects declared clearance")
        module = building["wall"]
        half = modules[module]["half_m"]
        for z in range(floors):
            for side in range(4):
                count = nx if side < 2 else ny
                for i in range(count):
                    if z == 0 and side == 0 and i == nx//2:
                        continue  # Explicit open entrance; stairs remain authored modules.
                    local = [(i+.5)*cell[0], 0 if side == 0 else ny*cell[1]] if side < 2 else [0 if side == 2 else nx*cell[0], (i+.5)*cell[1]]
                    pos = [origin[0]+local[0], origin[1]+local[1], origin[2]+(z+.5)*cell[2]]
                    length = cell[0] if side < 2 else cell[1]
                    if not place(f"{key}_W{z}_{side}_{i}", module, pos, 0 if side < 2 else 90,
                                 [length/(2*half[0]), 1, cell[2]/(2*half[2])], structural=True):
                        raise ValueError("Building intersects declared clearance")
    for landmark in optional_rows(value["landmarks"], 16):
        exact(landmark, ("id", "position_m", "parts", "mechanism"))
        key, origin = identifier(landmark["id"]), vector(landmark["position_m"])
        for index, part in enumerate(rows(landmark["parts"], 32)):
            exact(part, ("module", "offset_m", "yaw_deg", "scale"))
            offset = vector(part["offset_m"])
            yaw = number(part["yaw_deg"], -360, 360)
            if not place(f"{key}_P{index}", part["module"], [a+b for a, b in zip(origin, offset)], yaw, vector(part["scale"], .01, 100), True):
                raise ValueError("Landmark intersects clearance")
        event = landmark["mechanism"]
        if event is not None:
            exact(event, ("kind", "element", "strength", "half_m"))
            if event["kind"] not in MECHANISMS or event["element"] not in ELEMENTS:
                raise ValueError("Unsupported reusable mechanism")
            number(event["strength"], .1, 2000)
            half = vector(event["half_m"], .1, 50)
            if event["kind"] in ("gate", "breakable") and any(overlap(bounds(origin, half, 0), b) for b in clearance):
                raise ValueError("Blocking mechanism occupies a protected route")
            if event["kind"] in ("gate", "breakable"):
                occupied.append(bounds(origin, half, 0))
            unique(key+"_Event")
            operations.append({"kind": "mechanism", "id": key+"_Event", "position_m": origin, **{"mechanism": event}})
    for platform in optional_rows(value.get("platforms", []), 32):
        exact(platform, ("id", "module", "position_m", "amplitude_m", "period_s", "phase_s"))
        key = identifier(platform["id"])
        module = platform["module"]
        if module not in modules:
            raise ValueError("Unknown platform module")
        position = vector(platform["position_m"])
        amplitude = number(platform["amplitude_m"], 0, 3)
        number(platform["period_s"], .1, 20); number(platform["phase_s"], 0, 20)
        if platform["phase_s"] >= platform["period_s"] or module not in theme["materials"]:
            raise ValueError("Platform needs phase below period and an explicit theme material")
        half = list(modules[module]["half_m"]); half[2] += amplitude
        swept = bounds(position, half, 0)
        if any(overlap(swept, box) for box in clearance+occupied):
            raise ValueError("Platform swept volume intersects an occupied or protected volume")
        unique(key); occupied.append(swept)
        operations.append({"kind": "platform", **platform, "mesh": modules[module]["mesh"],
                           "material": theme["materials"].get(module), "declared_bounds": swept})
    for zone in optional_rows(value["scatter"], 32):
        exact(zone, ("id", "min_m", "max_m", "count", "modules", "scale_range"))
        key = identifier(zone["id"])
        lo, hi = vector(zone["min_m"]), vector(zone["max_m"])
        if any(lo[i] >= hi[i] for i in (0, 1)) or lo[2] != hi[2]:
            raise ValueError("Scatter requires a flat declared XY area")
        choices = rows(zone["modules"], 32)
        if any(m not in modules for m in choices):
            raise ValueError("Unknown scatter module")
        count = integer(zone["count"], 1, 256)
        scales = zone["scale_range"]
        if not isinstance(scales, list) or len(scales) != 2 or not .1 <= number(scales[0], .1, 10) <= number(scales[1], .1, 10):
            raise ValueError("Invalid scale range")
        rng = random.Random(int(hashlib.sha256(f"{value['seed']}:{key}".encode()).hexdigest(), 16))
        placed = 0
        for attempt in range(count*100):
            module, scale, yaw = rng.choice(choices), rng.uniform(*scales), rng.uniform(-180, 180)
            pos = [rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1]), lo[2]+modules[module]["half_m"][2]*scale]
            box = bounds(pos, [h*scale for h in modules[module]["half_m"]], yaw)
            if any(box[0][i] < lo[i] or box[1][i] > hi[i] for i in (0, 1)):
                continue
            if place(f"{key}_{placed}", module, pos, yaw, [scale]*3):
                placed += 1
            if placed == count:
                break
        if placed != count:
            raise ValueError("Requested density cannot fit the declared free space")
    if not operations or len(operations)+len(theme["lights"])+3 > 512:
        raise ValueError("Empty or oversized level")
    return operations, refs


def compile_wardrobe(value):
    exact(value, ("kind", "target_level", "body", "skeleton", "animations", "animation", "outfits", "outfit"))
    refs = AssetClasses()
    for field, kind in (("body", "SkeletalMesh"), ("skeleton", "Skeleton")):
        value[field] = _object_path(value[field]); refs[value[field]] = kind
    if not isinstance(value["animations"], dict) or not 1 <= len(value["animations"]) <= 16:
        raise ValueError("Declare 1-16 preview animations")
    for key, path in value["animations"].items():
        identifier(key); value["animations"][key] = _object_path(path)
    if value["animation"] not in value["animations"]:
        raise ValueError("Choose a configured animation")
    refs[value["animations"][value["animation"]]] = "AnimSequence"
    outfits = value["outfits"]
    if not isinstance(outfits, dict) or not 1 <= len(outfits) <= 32 or value["outfit"] not in outfits:
        raise ValueError("Choose one of 1-32 saved outfits")
    def materials(items):
        seen = set()
        for binding in optional_rows(items, 32):
            exact(binding, ("slot", "material"))
            slot = integer(binding["slot"], 0, 31)
            if slot in seen:
                raise ValueError("Duplicate material slot")
            seen.add(slot); binding["material"] = _object_path(binding["material"])
    for key, outfit in outfits.items():
        identifier(key); exact(outfit, ("materials", "accessories", "garments"))
        materials(outfit["materials"])
        seen = set()
        for part in optional_rows(outfit["accessories"], 16):
            exact(part, ("id", "mesh", "socket", "offset_m", "rotation_rpy_deg", "scale"))
            identifier(part["id"]); name(part["socket"])
            part["mesh"] = _object_path(part["mesh"])
            vector(part["offset_m"], -5, 5); vector(part["rotation_rpy_deg"], -360, 360); vector(part["scale"], .01, 10)
            if part["id"].casefold() in seen:
                raise ValueError("Duplicate outfit part")
            seen.add(part["id"].casefold())
        for part in optional_rows(outfit["garments"], 8):
            exact(part, ("id", "mesh", "materials")); identifier(part["id"])
            part["mesh"] = _object_path(part["mesh"]); materials(part["materials"])
            if part["id"].casefold() in seen or part["mesh"] == value["body"]:
                raise ValueError("Duplicate outfit part or body used as clothing")
            seen.add(part["id"].casefold())
    outfit = outfits[value["outfit"]]
    refs.update({b["material"]: "MaterialInstanceConstant" for b in outfit["materials"]})
    for part in outfit["accessories"]:
        refs[part["mesh"]] = "StaticMesh"
    for part in outfit["garments"]:
        refs[part["mesh"]] = "SkeletalMesh"
        refs.update({b["material"]: "MaterialInstanceConstant" for b in part["materials"]})
    return [{"body": value["body"], "animation": value["animations"][value["animation"]], **outfit}], refs


def make_plan(spec, project_root):
    value = copy.deepcopy(spec)
    if not isinstance(value, dict) or value.get("kind") not in ("level", "wardrobe"):
        raise ValueError("Expected level or wardrobe recipe")
    if not isinstance(value.get("target_level"), str) or not re.fullmatch(r"/Game/CryptoNyan/ReviewMaps/[A-Za-z][A-Za-z0-9_]{0,47}", value["target_level"]):
        raise ValueError("Choose an explicit empty review map")
    operations, refs = (compile_level if value["kind"] == "level" else compile_wardrobe)(value)
    project = GameProject(project_root)
    result = {"schema": "cryptonyan.scene-plan/1", "recipe": value, "operations": operations, "source_classes": refs,
              "sources": snapshots(project, refs), "project_root": str(project.root), "project_identity": project._project_identity(),
              "engine_validated": False, "navigation_validated": False}
    return {**result, "identity": _hash(result)}


def load_plan(path):
    result = read_json(path)
    if not isinstance(result, dict) or result.get("schema") != "cryptonyan.scene-plan/1" or result != make_plan(result["recipe"], result["project_root"]):
        raise ValueError("Scene plan or source assets changed")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Prepare level dressing or outfit previews from existing project assets")
    p.add_argument("recipe", type=Path); p.add_argument("--project", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    plan = make_plan(read_json(args.recipe), args.project)
    write_new(args.output, plan, args.project)
    print(json.dumps({"identity": plan["identity"], "placements": len(plan["operations"])}))


if __name__ == "__main__":
    main()
