# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender fixture and copy-preservation assertions; never touches user scenes."""
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "addons_core"))
from cryptonyan_asset_studio.asset_doctor import audit_blender


def signature(obj):
    return (obj.name, tuple(tuple(v.co) for v in obj.data.vertices),
            tuple(tuple(row) for row in obj.matrix_world), obj.data.name)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    mode, path = args
    if mode == "create":
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        cube.name = "Bad Name"
        cube.scale = (2, 1, 1)
        bpy.ops.mesh.primitive_cube_add(location=(4, 0, 0))
        guarded = bpy.context.object
        guarded.name = "Guarded"
        guarded.modifiers.new("Keep subdivision", "SUBSURF")
        bpy.ops.mesh.primitive_cube_add(location=(8, 0, 0))
        shaped = bpy.context.object
        shaped.name = "Shaped"
        shaped.shape_key_add(name="Basis")
        shaped.shape_key_add(name="Smile")
        bpy.ops.object.armature_add(location=(12, 0, 0))
        bpy.context.object.name = "CatRig"
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(path).resolve()), check_existing=False)
    elif mode == "create_publish":
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        mesh = bpy.data.meshes.new("AsymmetricMesh")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 2, 0), (0, 0, 3)], [],
                         [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)])
        obj = bpy.data.objects.new("Platform", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = (17, -8, 3)
        from math import pi
        obj.rotation_euler.z = pi / 2
        obj.scale = (2, 1, 1)
        material = bpy.data.materials.new("M_Platform")
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.2, 0.7, 0.3, 1)
        bsdf.inputs["Metallic"].default_value = 0.2
        bsdf.inputs["Roughness"].default_value = 0.3
        mesh.materials.append(material)
        for name in ("Negative", "Procedural"):
            other = obj.copy()
            other.data = obj.data.copy()
            other.name = name
            bpy.context.scene.collection.objects.link(other)
            if name == "Negative":
                other.scale.x = -1
            else:
                other.data.materials[0] = material.copy()
                other.data.materials[0].node_tree.nodes.new("ShaderNodeTexNoise")
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(path).resolve()), check_existing=False)
    elif mode == "verify_export":
        from math import isclose
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        assert len(meshes) == 1
        obj = meshes[0]
        obj.data.calc_loop_triangles()
        assert len(obj.data.loop_triangles) == 4
        actual = {tuple(round(v, 4) for v in obj.matrix_world @ vertex.co) for vertex in obj.data.vertices}
        assert actual == {(0, 0, 0), (0, 2, 0), (-2, 0, 0), (0, 0, 3)}, actual
        bsdf = next(n for n in obj.data.materials[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        assert isclose(bsdf.inputs["Metallic"].default_value, 0.2, abs_tol=1e-6)
        assert isclose(bsdf.inputs["Roughness"].default_value, 0.3, abs_tol=1e-6)
    elif mode == "create_pbr_guards":
        bpy.ops.wm.open_mainfile(filepath=str(Path(path).resolve()), use_scripts=False)
        original = bpy.data.objects["Bad Name"]
        for name in ("WrongColorSpace", "ExternalImage", "MultipleUVs", "MappedTexture", "ColoredScalar", "MutedNode"):
            obj = original.copy()
            obj.data = original.data.copy()
            obj.name = name
            bpy.context.scene.collection.objects.link(obj)
            material = original.data.materials[0].copy()
            obj.data.materials[0] = material
            texture = next(n for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image.colorspace_settings.name == "sRGB")
            texture.image = texture.image.copy()
            if name == "WrongColorSpace":
                texture.image.colorspace_settings.name = "Non-Color"
            elif name == "ExternalImage":
                texture.image.unpack(method="REMOVE")
            elif name == "MultipleUVs":
                obj.data.uv_layers.new(name="UnsupportedSecondUV")
            elif name == "ColoredScalar":
                shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                roughness = shader.inputs["Roughness"].links[0].from_node
                roughness.image = texture.image.copy()
                roughness.image.colorspace_settings.name = "Non-Color"
            elif name == "MutedNode":
                texture.mute = True
            else:
                coordinates = material.node_tree.nodes.new("ShaderNodeTexCoord")
                material.node_tree.links.new(coordinates.outputs["Generated"], texture.inputs["Vector"])
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(path).resolve()), check_existing=False)
    elif mode == "verify_pbr":
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
        meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        assert len(meshes) == 1
        material = meshes[0].data.materials[0]
        shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for name in ("Base Color", "Roughness", "Metallic", "Normal"):
            assert shader.inputs[name].is_linked, name
        images = [n.image for n in material.node_tree.nodes if n.type == "TEX_IMAGE"]
        assert len(images) == 3
        assert sorted(i.colorspace_settings.name for i in images) == ["Non-Color", "Non-Color", "sRGB"]
        assert all(tuple(i.size) == (2, 2) for i in images)
        # glTF packs roughness into G and metallic into B; normal stays OpenGL +Y.
        data_pixels = [tuple(i.pixels[:3]) for i in images if i.colorspace_settings.name == "Non-Color"]
        assert any(abs(p[1] - 160 / 255) < 0.01 and abs(p[2] - 40 / 255) < 0.01 for p in data_pixels), data_pixels
        assert any(abs(p[0] - 128 / 255) < 0.01 and abs(p[1] - 128 / 255) < 0.01 and p[2] > 0.99 for p in data_pixels), data_pixels
    elif mode == "verify":
        bpy.ops.wm.open_mainfile(filepath=str(Path(path).resolve()), use_scripts=False)
        cube = bpy.data.objects["Bad Name"]
        before = signature(cube)
        result = audit_blender()
        assert result["dry_run"] and result["repairs"] == []
        assert signature(cube) == before
        row = next(o for o in result["objects"] if o["name"] == "Bad Name")
        assert row["vertices"] == 8 and row["faces"] == 6 and row["triangles"] == 12
        assert row["bounds_world"] == [[-2, -1, -1], [2, 1, 1]]
        assert isinstance(row["loopcut"]["uv_audit"], dict)
        fixed = audit_blender(repair_copy=True)
        assert len(fixed["repairs"]) == 1, fixed["repairs"]
        assert signature(cube) == before
        duplicate = bpy.data.objects[fixed["repairs"][0]["copy"]]
        assert duplicate.data != cube.data
        assert tuple(duplicate.matrix_world) == tuple(cube.matrix_world)
        assert [tuple(v.co) for v in duplicate.data.vertices] == [tuple(v.co) for v in cube.data.vertices]
        assert duplicate.name == "SM_Bad_Name"
        assert len(bpy.data.objects["Guarded"].modifiers) == 1
        assert len(bpy.data.objects["Shaped"].data.shape_keys.key_blocks) == 2
        from math import isclose, pi
        from mathutils import Euler
        cube.rotation_mode = "QUATERNION"
        cube.rotation_quaternion = Euler((0, 0, pi / 2)).to_quaternion()
        rotated = audit_blender((cube.name,))["objects"][0]
        assert rotated["rotation_mode"] == "QUATERNION"
        assert isclose(rotated["rotation_euler_radians"][2], pi / 2, abs_tol=1e-6)
    elif mode == "verify_saved":
        bpy.ops.wm.open_mainfile(filepath=str(Path(path).resolve()), use_scripts=False)
        assert "SM_Bad_Name" in bpy.data.objects
        assert "Bad Name" in bpy.data.objects
        assert "SM_Guarded" not in bpy.data.objects
        assert "SM_Shaped" not in bpy.data.objects
        assert bpy.data.objects["Bad Name"].data != bpy.data.objects["SM_Bad_Name"].data
    else:
        raise ValueError("Unknown fixture operation")
    print("CRYPTONYAN_BLENDER_ASSERTIONS_PASSED")


if __name__ == "__main__":
    main()
