# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable, content-addressed static mesh bundles. No Blender or Unreal import required."""
import hashlib
import json
import math
from pathlib import Path
import re

from loopcut import glb
from .schema import integer, keys
from .storage import digest, safe_path, write_json
from .materials import png_info

SCHEMA = "cryptonyan.publication/1"
PBR_SCHEMA = "cryptonyan.publication/2"
MAX_GLB_BYTES = 128 * 1024 * 1024
REVIEW_ROOT = "/Game/CryptoNyan/Review"


def asset_name(name):
    stem = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")[:40] or "Mesh"
    return "SM_" + stem + "_" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]


def package_id(data):
    payload = {k: v for k, v in data.items() if k != "package_id"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()[:32]


def _exact(data, names):
    keys(data, names)
    if set(data) != set(names):
        raise ValueError("Missing publication fields")


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid publication hash")


def _vector(value):
    if not isinstance(value, list) or len(value) != 3 or any(
            type(v) not in (float, int) or not math.isfinite(v) for v in value):
        raise ValueError("Invalid publication bounds")


def validate_manifest(data):
    pbr = data.get("schema") == PBR_SCHEMA
    _exact(data, ("schema", "package_id", "source", "producer", "asset", "quality", "policy") + (("textures",) if pbr else ()))
    if data["schema"] not in (SCHEMA, PBR_SCHEMA) or not isinstance(data["package_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", data["package_id"]):
        raise ValueError("Unsupported publication schema or ID")
    _exact(data["source"], ("sha256", "object"))
    _hash(data["source"]["sha256"])
    name = data["source"]["object"]
    if not isinstance(name, str) or not name or len(name) > 1024 or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid source object name")
    _exact(data["producer"], ("studio", "blender"))
    if any(not isinstance(v, str) or not v or len(v) > 100 for v in data["producer"].values()):
        raise ValueError("Invalid producer version")
    item = data["asset"]
    _exact(item, ("name", "file", "sha256", "bytes", "triangles", "bounds_blender_m", "material_count"))
    if item["name"] != asset_name(name) or item["file"] != item["name"] + ".glb":
        raise ValueError("Invalid asset name or file path")
    _hash(item["sha256"])
    integer(item["bytes"], "bytes", 20, MAX_GLB_BYTES)
    integer(item["triangles"], "triangles", 1, 500000)
    if type(item["material_count"]) is not int or item["material_count"] != 1:
        raise ValueError("Publisher v1 requires one material")
    bounds = item["bounds_blender_m"]
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise ValueError("Invalid bounds")
    for v in bounds:
        _vector(v)
    if any(bounds[0][i] > bounds[1][i] for i in range(3)):
        raise ValueError("Inverted bounds")
    _exact(data["quality"], ("file", "sha256"))
    if data["quality"]["file"] != "quality.json":
        raise ValueError("Invalid report path")
    _hash(data["quality"]["sha256"])
    if data["policy"] != {"format": "glb", "units": "meters", "pivot": "source_object_origin",
                          "transforms": "rotation_scale_baked", "target_engine": "5.8",
                          "collision": "none", "lod": "source_only", "textures": "embedded_png" if pbr else "none"}:
        raise ValueError("Unsupported publication policy")
    if pbr and (not isinstance(data["textures"], list) or not 1 <= len(data["textures"]) <= 3):
        raise ValueError("Invalid embedded texture inventory")
    if data["package_id"] != package_id(data):
        raise ValueError("Publication ID does not match contents")
    return data


def texture_inventory(document, binary):
    """Describe the exact embedded image bytes and glTF PBR channel assignments."""
    images, textures = document.get("images", []), document.get("textures", [])
    if not images and not textures:
        return []
    if not 1 <= len(images) <= 3 or not 1 <= len(textures) <= 3 or len(document.get("materials", [])) != 1:
        raise ValueError("Unsupported texture count")
    material = document["materials"][0]
    if material.get("extensions") or material.get("occlusionTexture") or material.get("emissiveTexture") or material.get("alphaMode", "OPAQUE") != "OPAQUE":
        raise ValueError("Unsupported textured material")
    pbr = material.get("pbrMetallicRoughness", {})
    slots = [("base_color", pbr.get("baseColorTexture"), "sRGB"),
             ("metallic_roughness", pbr.get("metallicRoughnessTexture"), "Non-Color"),
             ("normal", material.get("normalTexture"), "Non-Color")]
    inventory, used_images, used_textures = [], set(), set()
    for role, binding, color_space in slots:
        if binding is None:
            continue
        if binding.get("texCoord", 0) != 0 or binding.get("extensions") or binding.get("scale", 1) != 1:
            raise ValueError("Unsupported texture coordinate or normal scale")
        index = binding["index"]
        if type(index) is not int or not 0 <= index < len(textures):
            raise ValueError("Invalid texture index")
        texture = textures[index]
        image_index = texture.get("source")
        if texture.get("extensions") or type(image_index) is not int or not 0 <= image_index < len(images):
            raise ValueError("Invalid image index")
        image = images[image_index]
        if "uri" in image or image.get("mimeType") != "image/png" or type(image.get("bufferView")) is not int:
            raise ValueError("Require embedded PNG images")
        view = document["bufferViews"][image["bufferView"]]
        start, length = view.get("byteOffset", 0), view["byteLength"]
        if view.get("buffer", 0) != 0 or start < 0 or length < 1 or start + length > len(binary):
            raise ValueError("Invalid image buffer range")
        payload = binary[start:start + length]
        info = png_info(payload)
        inventory.append({"role": role, "image": image_index, "sha256": hashlib.sha256(payload).hexdigest(),
                          "bytes": length, "color_space": color_space, **info})
        used_images.add(image_index)
        used_textures.add(index)
    if used_images != set(range(len(images))) or used_textures != set(range(len(textures))):
        raise ValueError("Unreferenced GLB textures")
    for primitive in document["meshes"][0]["primitives"]:
        if "TEXCOORD_0" not in primitive.get("attributes", {}):
            raise ValueError("Textured mesh has no UV coordinates")
    return inventory


def describe_textures(path):
    return texture_inventory(*glb.parse(path.read_bytes()))


def inspect_glb(path, item, textures=None):
    """Reuse upstream binary checks, with a narrow single-node static mesh envelope."""
    if path.stat().st_size != item["bytes"] or path.stat().st_size > MAX_GLB_BYTES or digest(path) != item["sha256"]:
        raise ValueError("GLB size or hash mismatch")
    document, binary = glb.parse(path.read_bytes())
    if glb.validate(document, binary):
        raise ValueError("GLB failed upstream validation")
    nodes = document.get("nodes", [])
    if (len(nodes) != 1 or nodes[0].get("mesh") != 0 or nodes[0].get("name") != item["name"] or
            any(k in nodes[0] for k in ("children", "skin", "matrix", "translation", "rotation", "scale")) or
            len(document.get("meshes", [])) != 1 or document.get("skins") or document.get("animations") or
            document.get("extensionsRequired") or
            any("uri" in b for b in document.get("buffers", []))):
        raise ValueError("GLB is outside the static publication contract")
    if texture_inventory(document, binary) != (textures or []):
        raise ValueError("GLB textures do not match manifest")
    for primitive in document["meshes"][0].get("primitives", []):
        if primitive.get("mode", 4) != 4 or primitive.get("targets") or primitive.get("material") != 0:
            raise ValueError("Unsupported GLB primitive")
    found = glb.summary(document)
    size = [item["bounds_blender_m"][1][i] - item["bounds_blender_m"][0][i] for i in range(3)]
    if found["materials"] != 1 or glb.compare(found, {item["name"]: {"tris": item["triangles"], "size": size}}):
        raise ValueError("GLB metrics do not match manifest")
    return found


def load_package(manifest_path):
    path = Path(manifest_path)
    if path.is_symlink() or path.name != "manifest.json" or path.stat().st_size > 65536:
        raise ValueError("Invalid manifest path or size")
    data = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
    root = path.parent.resolve()
    report = safe_path(root, data["quality"]["file"])
    if report.stat().st_size > 32 * 1024 * 1024 or digest(report) != data["quality"]["sha256"]:
        raise ValueError("Quality report hash mismatch")
    quality = json.loads(report.read_text(encoding="utf-8"))
    if quality.get("schema") != "cryptonyan.quality-batch/1" or quality.get("passed") is not True:
        raise ValueError("Publication quality gate did not pass")
    rows = quality.get("reports", [])
    if (len(rows) != 1 or rows[0].get("source") != "blender" or rows[0].get("passed") is not True or
            len(rows[0].get("objects", [])) != 1 or rows[0]["objects"][0].get("name") != data["source"]["object"] or
            rows[0]["objects"][0].get("triangles") != data["asset"]["triangles"]):
        raise ValueError("Publication audit does not match asset")
    inspect_glb(safe_path(root, data["asset"]["file"]), data["asset"], data.get("textures"))
    return data


def seal_manifest(data, root):
    data["quality"] = {"file": "quality.json", "sha256": digest(root / "quality.json")}
    data["package_id"] = package_id(data)
    validate_manifest(data)
    path = safe_path(root, "manifest.json")
    if path.exists():
        raise ValueError("Manifest already exists")
    write_json(path, data)
    load_package(path)


def review_destination(package):
    validate_manifest(package)
    return REVIEW_ROOT + "/P_" + package["package_id"]
