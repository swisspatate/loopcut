# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit masked PBR variants, frozen sources and portable flat material output."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from .animation_doctor import exact, number, read_json
from .creative_director import integer
from .image_workshop import identity
from .materials import CHANNELS, load_material, pack_material, read_png
from .png_pixels import decode, encode, MAX_PIXELS
from .publication import _hash
from .reference_board import identifier, _separate
from .storage import digest, safe_path, write_json

SCHEMA = "cryptonyan.material-layers/1"
MAX_LAYERS = 8
MAX_BYTES = 128 * 1024 * 1024
MAX_WORK = 16 * 1024 * 1024


def _binding(value):
    exact(value, ("file", "sha256"))
    safe_path(Path.cwd(), value["file"]); _hash(value["sha256"])


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "id", "base", "layers"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported material layer recipe")
    identifier(value["id"]); _binding(value["base"])
    if not isinstance(value["layers"], list) or not 1 <= len(value["layers"]) <= MAX_LAYERS:
        raise ValueError("Declare one to eight material layers")
    ids = set()
    for layer in value["layers"]:
        exact(layer, ("id", "material", "mask", "opacity", "channels", "blend"))
        identifier(layer["id"]); _binding(layer["material"]); _binding(layer["mask"])
        if layer["id"] in ids or layer["blend"] not in ("mix", "multiply"):
            raise ValueError("Duplicate layer or unsupported blend")
        ids.add(layer["id"]); number(layer["opacity"], 0, 1)
        channels = layer["channels"]
        if (not isinstance(channels, list) or not 1 <= len(channels) <= 4 or
                any(not isinstance(c, str) or c not in CHANNELS for c in channels) or len(set(channels)) != len(channels)):
            raise ValueError("Declare distinct supported PBR channels")
        if "normal" in channels and layer["blend"] != "mix":
            raise ValueError("Normals support normalized mix only")
    return value


def _material(path, expected):
    if digest(path) != expected:
        raise ValueError("Material manifest differs from pinned hash")
    data = load_material(path)
    files = {path.name: path.read_bytes()}
    if hashlib.sha256(files[path.name]).hexdigest() != expected:
        raise ValueError("Material changed during capture")
    for role, item in data["channels"].items():
        if item["width"] * item["height"] > MAX_PIXELS:
            raise ValueError("Layers currently support at most one megapixel")
        payload, _ = read_png(safe_path(path.parent, item["file"]))
        if hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError("Material changed during capture")
        files[item["file"]] = payload
    return data, files


def _capture(spec, root, frozen=False):
    materials, masks, files, sizes = {}, {}, {}, set()
    bindings = [("base", spec["base"])] + [("layer-"+str(i), l["material"]) for i, l in enumerate(spec["layers"])]
    for key, binding in bindings:
        relative = "inputs/"+key+"/material.json" if frozen else binding["file"]
        path = safe_path(root, relative)
        data, payloads = _material(path, binding["sha256"])
        materials[key] = {"file": "inputs/"+key+"/material.json", "sha256": binding["sha256"], "material": data}
        # Source manifest may have an arbitrary name; frozen manifests are canonicalized by filename only.
        files["inputs/"+key+"/material.json"] = payloads.pop(path.name)
        files.update({"inputs/"+key+"/"+filename: payload for filename, payload in payloads.items()})
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("Layer sources exceed byte budget")
        sizes.update((c["width"], c["height"]) for c in data["channels"].values())
    for i, layer in enumerate(spec["layers"]):
        key, relative = "layer-"+str(i), "inputs/mask-"+str(i)+".png"
        path = safe_path(root, relative if frozen else layer["mask"]["file"])
        payload, size = read_png(path)
        if hashlib.sha256(payload).hexdigest() != layer["mask"]["sha256"]:
            raise ValueError("Mask differs from pinned hash")
        masks[key] = {"file": relative, "sha256": layer["mask"]["sha256"], **size}
        files[relative] = payload; sizes.add((size["width"], size["height"]))
        if sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError("Layer sources exceed byte budget")
        if not set(layer["channels"]) <= (materials["base"]["material"]["channels"].keys() & materials[key]["material"]["channels"].keys()):
            raise ValueError("Each blended channel must exist in both base and layer")
    if len(sizes) != 1:
        raise ValueError("All maps and masks must share dimensions; no implicit resampling")
    width, height = next(iter(sizes))
    work = width * height * (len(materials["base"]["material"]["channels"]) + sum(len(l["channels"]) for l in spec["layers"]))
    if width * height > MAX_PIXELS or work > MAX_WORK or sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("Layer pixel work or source byte budget exceeded")
    plan = {"schema": "cryptonyan.material-layer-bundle/1", "recipe": spec,
            "materials": materials, "masks": masks, "width": width, "height": height,
            "files": {name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)} for name, payload in files.items()}}
    plan["identity"] = identity(plan)
    return plan, files


def prepare(recipe, source_root, output):
    spec = specification(recipe)
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    _separate(source_root, output)
    plan, files = _capture(spec, source_root)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for filename, payload in files.items():
            path = safe_path(output, filename); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        write_json(output / "plan.json", plan)
        if load_bundle(output) != plan:
            raise ValueError("Layer inputs changed during preparation")
        return plan
    except BaseException:
        shutil.rmtree(output)
        raise


def load_bundle(folder):
    folder = Path(folder)
    path = safe_path(folder, "plan.json")
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Layer plan exceeds 1 MiB")
    value = read_json(path)
    exact(value, ("schema", "recipe", "materials", "masks", "width", "height", "files", "identity"))
    if value["schema"] != "cryptonyan.material-layer-bundle/1":
        raise ValueError("Unsupported layer bundle")
    expected, _ = _capture(specification(value["recipe"]), folder, frozen=True)
    if value != expected:
        raise ValueError("Layer bundle identity or files changed")
    return value


def _pixels(payload, role):
    size, rgba = decode(payload)
    for i in range(0, len(rgba), 4):
        r, g, b, a = rgba[i:i+4]
        if a != 255:
            raise ValueError("Layer maps and masks require opaque alpha")
        if role in ("roughness", "metallic", "mask") and not r == g == b:
            raise ValueError("Scalar maps and masks must be greyscale RGB")
        if role == "normal" and (b < 128 or sum((v/127.5-1)**2 for v in (r,g,b)) < .01):
            raise ValueError("Require nondegenerate upper-hemisphere OpenGL tangent normals")
    return size, rgba


def _linear(v):
    v /= 255
    return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4


def _byte(v, srgb=False):
    v = max(0, min(1, v))
    if srgb: v = 12.92*v if v <= .0031308 else 1.055*v**(1/2.4)-.055
    return max(0, min(255, round(v*255)))


def _normal(rgb):
    xyz = [v/127.5-1 for v in rgb]
    length = math.sqrt(sum(v*v for v in xyz))
    return [v/length for v in xyz]


def _blend(base, overlay, mask, role, opacity, mode):
    output = bytearray(len(base)//4*3)
    for pixel, i in enumerate(range(0, len(base), 4)):
        weight = mask[i]/255 * opacity
        a, b = base[i:i+3], overlay[i:i+3]
        # Exact endpoints preserve the declared source bytes, including normal-map quantization.
        if weight == 0: rgb = a
        elif weight == 1 and mode == "mix": rgb = b
        elif role == "normal":
            a, b = _normal(a), _normal(b)
            xyz = [(1-weight)*x+weight*y for x,y in zip(a,b)]
            length = math.sqrt(sum(v*v for v in xyz))
            if length < 1e-6: raise ValueError("Degenerate mixed normal")
            rgb = [_byte(.5+.5*v/length) for v in xyz]
        else:
            a = [_linear(v) if role == "base_color" else v/255 for v in a]
            b = [_linear(v) if role == "base_color" else v/255 for v in b]
            if mode == "multiply": b = [x*y for x,y in zip(a,b)]
            rgb = [_byte((1-weight)*x+weight*y, role == "base_color") for x,y in zip(a,b)]
        output[pixel*3:pixel*3+3] = bytes(rgb)
    return output


def compose(bundle, output):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    _separate(bundle, output)
    plan = load_bundle(bundle)
    # Capture the same verified bytes before computation; no live image paths during blending.
    verified, files = _capture(plan["recipe"], bundle, frozen=True)
    if verified != plan: raise ValueError("Inputs changed during capture")
    rasters = {}
    for key, item in plan["materials"].items():
        rasters[key] = {role: _pixels(files["inputs/"+key+"/"+c["file"]], role)[1]
                        for role,c in item["material"]["channels"].items()}
    masks = {key: _pixels(files[m["file"]], "mask")[1] for key,m in plan["masks"].items()}
    result = {role: bytes(v for i,v in enumerate(rgba) if i%4 != 3) for role,rgba in rasters["base"].items()}
    # Keep intermediates as 8-bit maps, matching the published raster algorithm contract.
    for index, layer in enumerate(plan["recipe"]["layers"]):
        key = "layer-"+str(index)
        for role in layer["channels"]:
            current = bytearray()
            for i in range(0, len(result[role]), 3): current.extend(result[role][i:i+3]+b"\xff")
            result[role] = _blend(current, rasters[key][role], masks[key], role, layer["opacity"], layer["blend"])
    if output.exists() or output.is_symlink(): raise FileExistsError("Choose a new material destination")
    with tempfile.TemporaryDirectory(prefix=".layer-output-", dir=output.parent) as temp:
        source = Path(temp)
        changed = {role for layer in plan["recipe"]["layers"] for role in layer["channels"]}
        for role,pixels in result.items():
            payload = encode(plan["width"], plan["height"], pixels) if role in changed else files["inputs/base/"+role+".png"]
            (source / (role+".png")).write_bytes(payload)
        material = pack_material(source, {role: role+".png" for role in result}, output)
    receipt = {"schema": "cryptonyan.material-composition/1", "algorithm": "masked-pbr-8bit/1",
               "plan_identity": plan["identity"], "plan": plan, "material": material,
               "normal_blend": "normalized_linear_mix", "visual_quality_validated": False, "engine_validated": False}
    write_json(output / "layers.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("recipe", type=Path)
    prep.add_argument("--source-root", type=Path, required=True); prep.add_argument("--output", type=Path, required=True)
    for command in ("check", "compose"):
        p = sub.add_parser(command); p.add_argument("bundle", type=Path)
        if command == "compose": p.add_argument("--output", type=Path, required=True)
    a = parser.parse_args(argv)
    result = prepare(read_json(a.recipe), a.source_root, a.output) if a.command == "prepare" else compose(a.bundle, a.output) if a.command == "compose" else load_bundle(a.bundle)
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
