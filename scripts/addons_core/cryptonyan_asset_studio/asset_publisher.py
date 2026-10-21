# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-only export on an isolated copy; source scenes are never saved."""
import math

from . import __version__
from .executors import WorkerFailure
from .publication import MAX_GLB_BYTES, SCHEMA, asset_name, inspect_glb
from .storage import digest, safe_path


def export_static_mesh(mission, snapshot, output, audit):
    import bpy
    from mathutils import Matrix
    from loopcut import glb

    obj = bpy.context.scene.objects.get(mission.target_assets[0])
    row = audit["objects"][0]
    if (obj is None or obj.type != "MESH" or not obj.visible_get() or obj.hide_select or
            obj.instance_type != "NONE" or any(f["code"] == "repair_guard" for f in row["findings"]) or
            not math.isclose(bpy.context.scene.unit_settings.scale_length, 1.0) or
            obj.matrix_world.to_3x3().determinant() <= 1e-8):
        raise WorkerFailure(code="publish_guard")
    # Initial material envelope: one opaque, constant Principled BSDF (or a default).
    # Textures, groups and procedural shaders need an explicit baking milestone.
    if len(obj.material_slots) > 1:
        raise WorkerFailure(code="publish_guard")
    material = obj.material_slots[0].material if obj.material_slots else None
    if material:
        if (material.library or material.override_library or material.animation_data or
                not material.use_nodes or material.node_tree.animation_data):
            raise WorkerFailure(code="publish_guard")
        nodes = list(material.node_tree.nodes)
        shaders = [n for n in nodes if n.type == "BSDF_PRINCIPLED"]
        outputs = [n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
        if (len(nodes) != 2 or len(shaders) != 1 or len(outputs) != 1 or
                any(socket.is_linked for socket in shaders[0].inputs) or
                shaders[0].inputs["Alpha"].default_value != 1 or
                len(material.node_tree.links) != 1 or
                material.node_tree.links[0].from_node != shaders[0] or
                material.node_tree.links[0].to_socket != outputs[0].inputs["Surface"]):
            raise WorkerFailure(code="publish_guard")
        default = bpy.data.materials.new("CryptoNyan_PBR_Default_Check")
        default.use_nodes = True
        try:
            reference = next(n for n in default.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            for actual, baseline in zip(shaders[0].inputs, reference.inputs):
                if actual.name in ("Base Color", "Metallic", "Roughness") or not hasattr(actual, "default_value"):
                    continue
                a, b = actual.default_value, baseline.default_value
                if hasattr(a, "__iter__"):
                    a, b = tuple(a), tuple(b)
                if a != b:
                    raise WorkerFailure(code="publish_guard")
        finally:
            bpy.data.materials.remove(default)

    # Work only in the child snapshot, copying both object and mesh data.
    copied = obj.copy()
    copied.data = obj.data.copy()
    copied.name = asset_name(obj.name)
    bpy.context.scene.collection.objects.link(copied)
    path = safe_path(output, copied.name + ".glb")
    if path.exists() or copied.name != asset_name(obj.name):
        raise WorkerFailure(code="publish_guard")
    try:
        matrix = obj.matrix_world.copy()
        matrix.translation = (0, 0, 0)
        copied.data.transform(matrix)
        copied.matrix_world = Matrix.Identity(4)
        if material is None:
            material = bpy.data.materials.new("M_CryptoNyan_Default")
            material.use_nodes = True
        copied.data.materials.clear()
        copied.data.materials.append(material)
        for polygon in copied.data.polygons:
            polygon.material_index = 0
        bpy.context.view_layer.update()
        points = [tuple(v.co) for v in copied.data.vertices]
        bounds = [[min(v[i] for v in points) for i in range(3)],
                  [max(v[i] for v in points) for i in range(3)]]
        expected = glb._expected([copied])
        glb._export(path, [copied])
        if path.stat().st_size > MAX_GLB_BYTES:
            raise WorkerFailure(code="export_invalid")
        item = {"name": copied.name, "file": path.name, "sha256": digest(path), "bytes": path.stat().st_size,
                "triangles": row["triangles"], "bounds_blender_m": bounds, "material_count": 1}
        try:
            found = inspect_glb(path, item)
            if glb.compare(found, expected) or glb.dropped_nodes([copied]):
                raise ValueError("Export differs from prepared copy")
        except (ValueError, KeyError, IndexError):
            raise WorkerFailure(code="export_invalid") from None
        return {"schema": SCHEMA, "source": {"sha256": digest(snapshot), "object": obj.name},
                "producer": {"studio": __version__, "blender": bpy.app.version_string}, "asset": item,
                "policy": {"format": "glb", "units": "meters", "pivot": "source_object_origin",
                           "transforms": "rotation_scale_baked", "target_engine": "5.8",
                           "collision": "none", "lod": "source_only", "textures": "none"}}
    finally:
        mesh = copied.data
        bpy.data.objects.remove(copied, do_unlink=True)
        bpy.data.meshes.remove(mesh)
