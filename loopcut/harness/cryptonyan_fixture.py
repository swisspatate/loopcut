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
