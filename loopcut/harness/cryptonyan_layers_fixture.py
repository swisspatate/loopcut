# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual sidebar operators, packed maps and existing Loopcut GLB exporter."""
from pathlib import Path
import sys
import hashlib
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio.blender_materials import create_packed_material,validate_material
from cryptonyan_asset_studio.materials import load_material
from loopcut import glb
root=Path(sys.argv[sys.argv.index('--')+1])
before=[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.register();studio.register()
s=bpy.context.window_manager.cryptonyan_layers
s.recipe=str(root/'recipe.json');s.sources=str(root/'sources');s.bundle=str(root/'bundle');s.output=str(root/'result')
for action in ('PREPARE','CHECK','COMPOSE'):
    assert bpy.ops.cryptonyan.layer_action(action=action)=={'FINISHED'}
assert before==[(o.name,tuple(o.location)) for o in bpy.context.scene.objects]
studio.unregister();studio.unregister()
assert not hasattr(bpy.types.WindowManager,'cryptonyan_layers')
# Apply the composed bundle to a disposable cube for existing publisher compatibility.
obj=bpy.data.objects.get('Cube')
material=create_packed_material(root/'result/material.json')
obj.data.materials.clear();obj.data.materials.append(material)
assert validate_material(obj,material)=={'base_color','roughness','normal'}
manifest=load_material(root/'result/material.json')
images=[n.image for n in material.node_tree.nodes if n.type=='TEX_IMAGE']
assert {hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in images}=={c['sha256'] for c in manifest['channels'].values()}
for image in images:
    assert len(image.pixels)>0 and image.has_data
# Export only the disposable mesh through Blender's existing glTF add-on.
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
bpy.ops.export_scene.gltf(filepath=str(root/'material.glb'),export_format='GLB',use_selection=True)
doc,binary=glb.parse((root/'material.glb').read_bytes())
assert not glb.validate(doc,binary)
assert len(doc.get('images',[]))>=2
print('CRYPTONYAN_LAYERS_ASSERTIONS_PASSED')
