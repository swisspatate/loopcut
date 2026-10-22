# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual GLB room instances in a factory Blender scene; no original .blend opened."""
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.modular_levels import load_bundle,placement_bounds
from cryptonyan_asset_studio.storage import safe_path,write_json


def build(folder):
    import bpy
    from mathutils import Matrix
    root=Path(folder)
    plan=load_bundle(root/'inputs')
    if bpy.data.filepath:raise ValueError('Modular worker requires a factory scene')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    meshes={}
    for item in plan['catalog']['modules']:
        if item['id'] not in {p['module'] for p in plan['placements']}:continue
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(safe_path(root/'inputs',item['preview_glb']['file'])))
        imported=set(bpy.data.objects)-before
        if len(imported)!=1:raise ValueError('Expected exactly one static GLB mesh')
        obj=imported.pop()
        if obj.type!='MESH' or obj.parent or obj.animation_data or obj.modifiers:raise ValueError('Unexpected GLB runtime object')
        obj.data.transform(obj.matrix_world);obj.matrix_world=Matrix.Identity(4)
        meshes[item['id']]=obj.data
        bpy.data.objects.remove(obj,do_unlink=True)
    objects={}
    for p in plan['placements']:
        obj=bpy.data.objects.new(p['id'],meshes[p['module']]);scene.collection.objects.link(obj)
        x,y,z=p['position_m'];obj.location=(x,-y,z);obj.rotation_euler.z=-math.radians(p['yaw_deg'])
        obj['cryptonyan_module']=p['module'];obj['cryptonyan_plan']=plan['identity'];obj['engine_validated']=False
        objects[p['id']]=obj
    scene.view_layers[0].update()
    error=0.0
    for p in plan['placements']:
        obj=objects[p['id']]
        points=[obj.matrix_world@vertex.co for vertex in obj.data.vertices]
        actual=[[min(v[i] if i!=1 else -v[i] for v in points) for i in range(3)],
                [max(v[i] if i!=1 else -v[i] for v in points) for i in range(3)]]
        expected=placement_bounds(plan,p)
        error=max(error,max(abs(a-b) for x,y in zip(actual,expected) for a,b in zip(x,y)))
    if error>1e-4:raise ValueError('Imported room placement bounds differ from the verified plan')
    curve=bpy.data.curves.new('DeclaredConnections','CURVE');curve.dimensions='3D';curve.bevel_depth=.025
    for edge in plan['links']:
        spline=curve.splines.new('POLY');spline.points.add(1)
        for point,key in zip(spline.points,(edge['from'],edge['to'])):
            pos=objects[key].location;point.co=(pos.x,pos.y,pos.z+.1,1)
    overlay=bpy.data.objects.new('DeclaredConnections',curve);scene.collection.objects.link(overlay)
    markers=[(plan['main_route'][0],'Start'),(plan['main_route'][-1],'Goal')]+[(w['tile'],w['id']) for w in plan['checkpoints']]
    for key,label in markers:
        marker=bpy.data.objects.new(label,None);scene.collection.objects.link(marker)
        marker.location=objects[key].location;marker.empty_display_type='PLAIN_AXES';marker.empty_display_size=.6
    for image in bpy.data.images:
        if image.source=='FILE' and not image.packed_file:image.pack()
    scene['cryptonyan_level_id']=plan['identity'];scene['engine_validated']=False
    scene['navigation_scope']='declared graph and authored proxies; review in Unreal'
    write_json(root/'preview-check.json',{'plan_identity':plan['identity'],'checked_placements':len(objects),'max_bounds_error_m':error})
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'modular-preview.blend'),check_existing=False)


if __name__=='__main__':build(Path(sys.argv[sys.argv.index('--')+1]))
