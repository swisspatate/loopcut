# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-only export on an isolated copy; source scenes are never saved."""
import math

from . import __version__
from .executors import WorkerFailure
from .publication import MAX_GLB_BYTES, SCHEMA, PBR_SCHEMA, asset_name, inspect_glb, describe_textures
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
    if len(obj.material_slots) > 1:
        raise WorkerFailure(code="publish_guard")
    material = obj.material_slots[0].material if obj.material_slots else None
    from .blender_materials import validate_material
    try:
        roles = validate_material(obj, material)
    except (ValueError, KeyError):
        raise WorkerFailure(code="publish_guard") from None

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
            textures = describe_textures(path)
            expected_roles = {"metallic_roughness" if r in ("metallic", "roughness") else r for r in roles}
            if {t["role"] for t in textures} != expected_roles:
                raise ValueError("Export dropped or changed a PBR texture binding")
            found = inspect_glb(path, item, textures)
            if glb.compare(found, expected) or glb.dropped_nodes([copied]):
                raise ValueError("Export differs from prepared copy")
        except (ValueError, KeyError, IndexError):
            raise WorkerFailure(code="export_invalid") from None
        return {"schema": PBR_SCHEMA if textures else SCHEMA,
                **({"textures": textures} if textures else {}),
                "source": {"sha256": digest(snapshot), "object": obj.name},
                "producer": {"studio": __version__, "blender": bpy.app.version_string}, "asset": item,
                "policy": {"format": "glb", "units": "meters", "pivot": "source_object_origin",
                           "transforms": "rotation_scale_baked", "target_engine": "5.8",
                           "collision": "none", "lod": "source_only", "textures": "embedded_png" if textures else "none"}}
    finally:
        mesh = copied.data
        bpy.data.objects.remove(copied, do_unlink=True)
        bpy.data.meshes.remove(mesh)
