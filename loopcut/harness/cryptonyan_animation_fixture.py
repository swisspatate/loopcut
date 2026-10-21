# SPDX-License-Identifier: GPL-3.0-or-later
"""A custom-named existing rig, two actions and a world-space evaluated constraint."""
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
from loopcut.scene_context import _fcurves

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 10
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = .01
data = bpy.data.armatures.new("CustomSkeleton")
rig = bpy.data.objects.new("ExistingRig", data)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
root = data.edit_bones.new("Origin")
root.head, root.tail = (0, 0, 0), (0, 10, 0)
foot = data.edit_bones.new("FootCustom")
foot.head, foot.tail, foot.parent = (0, 0, 0), (0, 5, 0), root
bpy.ops.object.mode_set(mode="OBJECT")
target = bpy.data.objects.new("ContactTarget", None)
scene.collection.objects.link(target)
for frame, x in ((1, 0), (11, 40)):
    target.location.x = x
    target.keyframe_insert("location", frame=frame)
for curve in _fcurves(target):
    for point in curve.keyframe_points:
        point.interpolation = "LINEAR"
constraint = rig.pose.bones["FootCustom"].constraints.new("COPY_LOCATION")
constraint.target = target
constraint.owner_space = constraint.target_space = "WORLD"
rig.animation_data_create()
for action_name, distance in (("Run", 100), ("Unused", 0)):
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    rig.animation_data.action = action
    for frame, x in ((1, 0), (11, distance)):
        rig.pose.bones["Origin"].location.x = x
        rig.pose.bones["Origin"].keyframe_insert("location", frame=frame)
    for curve in _fcurves(rig):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
scene.frame_set(7)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--")+1], check_existing=False)
