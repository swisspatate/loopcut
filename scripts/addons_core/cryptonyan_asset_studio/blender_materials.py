# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, inspectable Principled material envelope; evaluated inside Blender only."""
import json
import math
from pathlib import Path

from .materials import CHANNELS, load_material, png_info
from .storage import digest, safe_path

SOCKETS = {"base_color": "Base Color", "roughness": "Roughness", "metallic": "Metallic", "normal": "Normal"}


def _validate_scalar(image):
    import numpy as np
    from loopcut.texture_tools import _Pixels
    pixels = _Pixels().of(image)
    if (pixels is None or not np.isfinite(pixels).all() or
            not np.allclose(pixels[:, :, 0], pixels[:, :, 1], atol=1e-6, rtol=0) or
            not np.allclose(pixels[:, :, 0], pixels[:, :, 2], atol=1e-6, rtol=0)):
        raise ValueError("Scalar maps must contain greyscale RGB; avoid luminance/red-channel ambiguity")


def validate_material(obj, material):
    import bpy
    if material is None:
        return set()
    if (material.library or material.override_library or material.animation_data or not material.use_nodes or
            material.node_tree.animation_data):
        raise ValueError("Unsupported material ownership or animation")
    nodes, links = list(material.node_tree.nodes), list(material.node_tree.links)
    if any(n.mute for n in nodes):
        raise ValueError("Muted shader nodes are unsupported")
    shaders = [n for n in nodes if n.type == "BSDF_PRINCIPLED"]
    outputs = [n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
    if len(shaders) != 1 or len(outputs) != 1:
        raise ValueError("Require a single Principled surface")
    shader, output = shaders[0], outputs[0]
    used = {shader, output}
    expected_links = {(shader.outputs["BSDF"], output.inputs["Surface"])}
    images, roles, sizes = set(), set(), set()
    default = bpy.data.materials.new("CryptoNyan_PBR_Default_Check")
    default.use_nodes = True
    try:
        reference = next(n for n in default.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for actual, baseline in zip(shader.inputs, reference.inputs):
            if actual.is_linked and actual.name not in SOCKETS.values():
                raise ValueError("Unsupported Principled input")
            if actual.name in ("Base Color", "Metallic", "Roughness") or not hasattr(actual, "default_value"):
                continue
            a, b = actual.default_value, baseline.default_value
            if hasattr(a, "__iter__"):
                a, b = tuple(a), tuple(b)
            if a != b:
                raise ValueError("Unsupported Principled value")
        for role, socket_name in SOCKETS.items():
            socket = shader.inputs[socket_name]
            if not socket.is_linked:
                continue
            source = socket.links[0].from_socket
            expected_links.add((source, socket))
            if role == "normal":
                normal = source.node
                if (normal.type != "NORMAL_MAP" or source != normal.outputs["Normal"] or normal.space != "TANGENT" or
                        normal.uv_map or normal.inputs["Strength"].is_linked or normal.inputs["Strength"].default_value != 1 or
                        not normal.inputs["Color"].is_linked):
                    raise ValueError("Require an OpenGL tangent normal map at strength 1")
                used.add(normal)
                source = normal.inputs["Color"].links[0].from_socket
                expected_links.add((source, normal.inputs["Color"]))
            texture = source.node
            if (texture.type != "TEX_IMAGE" or source != texture.outputs["Color"] or texture.inputs["Vector"].is_linked or
                    texture.interpolation != "Linear" or texture.extension != "REPEAT" or texture.projection != "FLAT"):
                raise ValueError("Require directly connected UV image textures")
            image = texture.image
            if (image is None or image.source != "FILE" or not image.packed_file or image.is_dirty or image.library or
                    image.colorspace_settings.name != CHANNELS[role] or image in images):
                raise ValueError("Require distinct, packed PNG images in the correct colour space")
            info = png_info(bytes(image.packed_file.data))
            if role in ("roughness", "metallic"):
                _validate_scalar(image)
            sizes.add((info["width"], info["height"]))
            images.add(image)
            roles.add(role)
            used.add(texture)
        if set(nodes) != used or {(l.from_socket, l.to_socket) for l in links} != expected_links:
            raise ValueError("Unsupported or unused material nodes/links")
        if images and (len(obj.data.uv_layers) != 1 or not obj.data.uv_layers.active):
            raise ValueError("Textured publishing requires exactly one UV map")
        if len(sizes) > 1 or (images and any(not math.isfinite(v) for loop in obj.data.uv_layers.active.data for v in loop.uv)):
            raise ValueError("Require matching image dimensions and finite UV coordinates")
        return roles
    finally:
        bpy.data.materials.remove(default)


def create_packed_material(bundle, *, name="M_CryptoNyan_PBR"):
    """Create one reusable material from validated bytes; no scene load or save."""
    import bpy
    bundle = Path(bundle)
    material_data = load_material(bundle)
    # Capture validated bytes, then pack from memory; do not depend on live external paths.
    payloads = {role: safe_path(bundle.parent, item["file"]).read_bytes() for role, item in material_data["channels"].items()}
    import hashlib
    if any(hashlib.sha256(payloads[role]).hexdigest() != item["sha256"] for role, item in material_data["channels"].items()):
        raise ValueError("Material changed during preparation")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for role, item in material_data["channels"].items():
        image = bpy.data.images.new("CryptoNyan_" + role, width=item["width"], height=item["height"])
        image.source = "FILE"
        image.filepath = "//" + role + ".png"
        image.pack(data=payloads[role], data_len=len(payloads[role]))
        image.colorspace_settings.name = item["color_space"]
        texture = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = image
        socket = texture.outputs["Color"]
        if role == "normal":
            normal = material.node_tree.nodes.new("ShaderNodeNormalMap")
            material.node_tree.links.new(socket, normal.inputs["Color"])
            socket = normal.outputs["Normal"]
        material.node_tree.links.new(socket, shader.inputs[SOCKETS[role]])
    material["cryptonyan_material_manifest"] = json.dumps(material_data, sort_keys=True)
    return material


def apply_material_copy(source, bundle, target, output):
    """Run in a factory-started child Blender; create a new .blend, never save source."""
    import bpy
    source, bundle, output = Path(source), Path(bundle), Path(output)
    if source.is_symlink() or output.exists() or output.is_symlink() or output.suffix.lower() != ".blend":
        raise ValueError("Require a source file and a new .blend destination")
    source = source.resolve(strict=True)
    output = output.resolve()
    before = digest(source)
    bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
    obj = bpy.context.scene.objects.get(target)
    if obj is None or obj.type != "MESH" or obj.library or obj.override_library or len(obj.data.uv_layers) != 1:
        raise ValueError("Target must be a local mesh with one UV map")
    obj.data = obj.data.copy()
    material = create_packed_material(bundle)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    validate_material(obj, material)
    if digest(source) != before:
        raise ValueError("Source changed during preparation")
    # Exclusive reservation prevents accidental overwrite, including source aliases.
    with output.open("xb"):
        pass
    # Keep the reserved output on failure for diagnosis; never remove a possibly written scene.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False, copy=True)
    if digest(source) != before:
        raise ValueError("Source changed during preparation")
    return {"source_sha256": before, "output_sha256": digest(output), "object": target}
