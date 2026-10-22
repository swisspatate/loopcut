# SPDX-License-Identifier: GPL-3.0-or-later
"""Real UI calls and child GLB preview; inspect the saved instance transforms."""
from pathlib import Path
import sys
import math
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio import modular_levels as levels
root=Path(sys.argv[sys.argv.index('--')+1])
before=[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.register();studio.register()
s=bpy.context.window_manager.cryptonyan_modular
s.recipe=str(root/'recipe.json');s.catalog=str(root/'catalog.json');s.sources=str(root/'sources')
s.bundle=str(root/'bundle');s.output=str(root/'preview')
for action in ('PREPARE','CHECK','PREVIEW'):assert bpy.ops.cryptonyan.modular_action(action=action)=={'FINISHED'}
assert before==[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.unregister();studio.unregister()
assert not hasattr(bpy.types.WindowManager,'cryptonyan_modular')
plan=levels.load_bundle(root/'bundle')
bpy.ops.wm.open_mainfile(filepath=str(root/'preview/modular-preview.blend'),use_scripts=False)
scene=bpy.context.scene
assert scene['cryptonyan_level_id']==plan['identity']
meshes={o.name:o for o in scene.objects if o.type=='MESH'}
assert len(meshes)==len(plan['placements'])
for p in plan['placements']:
    o=meshes[p['id']];x,y,z=p['position_m']
    assert max(abs(a-b) for a,b in zip(o.location,(x,-y,z)))<1e-5
    assert abs(o.rotation_euler.z+math.radians(p['yaw_deg']))<1e-5
    assert o['cryptonyan_module']==p['module']
assert len({o.data.as_pointer() for o in meshes.values()})==len({p['module'] for p in plan['placements']})
assert not bpy.data.texts and not bpy.data.libraries
print('CRYPTONYAN_MODULAR_ASSERTIONS_PASSED')
