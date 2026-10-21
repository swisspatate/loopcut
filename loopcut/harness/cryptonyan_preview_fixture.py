# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender assertions, including subframes beyond the shortest two cycles."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
import bpy
from cryptonyan_asset_studio.runner_kit import read_json
from cryptonyan_asset_studio.runner_motion import position_at
from cryptonyan_asset_studio.world_preview import preview_placement, validate_preview
from loopcut.scene_context import _fcurves

root = Path(sys.argv[sys.argv.index("--")+1])
catalog = validate_preview(root)
plan = read_json(root / "world-plan.json")
bpy.ops.wm.open_mainfile(filepath=str(root / "world-preview.blend"), load_ui=False, use_scripts=False)
scene = bpy.context.scene
assert len(scene.objects) == len(plan["actors"])
assert scene.frame_end == catalog["window"]["frame_end"]
assert scene.render.fps == 30 and scene.render.fps_base == 1
assert len({obj.data.as_pointer() for obj in scene.objects}) == len(plan["modules"])
assert not bpy.data.libraries and not bpy.data.texts
assert len([c for c in scene.collection.children if c.name.startswith("Z")]) == len(plan["zones"])
module_meshes = {}
for item in plan["actors"]:
    obj = scene.objects[item["id"]]
    module_meshes.setdefault(item["module"], obj.data)
    assert obj.data == module_meshes[item["module"]]
    assert obj.parent is None and not obj.modifiers
    assert obj["cryptonyan_collision"] == item["collision"]
    assert obj.material_slots[0].link == "OBJECT"
    mat = obj.material_slots[0].material
    palette = plan["recipe"]["biomes"][item["biome"]]
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert max(abs(a-b) for a, b in zip(shader.inputs["Base Color"].default_value[:3], palette["color_linear"])) < 1e-6
    assert abs(shader.inputs["Roughness"].default_value-palette["roughness"]) < 1e-6
    assert max(abs(a-b) for a, b in zip(obj.scale, item["scale"])) < 1e-6
    if item["amplitude_cm"]:
        curves = _fcurves(obj)
        assert len(curves) == 1
        assert curves[0].keyframe_points[-1].co.x == scene.frame_end
        assert all(k.interpolation == "LINEAR" for k in curves[0].keyframe_points)
    else:
        assert obj.animation_data is None
for frame in (1, 17, 80, 162, 199, 240, 280):
    for subframe in (0., .37):
        scene.frame_set(frame, subframe=subframe)
        for item in plan["actors"]:
            expected = position_at(preview_placement(item), (frame-1+subframe)/30)
            actual = scene.objects[item["id"]].matrix_world.translation
            assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-4, (item["id"], frame, actual, expected)
print("CRYPTONYAN_WORLD_PREVIEW_PASSED")
