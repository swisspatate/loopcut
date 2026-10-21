# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed weighted body and near-body unrigged cloth; no production assets."""
import sys
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
data = bpy.data.armatures.new("ExistingSkeleton")
rig = bpy.data.objects.new("ExistingRig", data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
root = data.edit_bones.new("Origin"); root.head, root.tail = (0,0,0), (0,0,1)
child = data.edit_bones.new("Tip"); child.head, child.tail, child.parent = (0,0,1), (0,0,2), root
bpy.ops.object.mode_set(mode="OBJECT")
for frame, x in ((1,0), (3,.2)):
    rig.pose.bones["Tip"].location.x = x
    if "--penetrate" in sys.argv: rig.pose.bones["Tip"].location.y = x*4
    rig.pose.bones["Tip"].keyframe_insert("location", frame=frame)
rig.animation_data.action.name = "Preview"
bpy.context.scene.frame_set(1)
bpy.ops.mesh.primitive_cube_add()
body = bpy.context.object; body.name = "Body"
if "--open" in sys.argv:
    import bmesh
    bm=bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table(); bm.faces.remove(bm.faces[0]); bm.to_mesh(body.data); bm.free()
for name, weight in (("Origin",.75),("Tip",.25)):
    body.vertex_groups.new(name=name).add(list(range(len(body.data.vertices))),weight,"REPLACE")
body.modifiers.new("Skin","ARMATURE").object = rig
mesh=bpy.data.meshes.new("GarmentData")
z = 2 if "--far" in sys.argv else 1.01
mesh.from_pydata([(-.5,-.5,z),(.5,-.5,z),(.5,.5,z),(-.5,.5,z)],[],[(0,1,2,3)])
garment=bpy.data.objects.new("Garment",mesh); bpy.context.scene.collection.objects.link(garment)
uv=mesh.uv_layers.new(name="UV")
for loop, value in zip(uv.data, ((0,0),(1,0),(1,1),(0,1))): loop.uv=value
garment.vertex_groups.new(name="PaintMask").add([0],.4,"REPLACE")
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--")+1],check_existing=False)
