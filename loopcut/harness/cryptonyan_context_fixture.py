# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual Blender selection capture and mask operators; no GPU viewport in background."""
import json
from pathlib import Path
import struct
import sys
import zlib
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio import scene_selection,reference_board,reference_ui,mask_paint
from cryptonyan_asset_studio.storage import write_json
root=Path(sys.argv[sys.argv.index('--')+1])
def png():
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,8,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80\x80\xff'*16)*8))+chunk(b'IEND',b'')
image=root/'reference.png';image.write_bytes(png())
cube=bpy.data.objects['Cube']
bpy.ops.object.armature_add();rig=bpy.context.object;rig.name='CatRig'
mod=cube.modifiers.new('ExistingRig','ARMATURE');mod.object=rig
rig.keyframe_insert(data_path='location',frame=1)
rig.location.x=1;rig.keyframe_insert(data_path='location',frame=10)
bpy.context.scene.frame_set(3)
mat=cube.data.materials[0];texture=mat.node_tree.nodes.new('ShaderNodeTexImage')
texture.image=bpy.data.images.load(str(image),check_existing=False);texture.image.pack()
bpy.ops.object.select_all(action='DESELECT');cube.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=cube
before=[(o.name,tuple(o.location),o.data.as_pointer() if o.data else None) for o in bpy.context.scene.objects]
node_count=len(mat.node_tree.nodes)
studio.register();studio.register()
s=bpy.context.window_manager.cryptonyan_context;s.library=str(root/'library');s.snapshot_id='rigged-cat'
assert bpy.ops.cryptonyan.context_export(action='METADATA')=={'FINISHED'}
snapshot=scene_selection.load(root/'library/scene-contexts/rigged-cat')
objects={o['summary']['name']:o for o in snapshot['facts']['objects']}
assert objects['Cube']['rig']=={'name':'CatRig','bones':['Bone'],'pose_position':'POSE'}
assert objects['Cube']['uv_maps']==['UVMap']
assert objects['CatRig']['animation']['channel_count']==3
assert objects['Cube']['materials'][0]['images'][0]['packed']
assert snapshot['facts']['scene']['frame']==3 and snapshot['image'] is None
board=root/'library/board';reference_board.create(board,'board','Board')
reference_board.add(board,0,'front',image,'Front')
ui=bpy.context.window_manager.cryptonyan_references;ui.folder=str(board);reference_ui.refresh(ui)
assert bpy.ops.cryptonyan.mask_action(action='REFERENCE')=={'FINISHED'}
settings=bpy.context.window_manager.cryptonyan_masks
settings.editor=str(root/'editor.html')
assert bpy.ops.cryptonyan.mask_action(action='EDITOR')=={'FINISHED'}
_,ref=mask_paint._reference(Path(settings.reference))
project={'schema':mask_paint.SCHEMA,'reference':ref,'intent':'Neige','strokes':[{'mode':'paint','radius_px':2,'value':255,'points':[[.25,.5],[.75,.5]]}]}
write_json(root/'strokes.json',project)
settings.strokes=str(root/'strokes.json');settings.output=str(root/'mask')
assert bpy.ops.cryptonyan.mask_action(action='RENDER')=={'FINISHED'}
assert mask_paint.load_bundle(root/'mask')['reference']==ref
assert before==[(o.name,tuple(o.location),o.data.as_pointer() if o.data else None) for o in bpy.context.scene.objects]
assert node_count==len(mat.node_tree.nodes)
studio.unregister();studio.unregister()
assert not hasattr(bpy.types.WindowManager,'cryptonyan_context') and not hasattr(bpy.types.WindowManager,'cryptonyan_masks')
print('CRYPTONYAN_CONTEXT_ASSERTIONS_PASSED')
