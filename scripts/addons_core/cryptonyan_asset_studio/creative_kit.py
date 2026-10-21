# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded creative kit recipes and isolated Blender builds, without source scenes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import time
import zlib

from .executors import BlenderExecutor, ExecutionContext, run_process
from .materials import load_material
from .runner_kit import read_json
from .storage import digest, safe_path, write_json
from .world_materials import MAX_TEXTURE_BYTES, MAX_TEXTURE_PIXELS

ELEMENTS = {"fire": (1, .12, .01), "ice": (.1, .65, 1), "earth": (.4, .2, .06),
            "wind": (.6, 1, .8), "water": (.02, .3, .8), "electric": (.7, .15, 1)}
PALETTES = {"volcanic": (.2, .06, .025), "ice": (.2, .55, .7),
            "forest": (.15, .3, .08), "neon": (.18, .04, .35)}
LIGHTS = {"day": {"sun_energy": 3, "sun_angle": 45, "world_strength": .35},
          "sunset": {"sun_energy": 1.5, "sun_angle": 12, "world_strength": .15},
          "night": {"sun_energy": .15, "sun_angle": 35, "world_strength": .04}}
CLIPS = {"idle": 61, "run": 25, "jump": 31, "land": 13, "dash": 13, "brake": 19}


def recipe(data):
    defaults = {"schema": "cryptonyan.creative-kit/1", "seed": 42, "biome": "volcanic",
                "bays": 3, "floors": 2, "terrain_grid": 65, "terrain_size_m": 64,
                "mountain_height_m": 12, "lighting": "sunset", "weather": "ash", "liquid": "lava"}
    if not isinstance(data, dict) or not set(data) <= defaults.keys():
        raise ValueError("Unknown creative recipe fields")
    result = {**defaults, **data}
    if result["schema"] != defaults["schema"]:
        raise ValueError("Unsupported creative recipe")
    for key, low, high in (("seed", 0, 2**32-1), ("bays", 2, 6), ("floors", 1, 4)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError("Invalid creative integer parameter")
    for key, low, high in (("terrain_size_m", 32, 256), ("mountain_height_m", 1, 64)):
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError("Invalid terrain dimensions")
    for key, choices in (("biome", PALETTES), ("lighting", LIGHTS),
                         ("weather", ("clear", "rain", "snow", "ash")), ("liquid", ("water", "lava"))):
        if not isinstance(result[key], str) or result[key] not in choices:
            raise ValueError("Unknown creative preset")
    if type(result["terrain_grid"]) is not int or result["terrain_grid"] not in (33, 65, 129):
        raise ValueError("Terrain grid must be 33, 65 or 129")
    return result


def terrain_height(x, y, spec):
    """Deterministic ridges with a flat central plaza, metres; no external noise lib."""
    phase = spec["seed"] % 997 / 997 * math.tau
    distance = math.hypot(x, y)
    plaza = max(12, spec["bays"]*2.25)
    apron = min(1, max(0, (distance-plaza)/12))
    ridge = (abs(math.sin(x*.13+phase)*math.cos(y*.11-phase)) +
             .3*abs(math.sin((x+y)*.31+phase))) / 1.3
    return spec["mountain_height_m"] * ridge * apron * apron


def modules():
    # Boxes are center/dimensions in metres; positive dimensions, front at y=0.
    box = lambda center, size: {"center": center, "size": size}
    return {
        "floor": [box([1.5, 1.5, -.1], [3, 3, .2])],
        "wall": [box([1.5, 0, 1.5], [3, .2, 3])],
        "door": [box([.45, 0, 1.5], [.9, .2, 3]), box([2.55, 0, 1.5], [.9, .2, 3]),
                 box([1.5, 0, 2.65], [1.2, .2, .7])],
        "window": [box([.35, 0, 1.5], [.7, .2, 3]), box([2.65, 0, 1.5], [.7, .2, 3]),
                   box([1.5, 0, .5], [1.6, .2, 1]), box([1.5, 0, 2.65], [1.6, .2, .7])],
        "roof": [box([1.5, 1.5, .1], [3, 3, .2])],
        "pillar": [box([0, 0, 1.5], [.3, .3, 3])],
        "bridge": [box([1.5, 0, -.1], [3, 1.5, .2]),
                   box([1.5, -.8, .5], [3, .1, 1]), box([1.5, .8, .5], [3, .1, 1])],
        "stairs": [box([(i+.5)*.3, .75, (i+1)*.15], [.3, 1.5, (i+1)*.3]) for i in range(10)]}


def plan(data):
    spec = recipe(data)
    actors = []
    def place(module, x, y, z, angle=0):
        actors.append({"id": f"A{len(actors):04d}", "module": module, "location_m": [x, y, z], "yaw_degrees": angle})
    bays, floors = spec["bays"], spec["floors"]
    for floor in range(floors):
        z = floor*3
        for x in range(bays):
            for y in range(bays):
                place("floor", x*3, y*3, z)
            place("door" if x in (bays//2-1, bays//2) else "window", x*3, 0, z)
            place("window", x*3, bays*3, z)
            place("window", 0, x*3, z, 90)
            place("window", bays*3, x*3, z, 90)
        # Each flight rises exactly one storey to a small balcony, outside the facade.
        place("stairs", bays//2*3-3 if floor % 2 == 0 else bays//2*3,
              -1.5 if floor % 2 == 0 else 0, z, 0 if floor % 2 == 0 else 180)
        place("bridge", bays//2*3 if floor % 2 == 0 else bays//2*3-6, -.75, z+3)
    for x in range(bays):
        for y in range(bays):
            place("roof", x*3, y*3, floors*3)
    for actor in actors:
        actor["location_m"][0] -= bays*1.5
        actor["location_m"][1] -= bays*1.5
    result = {"schema": "cryptonyan.creative-plan/1", "recipe": spec, "modules": modules(), "actors": actors,
              "sockets": {name: {"entry_m": [0, 0, 0], "exit_m": [3, 0, 3 if name == "stairs" else 0]}
                          for name in ("floor", "roof", "bridge", "stairs")},
              "lighting": LIGHTS[spec["lighting"]], "elements": ELEMENTS,
              "clips": {name: {"start": 1, "end": end, "fps": 30, "root_motion": False,
                               "loop": name in ("idle", "run")} for name, end in CLIPS.items()},
              "engine_validated": False, "navigation_validated": False}
    result = json.loads(json.dumps(result))  # Stable JSON types and no shared mutable preset dictionaries.
    result["kit_id"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def sprite_atlas(color, tile=32):
    """4x4 RGBA radial burst flipbook, 16 ordered frames; no learned model."""
    rows = []
    for y in range(tile*4):
        row = bytearray([0])
        for x in range(tile*4):
            frame = (y//tile)*4+x//tile
            phase = frame/15
            radius = math.hypot((x%tile+.5)/tile*2-1, (y%tile+.5)/tile*2-1)
            ring = math.exp(-((radius-(.12+.65*phase))/.12)**2)*(1-phase)**.5
            row.extend([*(round(v*255) for v in color), round(255*ring)])
        rows.append(row)
    def chunk(tag, data):
        return struct.pack(">I", len(data))+tag+data+struct.pack(">I", zlib.crc32(tag+data))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack(">IIBBBBB", tile*4, tile*4, 8, 6, 0, 0, 0))+chunk(b"IDAT", zlib.compress(b"".join(rows)))+chunk(b"IEND", b"")


def validate_cat_glb(path):
    from loopcut import glb
    from .publication import MAX_GLB_BYTES
    if path.stat().st_size > MAX_GLB_BYTES:
        raise ValueError("Animated cat GLB exceeds export budget")
    document, binary = glb.parse(path.read_bytes())
    if glb.validate(document, binary):
        raise ValueError("Animated cat failed Loopcut GLB structural checks")
    if (len(document.get("skins", [])) != 1 or
            len(document.get("animations", [])) != len(CLIPS) or
            {a.get("name") for a in document["animations"]} != {"CN_"+name for name in CLIPS}):
        raise ValueError("Animated cat must contain one skin and all six clips")


def validate_bundle(root):
    root = Path(root).resolve(strict=True)
    expected = plan(read_json(safe_path(root, "plan.json"))["recipe"])
    if read_json(safe_path(root, "plan.json")) != expected:
        raise ValueError("Creative plan changed")
    catalog = read_json(safe_path(root, "creative.json"))
    required = {"plan.json", "environment.blend", "architecture.blend", "cat.blend", "cat.glb", "worker-report.json",
                "height.raw", "height.json", *["fx/"+e+".png" for e in ELEMENTS]}
    if safe_path(root, "material/material.json").exists():
        mat = load_material(safe_path(root, "material/material.json"))
        required |= {"material/material.json", *["material/"+c["file"] for c in mat["channels"].values()]}
    if (set(catalog) != {"schema", "kit_id", "files", "engine_validated"} or
            catalog["schema"] != "cryptonyan.creative-bundle/1" or catalog["kit_id"] != expected["kit_id"]
            or catalog["engine_validated"] is not False or required != set(catalog["files"])):
        raise ValueError("Invalid creative bundle")
    for name, item in catalog["files"].items():
        path = safe_path(root, name)
        if set(item) != {"bytes", "sha256"} or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Creative artifact integrity failed")
    validate_cat_glb(safe_path(root, "cat.glb"))
    return catalog


def build(data, destination, *, blender=None, material=None, timeout_seconds=180):
    if type(timeout_seconds) not in (float, int) or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid creative build timeout")
    result = plan(data)
    destination = Path(destination).resolve()
    executor = BlenderExecutor(blender) if blender is not None else None
    source_material = load_material(material) if material is not None else None
    if source_material:
        pixels = sum(c["width"]*c["height"] for c in source_material["channels"].values())
        total = sum(safe_path(Path(material).parent,c["file"]).stat().st_size for c in source_material["channels"].values())
        if pixels > MAX_TEXTURE_PIXELS or total > MAX_TEXTURE_BYTES:
            raise ValueError("Creative material exceeds the shared preview texture budget")
    if material is not None and destination.is_relative_to(Path(material).resolve().parent):
        raise ValueError("Destination must be outside source material")
    destination.mkdir(exist_ok=False)
    write_json(destination / "plan.json", result)
    if executor is None:
        return {"kit_id": result["kit_id"], "built": False, "engine_validated": False}
    if source_material:
        (destination / "material").mkdir()
        for name in ["material.json"]+[c["file"] for c in source_material["channels"].values()]:
            shutil.copyfile(safe_path(Path(material).parent, name), destination / "material" / name)
        if load_material(destination / "material/material.json") != source_material:
            raise ValueError("Material changed during snapshot")
    (destination / "fx").mkdir()
    for element, color in ELEMENTS.items():
        (destination / "fx" / (element+".png")).write_bytes(sprite_atlas(color))
    spec = result["recipe"]
    grid, size, height = spec["terrain_grid"], spec["terrain_size_m"], spec["mountain_height_m"]
    heights = [terrain_height((x/(grid-1)-.5)*size, (y/(grid-1)-.5)*size, spec) for y in range(grid) for x in range(grid)]
    (destination / "height.raw").write_bytes(struct.pack("<"+"H"*len(heights), *(round(h/height*65535) for h in heights)))
    write_json(destination / "height.json", {"width": grid, "height": grid, "format": "uint16_little_endian",
               "min_m": 0, "max_m": height, "size_m": size, "preview_offset_m": -.22,
               "unreal_landscape_import_validated": False})
    with tempfile.TemporaryDirectory(prefix=".creative-", dir=destination) as temp:
        runtime = Path(temp)
        request = runtime / "request.json"
        write_json(request, {"bundle": str(destination), "plan_sha256": digest(destination / "plan.json")})
        context = ExecutionContext(runtime, runtime, (), threading.Event(), time.monotonic()+timeout_seconds)
        command = executor.command(request)
        command[command.index("--python")+1] = str(Path(__file__).with_name("creative_worker.py"))
        run_process(command, context)
    if read_json(destination / "plan.json") != result:
        raise ValueError("Creative plan changed during build")
    files = {p.relative_to(destination).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p)}
             for p in destination.rglob("*") if p.is_file()}
    write_json(destination / "creative.json", {"schema": "cryptonyan.creative-bundle/1", "kit_id": result["kit_id"],
               "files": files, "engine_validated": False})
    try:
        validate_bundle(destination)
    except Exception:
        (destination / "creative.json").unlink()
        raise
    return {"kit_id": result["kit_id"], "built": True, "engine_validated": False, "directory": str(destination)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build reusable architecture, terrain, FX and an animated quadruped prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = commands.add_parser(name)
        command.add_argument("recipe", type=Path)
        command.add_argument("--destination", type=Path, required=True)
        if name == "build":
            command.add_argument("--blender", type=Path, required=True)
            command.add_argument("--material", type=Path)
            command.add_argument("--timeout", type=float, default=180)
    commands.add_parser("check").add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    value = validate_bundle(args.bundle) if args.command == "check" else build(
        read_json(args.recipe), args.destination, blender=getattr(args, "blender", None),
        material=getattr(args, "material", None), timeout_seconds=getattr(args, "timeout", 180))
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
