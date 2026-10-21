# SPDX-License-Identifier: GPL-3.0-or-later
"""Generated stylized quadruped: weighted blockout, four IK legs, in-place clips.

This does not auto-rig arbitrary imported cats or produce production skin weights.
"""
import math

from .animation_adapter import CatRigConvention
from .creative_kit import CLIPS


def build_cat():
    import bpy
    from mathutils import Vector
    from loopcut.scene_context import _fcurves

    bones = {
        "root": ((0, 0, 0), (0, 0, .2), None, False),
        "pelvis": ((-.55, 0, .9), (-.2, 0, .95), "root", True),
        "spine.01": ((-.2, 0, .95), (.2, 0, 1), "pelvis", True),
        "spine.02": ((.2, 0, 1), (.55, 0, 1), "spine.01", True),
        "neck": ((.55, 0, 1), (.7, 0, 1.2), "spine.02", True),
        "head": ((.7, 0, 1.2), (1, 0, 1.2), "neck", True),
        "ear.L": ((.7, .2, 1.35), (.7, .2, 1.65), "head", True),
        "ear.R": ((.7, -.2, 1.35), (.7, -.2, 1.65), "head", True)}
    for i in range(3):
        bones[f"tail.{i+1:02d}"] = ((-.6-i*.3, 0, 1), (-.9-i*.3, 0, 1.05),
                                      "pelvis" if i == 0 else f"tail.{i:02d}", True)
    for end, x in (("front", .45), ("back", -.5)):
        for side, y in (("L", .28), ("R", -.28)):
            suffix = end+"."+side
            parent = "spine.02" if end == "front" else "pelvis"
            bones["upper_"+suffix] = ((x, y, .9), (x+.12, y, .48), parent, True)
            bones["lower_"+suffix] = ((x+.12, y, .48), (x, y, .14), "upper_"+suffix, True)
            bones["paw_"+suffix] = ((x, y, .14), (x+.2, y, .14), "lower_"+suffix, True)
            bones["ik_"+suffix] = ((x, y, .14), (x+.2, y, .14), "root", False)
            bones["pole_"+suffix] = ((x+1, y, .48), (x+1, y, .68), "root", False)
    arm = bpy.data.armatures.new("CryptoNyanCatSkeleton")
    rig = bpy.data.objects.new("CryptoNyanCat", arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, parent, deform) in bones.items():
        bone = arm.edit_bones.new(name)
        bone.head, bone.tail, bone.use_deform = head, tail, deform
        if parent:
            bone.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.show_in_front = True
    for name in bones:
        if name.startswith("lower_"):
            suffix = name.removeprefix("lower_")
            ik = rig.pose.bones[name].constraints.new("IK")
            ik.target, ik.subtarget, ik.chain_count = rig, "ik_"+suffix, 2
            ik.pole_target, ik.pole_subtarget, ik.pole_angle = rig, "pole_"+suffix, math.pi/2
            paw = rig.pose.bones["paw_"+suffix].constraints.new("COPY_ROTATION")
            paw.target, paw.subtarget = rig, "ik_"+suffix
            paw.target_space = paw.owner_space = "WORLD"
    material = bpy.data.materials.new("CatPeach")
    material.diffuse_color = (.8, .3, .17, 1)
    parts = []
    for name, (head, tail, parent, deform) in bones.items():
        if not deform:
            continue
        h, t = Vector(head), Vector(tail)
        width = .38 if name in ("pelvis", "spine.01", "spine.02") else .32 if name == "head" else .12
        if name.startswith("ear."):
            bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=.14, radius2=0, depth=(t-h).length, location=(h+t)/2)
        else:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(h+t)/2)
        obj = bpy.context.object
        obj.name = "Skin_"+name
        if not name.startswith("ear."):
            obj.dimensions = (width, (t-h).length+.05, width)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = (t-h).to_track_quat("Z", "Y") if name.startswith("ear.") else (t-h).to_track_quat("Y", "Z")
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        group = obj.vertex_groups.new(name=name)
        group.add(list(range(len(obj.data.vertices))), 1, "REPLACE")
        obj.data.materials.append(material)
        parts.append(obj)
    face_material = bpy.data.materials.new("CatFace")
    face_material.diffuse_color = (.015,.01,.02,1)
    for name, location, size in (("Eye.L",(1.035,.105,1.25),(.025,.055,.07)),
                                 ("Eye.R",(1.035,-.105,1.25),(.025,.055,.07)),
                                 ("Nose",(1.045,0,1.16),(.04,.055,.035))):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name, obj.dimensions = name, size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.vertex_groups.new(name="head").add(list(range(len(obj.data.vertices))),1,"REPLACE")
        obj.data.materials.append(face_material)
        parts.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    skin = bpy.context.object
    skin.name = "CryptoNyanCatSkin"
    modifier = skin.modifiers.new("QuadrupedSkin", "ARMATURE")
    modifier.object = rig
    skin.parent = rig
    actions = {}
    for name, end in CLIPS.items():
        rig.animation_data_create()
        action = bpy.data.actions.new("CN_"+name)
        action.use_fake_user = True
        rig.animation_data.action = action
        for frame in range(1, end+1, 2):
            phase = (frame-1)/(end-1)
            for pose in rig.pose.bones:
                pose.location = (0, 0, 0)
                pose.rotation_mode = "XYZ"
                pose.rotation_euler = (0, 0, 0)
            lift = .025*math.sin(phase*math.tau) if name == "idle" else 0
            if name == "jump":
                lift = .65*math.sin(math.pi*phase)
            if name == "land":
                lift = -.16*math.sin(math.pi*phase)
            if name in ("run", "dash"):
                lift = .035*(1-math.cos(phase*math.tau*2))
            pelvis = rig.pose.bones["pelvis"]
            pelvis.location = pelvis.bone.matrix_local.to_3x3().inverted() @ Vector((0, 0, lift))
            pelvis.keyframe_insert("location", frame=frame)
            for end_name in ("front", "back"):
                for side in ("L", "R"):
                    control = rig.pose.bones["ik_"+end_name+"."+side]
                    phase_offset = (0 if (end_name == "front") == (side == "L") else math.pi)
                    wave = math.sin(phase*math.tau+phase_offset)
                    offset = Vector((0, 0, 0))
                    if name in ("run", "dash"):
                        offset = Vector((wave*(.18 if name == "run" else .28), 0, max(0, wave)*.12))
                    elif name == "jump":
                        offset.z = lift+.1*math.sin(math.pi*phase)
                    elif name == "brake":
                        offset.x = (.16 if end_name == "front" else -.1)*math.sin(math.pi*phase)
                    control.location = control.bone.matrix_local.to_3x3().inverted() @ offset
                    control.keyframe_insert("location", frame=frame)
            for index in range(1, 4):
                tail = rig.pose.bones[f"tail.{index:02d}"]
                tail.rotation_euler.y = .15*math.sin(phase*math.tau+(index-1)*.4)
                tail.keyframe_insert("rotation_euler", frame=frame)
            for ear_name in ("ear.L", "ear.R"):
                ear = rig.pose.bones[ear_name]
                ear.rotation_euler.x = .12*math.sin(phase*math.tau)
                ear.keyframe_insert("rotation_euler", frame=frame)
        for curve in _fcurves(rig):
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
        actions[name] = action
    rig.animation_data.action = actions["run"]
    convention = CatRigConvention()
    rig["cryptonyan_root_motion"] = convention.root_motion
    rig["cryptonyan_rig"] = "generated_quadruped_blockout_v1"
    bpy.context.scene.render.fps = 30
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, CLIPS["run"]
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    return rig, skin, actions


def validate_cat(rig, skin):
    import math
    convention = CatRigConvention()
    required = (convention.root_bone, convention.pelvis_bone, *convention.foot_bones,
                *convention.spine_chain, *convention.tail_chain)
    if any(name not in rig.data.bones for name in required):
        raise ValueError("Missing quadruped bones")
    if len([c for p in rig.pose.bones for c in p.constraints if c.type == "IK" and c.chain_count == 2]) != 4:
        raise ValueError("Require four two-bone IK legs")
    for vertex in skin.data.vertices:
        if not vertex.groups or abs(sum(g.weight for g in vertex.groups)-1) > 1e-5:
            raise ValueError("Unweighted or unnormalized cat vertex")
        if any(skin.vertex_groups[g.group].name not in rig.data.bones or
               not rig.data.bones[skin.vertex_groups[g.group].name].use_deform for g in vertex.groups):
            raise ValueError("Skin bound to a non-deforming control")
    if any(not math.isfinite(v) for bone in rig.pose.bones for row in bone.matrix for v in row):
        raise ValueError("Invalid quadruped pose")
    return {"bones": len(rig.data.bones), "weighted_vertices": len(skin.data.vertices),
            "ik_legs": 4, "root_motion": False, "arbitrary_mesh_auto_rig": False}
