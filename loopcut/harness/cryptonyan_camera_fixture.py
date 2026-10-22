# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual operator calls, isolated child preview, and independent look-at checks."""
from pathlib import Path
import sys
import math
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio.camera_moves import load_program
root=Path(sys.argv[sys.argv.index('--')+1])
before=[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.register();studio.register()
s=bpy.context.window_manager.cryptonyan_cameras
s.recipe=str(root/'recipe.json');s.bundle=str(root/'bundle');s.output=str(root/'preview')
assert bpy.ops.cryptonyan.camera_action(action='PREPARE')=={'FINISHED'}
assert bpy.ops.cryptonyan.camera_action(action='PREVIEW')=={'FINISHED'}
assert before==[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.unregister();studio.unregister()
assert not hasattr(bpy.types.WindowManager,'cryptonyan_cameras')
data=load_program(root/'bundle')
bpy.ops.wm.open_mainfile(filepath=str(root/'preview/camera-preview.blend'),use_scripts=False)
scene=bpy.context.scene
assert scene.frame_start==1 and scene.frame_end==210
assert len(scene.objects)==2 and all(o.type=='CAMERA' for o in scene.objects)
assert [(m.name,m.frame) for m in scene.timeline_markers]==[('Approach',1),('Orbit',91)]
offset=0
for shot,compiled in zip(data['recipe']['shots'],data['cinematic']['shots']):
    obj=scene.objects[shot['id']]
    target=shot.get('target_m',shot.get('center_m'))
    target=Vector((target[0],-target[1],target[2]))
    for key in compiled['keys']:
        scene.frame_set(offset+key['frame']+1)
        x,y,z=key['position_m']
        assert (obj.location-Vector((x,-y,z))).length<1e-5
        actual=obj.matrix_world.to_quaternion()@Vector((0,0,-1))
        expected=(target-obj.matrix_world.translation).normalized()
        assert (actual-expected).length<1e-5
    offset+=shot['frames']
assert not bpy.data.texts and not bpy.data.libraries
print('CRYPTONYAN_CAMERA_ASSERTIONS_PASSED')
