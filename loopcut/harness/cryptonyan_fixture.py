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
    elif mode == "create_theme_assets":
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        material = bpy.data.materials.new("OriginalSharedMaterial")
        material.use_nodes = True
        for index, name in enumerate(("BlockA", "BlockB")):
            bpy.ops.mesh.primitive_cube_add(location=(index * 4, 0, 0))
            obj = bpy.context.object
            obj.name = name
            obj.data.materials.append(material)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(path).resolve()), check_existing=False)
    elif mode == "verify_theme_batch":
        import json
        root = Path(path)
        plan = json.loads((root / "plan.json").read_text())
        for job in plan["jobs"]:
            bpy.ops.wm.open_mainfile(filepath=str(root / job["id"] / "asset.blend"), use_scripts=False)
            obj = bpy.data.objects[job["object"]]
            material = obj.data.materials[0]
            texture = next(n for n in material.node_tree.nodes if n.type == "TEX_IMAGE")
            import hashlib
            expected = plan["materials"][job["material"]]["channels"]["base_color"]["sha256"]
            assert hashlib.sha256(bytes(texture.image.packed_file.data)).hexdigest() == expected
            other = bpy.data.objects["BlockB" if job["object"] == "BlockA" else "BlockA"]
            assert other.data.materials[0].name == "OriginalSharedMaterial"
            assert other.data.materials[0] != material
            assert all(n.type != "TEX_IMAGE" for n in other.data.materials[0].node_tree.nodes)
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
    elif mode == "verify_runner":
        import json
        root = Path(path)
        layout = json.loads((root / "layout.json").read_text())
        length, width, thickness = layout["module"]["size_m"]
        bpy.ops.wm.open_mainfile(filepath=str(root / "modules.blend"), use_scripts=False)
        assert len(bpy.context.scene.objects) == 1
        obj = bpy.data.objects["RunnerPlatform"]
        assert tuple(obj.location) == (0, 0, 0) and tuple(obj.scale) == (1, 1, 1)
        assert tuple(obj["cryptonyan_entry_m"]) == (0, 0, 0)
        assert tuple(obj["cryptonyan_exit_m"]) == (length, 0, 0)
        assert len(obj.data.uv_layers) == 1
        obj.data.calc_loop_triangles()
        assert len(obj.data.loop_triangles) == 12
        bpy.ops.wm.open_mainfile(filepath=str(root / "preview.blend"), use_scripts=False)
        assert len(bpy.context.scene.objects) == len(layout["placements"])
        assert len({o.data for o in bpy.context.scene.objects}) == 1
        for placement in layout["placements"]:
            obj = bpy.context.scene.objects[placement["id"]]
            from cryptonyan_asset_studio.runner_motion import position_at
            assert all(abs(a-b) < 1e-5 for a, b in zip(obj.location, position_at(placement, 0)))
            assert obj["cryptonyan_layout_id"] == layout["layout_id"]
        if layout["schema"] == "cryptonyan.runner-layout/2":
            period = layout["recipe"]["motion"]["period_frames"]
            for frame in (1, 2, period // 4 + 1, period, period + 1, 2 * period + 1):
                for subframe in (0, 0.37) if frame < 2 * period + 1 else (0,):
                    bpy.context.scene.frame_set(frame, subframe=subframe)
                    for placement in layout["placements"]:
                        obj = bpy.context.scene.objects[placement["id"]]
                        expected = position_at(placement, (frame - 1 + subframe) / 30)
                        assert all(abs(a-b) < 1e-5 for a, b in zip(obj.location, expected)), (frame, subframe, tuple(obj.location), expected)
                        assert not obj.animation_data or not obj.animation_data.drivers
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        manifest = json.loads((root / "publication/manifest.json").read_text())
        bpy.ops.import_scene.gltf(filepath=str(root / "publication" / manifest["asset"]["file"]))
        obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
        points = [obj.matrix_world @ v.co for v in obj.data.vertices]
        bounds = [[min(v[i] for v in points) for i in range(3)], [max(v[i] for v in points) for i in range(3)]]
        expected = [[0, -width/2, -thickness], [length, width/2, 0]]
        assert all(abs(a-b) < 1e-5 for va, vb in zip(bounds, expected) for a,b in zip(va,vb)), bounds
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
