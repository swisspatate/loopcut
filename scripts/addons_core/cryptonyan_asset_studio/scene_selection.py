# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Blender selection snapshots and bounded, verified MCP access."""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

from .animation_doctor import exact, number, read_json
from .creative_director import integer
from .image_workshop import identity
from .materials import read_png
from .reference_board import identifier, text
from .schema import now
from .storage import safe_path, write_json

SCHEMA = "cryptonyan.scene-selection/1"
MAX_JSON = 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


def _bounded(value, depth=0):
    if depth > 12:
        raise ValueError("Selection metadata too deep")
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("Too many metadata fields")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("Invalid metadata key")
            _bounded(child, depth+1)
    elif isinstance(value, list):
        if len(value) > 512:
            raise ValueError("Too many metadata items")
        for child in value:
            _bounded(child, depth+1)
    elif isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("Metadata text too long")
    elif type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("Invalid metadata number")
    elif value is not None and type(value) is not bool:
        raise ValueError("Unsupported metadata value")


def validate_facts(value):
    exact(value, ("schema", "blender", "source", "scene", "active", "objects"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported selection facts")
    text(value["blender"], 128, empty=False)
    exact(value["source"], ("file_name", "saved", "dirty"))
    if value["source"]["file_name"] is not None:
        text(value["source"]["file_name"], 512, empty=False)
    if any(type(value["source"][key]) is not bool for key in ("saved", "dirty")):
        raise ValueError("Invalid scene source flags")
    exact(value["scene"], ("name", "frame", "subframe", "fps", "unit_scale_m", "coordinate_policy"))
    text(value["scene"]["name"], 512, empty=False)
    integer(value["scene"]["frame"], -1048574, 1048574)
    number(value["scene"]["subframe"], 0, 1)
    number(value["scene"]["fps"], .001, 100000)
    number(value["scene"]["unit_scale_m"], 1e-9, 100000)
    text(value["scene"]["coordinate_policy"], 256, empty=False)
    if not isinstance(value["objects"], list) or not 1 <= len(value["objects"]) <= 32:
        raise ValueError("Select one to 32 objects")
    names = []
    for obj in value["objects"]:
        exact(obj, ("summary", "world_matrix", "uv_maps", "materials", "rig", "animation"))
        if not isinstance(obj["summary"], dict):
            raise ValueError("Invalid object summary")
        text(obj["summary"].get("name"), 512, empty=False)
        text(obj["summary"].get("type"), 64, empty=False)
        names.append(obj["summary"]["name"])
        matrix = obj["world_matrix"]
        if not isinstance(matrix, list) or len(matrix) != 4 or any(not isinstance(row, list) or len(row) != 4 for row in matrix):
            raise ValueError("Expected world matrix 4x4")
        if not isinstance(obj["uv_maps"], list) or len(obj["uv_maps"]) > 8:
            raise ValueError("Too many UV maps")
        if not isinstance(obj["materials"], list) or len(obj["materials"]) > 16:
            raise ValueError("Too many material slots")
    if len(set(names)) != len(names) or (value["active"] is not None and value["active"] not in names):
        raise ValueError("Invalid active object or duplicate selection")
    _bounded(value)
    if len(json.dumps(value, allow_nan=False).encode()) > MAX_JSON:
        raise ValueError("Selection facts exceed one MiB")
    return copy.deepcopy(value)


def blender_facts(context=None):
    """Main thread only. Reuse Loopcut summaries and legacy/slotted action inspection."""
    import bpy
    from loopcut.tools import object_summary
    from loopcut.scene_context import _fcurves
    context = context or bpy.context
    selected = sorted(context.selected_objects, key=lambda obj: obj.name)
    if context.mode != "OBJECT" or not 1 <= len(selected) <= 32:
        raise ValueError("Use Object mode and select one to 32 objects")
    result = []
    context.view_layer.update()
    for obj in selected:
        if len(obj.material_slots) > 16 or len(obj.modifiers) > 32:
            raise ValueError("Selection exceeds slot/modifier limits")
        uv = [layer.name for layer in obj.data.uv_layers] if obj.type == "MESH" else []
        if len(uv) > 8:
            raise ValueError("Selection exceeds UV limit")
        materials = []
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            item = {"slot": index, "name": material.name if material else None, "node_types": [], "images": []}
            if material and material.use_nodes and material.node_tree:
                nodes = material.node_tree.nodes
                if len(nodes) > 256:
                    raise ValueError("Material exceeds 256 nodes")
                item["node_types"] = sorted({node.bl_idname for node in nodes})
                for node in nodes:
                    image = getattr(node, "image", None)
                    if image is not None:
                        if len(item["images"]) >= 32:
                            raise ValueError("Material exceeds image summary limit")
                        item["images"].append({"name": image.name, "size": list(image.size),
                                               "color_space": image.colorspace_settings.name,
                                               "packed": bool(image.packed_file)})
            materials.append(item)
        rig = obj if obj.type == "ARMATURE" else obj.find_armature() if obj.type == "MESH" else None
        rig_info = None
        if rig:
            if len(rig.data.bones) > 512:
                raise ValueError("Rig exceeds 512 bone summary limit")
            rig_info = {"name": rig.name, "bones": [bone.name for bone in rig.data.bones],
                        "pose_position": rig.data.pose_position}
        curves = _fcurves(obj)
        if len(curves) > 16384:
            raise ValueError("Animation exceeds channel summary limit")
        animation = {"action": obj.animation_data.action.name if obj.animation_data and obj.animation_data.action else None,
                     "channel_count": len(curves), "channels": sorted({curve.data_path for curve in curves})[:64],
                     "channels_truncated": len({curve.data_path for curve in curves}) > 64}
        result.append({"summary": object_summary(obj), "world_matrix": [list(row) for row in obj.matrix_world],
                       "uv_maps": uv, "materials": materials, "rig": rig_info, "animation": animation})
    scene = context.scene
    active = context.view_layer.objects.active
    return validate_facts({"schema": SCHEMA, "blender": bpy.app.version_string,
        "source": {"file_name": Path(bpy.data.filepath).name if bpy.data.filepath else None,
                   "saved": bool(bpy.data.filepath), "dirty": bool(bpy.data.is_dirty)},
        "scene": {"name": scene.name, "frame": scene.frame_current, "subframe": scene.frame_subframe,
                  "fps": scene.render.fps / scene.render.fps_base, "unit_scale_m": scene.unit_settings.scale_length,
                  "coordinate_policy": "Blender axes and units; multiply coordinates by unit_scale_m for metres"},
        "active": active.name if active and active in selected else None, "objects": result})


def publish(library, snapshot_id, facts, image=None, image_kind="provided_png", image_note=""):
    identifier(snapshot_id)
    facts = validate_facts(facts)
    if image_kind not in ("provided_png", "loopcut_viewport"):
        raise ValueError("Unknown selection image kind")
    text(image_note, 4096)
    image_data = image_info = None
    if image is not None:
        path = Path(image)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_IMAGE:
            raise ValueError("Expected bounded regular PNG")
        image_data, size = read_png(path)
        image_info = {"file": "view.png", "sha256": hashlib.sha256(image_data).hexdigest(),
                      "bytes": len(image_data), **size, "kind": image_kind, "note": image_note}
    library = Path(library).resolve()
    namespace = safe_path(library, "scene-contexts")
    if (namespace / "board.json").exists():
        raise ValueError("scene-contexts namespace is occupied by a reference board")
    output = safe_path(namespace, snapshot_id)
    output.mkdir(parents=True, exist_ok=False)
    try:
        value = {"schema": "cryptonyan.selection-snapshot/1", "id": snapshot_id, "captured_at": now(),
                 "facts": facts, "image": image_info, "live_scene_control": False}
        value["identity"] = identity(value)
        if image_data is not None:
            (output / "view.png").write_bytes(image_data)
        write_json(output / "context.json", value)
        return load(output)
    except BaseException:
        shutil.rmtree(output)
        raise


def capture(library, snapshot_id, *, viewport=False, context=None):
    facts = blender_facts(context)
    image, note = None, ""
    if viewport:
        import bpy
        from loopcut.tools import capture_viewport, ToolError
        if bpy.app.background:
            raise ValueError("Viewport capture requires Blender with a graphical display")
        try:
            shot = capture_viewport(focus=[o["summary"]["name"] for o in facts["objects"]], angle="user", style="material")
        except (ToolError, RuntimeError) as exc:
            raise ValueError("Loopcut viewport capture unavailable; check the 3D view and GPU context") from exc
        if not shot.ok or shot.image_path is None:
            raise ValueError("Loopcut viewport capture did not return an image")
        image, note = shot.image_path, shot.text[:4096]
        after = blender_facts(context)
        facts["source"]["dirty"] = after["source"]["dirty"]
        if after != facts:
            raise ValueError("Selection changed during viewport capture")
        facts = after
    return publish(library, snapshot_id, facts, image, "loopcut_viewport", note)


def load(folder):
    folder = Path(folder)
    path = safe_path(folder, "context.json")
    if path.stat().st_size > MAX_JSON:
        raise ValueError("Selection snapshot exceeds one MiB")
    value = read_json(path)
    exact(value, ("schema", "id", "captured_at", "facts", "image", "live_scene_control", "identity"))
    if (value["schema"] != "cryptonyan.selection-snapshot/1" or value["live_scene_control"] is not False or
            identity({key: item for key, item in value.items() if key != "identity"}) != value["identity"]):
        raise ValueError("Selection snapshot identity mismatch")
    identifier(value["id"]); text(value["captured_at"], 64, empty=False)
    validate_facts(value["facts"])
    image = value["image"]
    if image is not None:
        exact(image, ("file", "sha256", "bytes", "width", "height", "kind", "note"))
        if image["file"] != "view.png" or image["kind"] not in ("provided_png", "loopcut_viewport"):
            raise ValueError("Invalid selection image path or kind")
        text(image["note"], 4096)
        integer(image["bytes"], 1, MAX_IMAGE)
        path = safe_path(folder, image["file"])
        if path.stat().st_size > MAX_IMAGE:
            raise ValueError("Selection image exceeds eight MiB")
        payload, size = read_png(path)
        if (len(payload) != image["bytes"] or hashlib.sha256(payload).hexdigest() != image["sha256"] or
                size != {key: image[key] for key in ("width", "height")}):
            raise ValueError("Selection image changed")
    return value


class SelectionService:
    def __init__(self, library):
        self.root = safe_path(library, "scene-contexts")

    def _folder(self, snapshot_id):
        return safe_path(self.root, identifier(snapshot_id))

    def list(self):
        if not self.root.exists():
            return {"snapshots": []}
        result = []
        for folder in sorted(self.root.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not (folder / "context.json").is_file():
                continue
            if len(result) >= 64:
                raise ValueError("Selection library exceeds 64 snapshots")
            value = self.read(folder.name)
            result.append({"snapshot_id": folder.name, "captured_at": value["captured_at"], "identity": value["identity"],
                           "selected": [obj["summary"]["name"] for obj in value["facts"]["objects"]], "has_image": value["image"] is not None})
        return {"snapshots": result}

    def read(self, snapshot_id):
        value = load(self._folder(snapshot_id))
        if value["id"] != snapshot_id:
            raise ValueError("Selection snapshot ID mismatch")
        return value

    def image(self, snapshot_id):
        value = self.read(snapshot_id)
        if value["image"] is None or value["image"]["bytes"] > 2 * 1024 * 1024:
            raise ValueError("Snapshot image unavailable or exceeds MCP 2 MiB limit")
        payload, _ = read_png(safe_path(self._folder(snapshot_id), "view.png"))
        if hashlib.sha256(payload).hexdigest() != value["image"]["sha256"]:
            raise ValueError("Selection image changed")
        return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(payload).decode("ascii")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check"); check.add_argument("folder", type=Path)
    listing = sub.add_parser("list"); listing.add_argument("library", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(load(args.folder) if args.command == "check" else SelectionService(args.library).list(), indent=2))


if __name__ == "__main__": main()
