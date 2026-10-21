# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect saved creative assets and real evaluated IK/skin animation in Blender."""
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
import bpy
from mathutils import Vector
from cryptonyan_asset_studio.creative_kit import CLIPS, validate_bundle
from cryptonyan_asset_studio.cat_rig import validate_cat
from cryptonyan_asset_studio.blender_materials import validate_material

root = Path(sys.argv[sys.argv.index("--")+1])
catalog = validate_bundle(root)
plan = json.loads((root / "plan.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(root / "architecture.blend"), load_ui=False, use_scripts=False)
assert len(bpy.context.scene.objects) == len(plan["modules"])
for name in plan["modules"]:
    obj = bpy.data.objects[name]
    assert len(obj.data.uv_layers) == 1 and not obj.modifiers
    assert all(v > 0 for v in obj.dimensions)
    if (root / "material/material.json").exists():
        validate_material(obj, obj.active_material)
bpy.ops.wm.open_mainfile(filepath=str(root / "environment.blend"), load_ui=False, use_scripts=False)
scene = bpy.context.scene
assert scene["cryptonyan_kit_id"] == catalog["kit_id"]
assert not bpy.data.libraries and not bpy.data.texts
assert len(scene.objects["Mountains"].data.vertices) == plan["recipe"]["terrain_grid"]**2
assert len({scene.objects[a["id"]].data.as_pointer() for a in plan["actors"]}) <= len(plan["modules"])
liquid = scene.objects["Liquid_"+plan["recipe"]["liquid"]]
scene.frame_set(1)
basis = [v.co.copy() for v in liquid.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
scene.frame_set(16)
wave = [v.co.copy() for v in liquid.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
assert max((a-b).length for a,b in zip(basis,wave)) > .05
particle = scene.objects["FX_fire_00"]
scene.frame_set(1); start = particle.location.copy()
scene.frame_set(16); assert (particle.location-start).length > .5

bpy.ops.wm.open_mainfile(filepath=str(root / "cat.blend"), load_ui=False, use_scripts=False)
scene = bpy.context.scene
rig, skin = scene.objects["CryptoNyanCat"], scene.objects["CryptoNyanCatSkin"]
validate_cat(rig, skin)
assert len([a for a in bpy.data.actions if a.name.startswith("CN_")]) == len(CLIPS)
for name, end in CLIPS.items():
    rig.animation_data.action = bpy.data.actions["CN_"+name]
    snapshots = []
    for frame in (1, (end+1)//2, end):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        validate_cat(rig, skin)
        evaluated = skin.evaluated_get(bpy.context.evaluated_depsgraph_get())
        snapshots.append([evaluated.matrix_world @ v.co for v in evaluated.data.vertices])
        assert rig.pose.bones["root"].location.length < 1e-6
    assert max((a-b).length for a,b in zip(snapshots[0],snapshots[1])) > .005, name
    if name in ("idle", "run"):
        assert max((a-b).length for a,b in zip(snapshots[0],snapshots[2])) < 1e-4, name
rig.animation_data.action = None
control = rig.pose.bones["ik_front.L"]
scene.frame_set(1)
bpy.context.view_layer.update()
before = rig.pose.bones["lower_front.L"].tail.copy()
control.location += control.bone.matrix_local.to_3x3().inverted() @ Vector((.08,0,.1))
bpy.context.view_layer.update()
assert (rig.pose.bones["lower_front.L"].tail-before).length > .05
print("CRYPTONYAN_CREATIVE_PASSED")
