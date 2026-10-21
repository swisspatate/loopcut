# SPDX-License-Identifier: GPL-3.0-or-later
"""Existing custom skeleton with deliberately defective, inspectable skin weights."""
import sys
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
data = bpy.data.armatures.new("ExistingSkeleton")
rig = bpy.data.objects.new("ExistingRig", data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for i, bone_name in enumerate(("Origin", "Leg", "Tail", "Spine", "Head", "Helper")):
    bone = data.edit_bones.new(bone_name)
    bone.head, bone.tail = (i, 0, 0), (i, 0, 1)
    if i:
        bone.parent = data.edit_bones["Origin"]
bpy.ops.object.mode_set(mode="OBJECT")
data.bones["Helper"].use_deform = False
mesh = bpy.data.meshes.new("BodyData")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1)], [], [(0, 1, 2, 3), (0, 1, 4)])
body = bpy.data.objects.new("Body", mesh)
bpy.context.scene.collection.objects.link(body)
for bone in data.bones:
    body.vertex_groups.new(name=bone.name)
body.vertex_groups.new(name="PaintMask")
# 0 unweighted; 1 sum .5; 2 five influences; 3 valid; 4 helper/mask only.
body.vertex_groups["Origin"].add([1], .5, "REPLACE")
for group in list(body.vertex_groups)[:5]:
    group.add([2], .2, "REPLACE")
body.vertex_groups["Leg"].add([3], 1, "REPLACE")
body.vertex_groups["Helper"].add([4], 1, "REPLACE")
body.vertex_groups["PaintMask"].add([4], 1, "REPLACE")
modifier = body.modifiers.new("ExistingSkin", "ARMATURE")
modifier.object = rig
modifier.use_bone_envelopes = False
wrong = body.copy()
wrong.name = "AmbiguousBody"
bpy.context.scene.collection.objects.link(wrong)
wrong.modifiers.new("SecondSkin", "ARMATURE").object = rig
if "--repair" in sys.argv:
    wrong.data = wrong.data.copy()
    uv = mesh.uv_layers.new(name="ExistingUV")
    for i, loop in enumerate(uv.data):
        loop.uv = (i / 8, (i % 3) / 4)
    body.shape_key_add(name="Basis")
    key = body.shape_key_add(name="ExistingSmile")
    key.data[2].co.z += .25
    key.value = .3
    locked = body.copy()
    locked.data = body.data.copy()
    locked.name = "LockedBody"
    bpy.context.scene.collection.objects.link(locked)
    locked.vertex_groups["Origin"].lock_weight = True
    shared = body.copy()
    shared.data = body.data.copy()
    shared.name = "SharedBody"
    bpy.context.scene.collection.objects.link(shared)
    twin = shared.copy()
    twin.name = "SharedTwin"
    bpy.context.scene.collection.objects.link(twin)
if "--external" in sys.argv:
    image = bpy.data.images.new("ExternalReference", width=1, height=1)
    image.source = "FILE"
    image.filepath = "//unpacked-texture.png"
    image.use_fake_user = True
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--")+1], check_existing=False)
