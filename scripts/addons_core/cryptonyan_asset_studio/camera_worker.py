# SPDX-License-Identifier: GPL-3.0-or-later
"""Factory-scene camera-only preview, with actual keyframe look-at readback."""
from pathlib import Path
import sys
import math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.camera_moves import load_program
from cryptonyan_asset_studio.creative_director import operations
from cryptonyan_asset_studio.storage import write_json


def build(folder):
    import bpy
    from mathutils import Vector
    from loopcut.scene_context import _fcurves
    root=Path(folder)
    data=load_program(root)
    if bpy.data.filepath: raise ValueError('Camera worker requires a factory scene')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.render.fps=data['recipe']['fps'];scene.render.fps_base=1
    scene.frame_start=1;scene.frame_end=sum(s['frames'] for s in data['cinematic']['shots'])
    scene['cryptonyan_camera_program']=data['identity']
    scene['cryptonyan_coordinates']='Blender_X=Unreal_X; Blender_Y=-Unreal_Y; Blender_Z=Unreal_Z'
    count,error=0,0.0
    expected=[]
    for shot,generated in zip(data['recipe']['shots'],operations(data['cinematic'])):
        camera_data=bpy.data.cameras.new(shot['id']);camera_data.lens=50
        obj=bpy.data.objects.new(shot['id'],camera_data);scene.collection.objects.link(obj)
        obj.rotation_mode='XYZ'
        previous=None
        for key in generated['keys']:
            # Unreal has a left-handed world and +X camera forward. Convert the world
            # handedness explicitly, then orient Blender's local -Z/+Y camera axes.
            x,y,z=[v/100 for v in key['position_cm']]
            pitch,yaw=map(math.radians,key['rotation_rpy_deg'][1:])
            forward=Vector((math.cos(pitch)*math.cos(yaw),-math.cos(pitch)*math.sin(yaw),math.sin(pitch)))
            rotation=forward.to_track_quat('-Z','Y').to_euler('XYZ',previous) if previous is not None else forward.to_track_quat('-Z','Y').to_euler('XYZ')
            obj.location=(x,-y,z);obj.rotation_euler=rotation;previous=rotation.copy()
            frame=key['frame']+1
            obj.keyframe_insert(data_path='location',frame=frame)
            obj.keyframe_insert(data_path='rotation_euler',frame=frame)
            expected.append((obj,frame,forward.copy()))
        # Reuse Loopcut's legacy/slotted-action compatibility helper.
        for curve in _fcurves(obj):
            for point in curve.keyframe_points:point.interpolation='LINEAR'
        marker=scene.timeline_markers.new(shot['id'],frame=generated['start']+1);marker.camera=obj
        if scene.camera is None:scene.camera=obj
    for obj,frame,forward in expected:
        scene.frame_set(frame)
        actual=obj.matrix_world.to_quaternion()@Vector((0,0,-1))
        error=max(error,(actual-forward).length);count+=1
    scene.frame_set(1)
    if error>1e-5:raise ValueError('Camera look-at readback failed')
    write_json(root/'camera-check.json',{'program_identity':data['identity'],'checked_keys':count,'look_at_error_max':error})
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'camera-preview.blend'),check_existing=False)


if __name__=='__main__':build(Path(sys.argv[sys.argv.index('--')+1]))
