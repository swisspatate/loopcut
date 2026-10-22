# SPDX-License-Identifier: GPL-3.0-or-later
"""Small authored room kit, generated only on explicit demo command in factory Blender."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.creative_worker import reset,box_mesh,instance,material
from cryptonyan_asset_studio.modular_levels import example_recipe
from cryptonyan_asset_studio.storage import digest,write_json
from loopcut import glb


def build(root):
    catalog={'schema':'cryptonyan.modular-catalog/1','cell_m':8,'modules':[]}
    definitions=[('End',['east']),('Straight',['east','west']),('Corner',['east','north']),
                 ('Tee',['east','north','west']),('Cross',['east','north','west','south'])]
    for index,(name,doors) in enumerate(definitions):
        reset()
        boxes=[{'center':[0,0,-.125],'size':[8,8,.25]}]
        proxies=[]
        for side in ('east','north','west','south'):
            axis=0 if side in ('east','west') else 1
            sign=1 if side in ('east','north') else -1
            sections=[(-4,4,0,3)] if side not in doors else [(-4,-1,0,3),(1,4,0,3),(-1,1,2.4,3)]
            for low,high,bottom,top in sections:
                center=[0,0,(bottom+top)/2];size=[0,0,top-bottom]
                center[axis]=sign*3.9;size[axis]=.2
                center[1-axis]=(low+high)/2;size[1-axis]=high-low
                minimum=[c-s/2 for c,s in zip(center,size)];maximum=[c+s/2 for c,s in zip(center,size)]
                proxies.append({'min':minimum,'max':maximum})
                # Demo input/proxies are Unreal local metres; source meshes use Blender Y=-Y.
                center[1]=-center[1]
                boxes.append({'center':center,'size':size})
        obj=instance(name,box_mesh(name,boxes))
        obj.data.materials.append(material('M_'+name,(.12+.08*index,.35,.65-.06*index)))
        path=root/(name+'.glb');glb._export(path,[obj])
        catalog['modules'].append({'id':name,'preview_glb':{'file':path.name,'sha256':digest(path)},'unreal_mesh':None,
            'tags':['Walkable','Room','Reward'],'doors':[{'side':side,'kind':'Walk','width_m':2,'height_m':2.4} for side in doors],
            'blockers_m':proxies})
    write_json(root/'catalog.json',catalog);write_json(root/'recipe.json',example_recipe())


if __name__=='__main__':build(Path(sys.argv[sys.argv.index('--')+1]))
