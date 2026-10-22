# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import modular_levels as levels
from cryptonyan_asset_studio.creative_director import make_plan,operations
from cryptonyan_asset_studio.unreal_director import execute
from cryptonyan_asset_studio.storage import digest,write_json
from cryptonyan_asset_studio.image_workshop import identity
from loopcut import glb
from test_glb import glb_bytes
from test_cryptonyan_director import Editor,Obj


def floor_glb():
    vertices=[(x,y,z) for x in (-4,4) for y in (-.25,0) for z in (-4,4)]
    indices=[0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3]
    binary=struct.pack('<24f36H',*[v for p in vertices for v in p],*indices)
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'Floor','mesh':0}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1,'material':0}]}],'materials':[{'name':'Floor'}],
         'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':96},{'buffer':0,'byteOffset':96,'byteLength':72}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':8,'type':'VEC3','min':[-4,-.25,-4],'max':[4,0,4]},
                      {'bufferView':1,'componentType':5123,'count':36,'type':'SCALAR'}]}
    return glb_bytes(doc,binary)


def recipe():
    return {'schema':'cryptonyan.modular-level/1','id':'Temple','seed':42,'grid':{'width':5,'height':5},
        'start':[0,0],'goal':[4,0],'waypoints':[{'id':'Shrine','cell':[2,2],'tag':'Room'}],
        'blocked':[],'route_cells':[9,15],'branches':{'count':2,'length':2,'end_tag':'Reward'},'loops':0,
        'required_tags':['Walkable'],'player':{'radius_m':.35,'height_m':1.5,'margin_m':.15},'search_budget':20000,
        'anchor_m':[10,20,1],'destination':'/Game/CryptoNyan/DirectedReviews/ModularDemo','target_level':'/Game/CryptoNyan/ReviewMaps/ModularDemo'}


def catalog(root):
    path=root/'floor.glb';path.write_bytes(floor_glb())
    result={'schema':'cryptonyan.modular-catalog/1','cell_m':8,'modules':[]}
    for name,sides in [('End',['east']),('Straight',['east','west']),('Corner',['east','north']),
                       ('Tee',['east','north','west']),('Cross',list(levels.SIDES))]:
        result['modules'].append({'id':name,'preview_glb':{'file':'floor.glb','sha256':digest(path)},'unreal_mesh':'/Game/Rooms/'+name+'.'+name,
            'tags':['Walkable','Room','Reward'],'doors':[{'side':s,'kind':'Walk','width_m':2,'height_m':2.4} for s in sides],'blockers_m':[]})
    return result


class ModularTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='modular é ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.sources=self.root/'sources';self.sources.mkdir()
        self.catalog=catalog(self.sources);self.recipe=recipe()

    def plan(self):return levels.make_plan(self.recipe,self.catalog,self.sources)

    def test_reproducible_graph_branches_and_unavoidable_checkpoint(self):
        before=copy.deepcopy((self.recipe,self.catalog));a=self.plan();b=self.plan()
        self.assertEqual(a,b);self.assertEqual((self.recipe,self.catalog),before)
        qa=levels.analyze(a);self.assertTrue(qa['model_passed']);self.assertEqual(qa['mandatory_checkpoints'],{'Shrine':True})
        self.assertEqual(len(a['branches']),2);self.assertEqual(len(a['placements']),len(a['main_route'])+4)
        self.assertFalse(qa['engine_validated'] or qa['controller_validated'] or qa['navmesh_validated'])
        main=[next(p['cell'] for p in a['placements'] if p['id']==key) for key in a['main_route']]
        self.assertIn([2,2],main)

    def test_different_seed_changes_module_choices_or_branch_locations(self):
        a=self.plan();self.recipe['seed']=43;b=self.plan()
        self.assertNotEqual(a['placements'],b['placements'])

    def test_blocked_cells_never_occupied_and_disconnected_grid_rejected(self):
        self.recipe['blocked']=[[4,4],[0,4]];plan=self.plan()
        self.assertFalse({tuple(c) for c in self.recipe['blocked']} & {tuple(p['cell']) for p in plan['placements']})
        self.recipe['blocked']=[[1,y] for y in range(5)]
        with self.assertRaisesRegex(ValueError,'No main route'):self.plan()

    def test_loops_do_not_turn_checkpoint_into_optional_path(self):
        spec=copy.deepcopy(self.recipe);spec['route_cells']=[15,15];spec['branches']={'count':0,'length':1,'end_tag':None};spec['loops']=1
        found=None
        for seed in range(16):
            spec['seed']=seed
            try:found=levels.make_plan(spec,self.catalog,self.sources);break
            except ValueError:continue
        self.assertIsNotNone(found)
        qa=levels.analyze(found);self.assertEqual(qa['loop_count'],1);self.assertTrue(qa['mandatory_checkpoints']['Shrine'])

    def test_narrow_low_door_or_blocked_center_is_not_accepted(self):
        for change in ('width','height','blocker'):
            cat=copy.deepcopy(self.catalog)
            for m in cat['modules']:
                if change=='blocker':m['blockers_m']=[{'min':[-.2,-.2,0],'max':[.2,.2,2]}]
                else:
                    for door in m['doors']:door['width_m' if change=='width' else 'height_m']=.5
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'No module'):levels.make_plan(self.recipe,cat,self.sources)

    def test_overhead_blockers_outside_player_height_are_allowed(self):
        for m in self.catalog['modules']:m['blockers_m']=[{'min':[-1,-1,2],'max':[1,1,3]}]
        self.assertTrue(levels.analyze(self.plan())['model_passed'])

    def test_door_kinds_must_match(self):
        end=copy.deepcopy(self.catalog['modules'][0])
        straight=copy.deepcopy(self.catalog['modules'][1])
        for door in straight['doors']:door['kind']='Bridge'
        cat={**self.catalog,'modules':[end,straight]}
        spec=recipe();spec.update(start=[0,0],goal=[2,0],waypoints=[],route_cells=[3,3])
        spec['branches']['count']=0
        with self.assertRaisesRegex(ValueError,'Connector kinds'):levels.make_plan(spec,cat,self.sources)

    def test_tag_requirement_and_missing_module_shape_rejected(self):
        for m in self.catalog['modules']:m['tags']=['Walkable']
        with self.assertRaisesRegex(ValueError,'No module'):self.plan()

    def test_forged_accessor_bounds_and_changed_binary_rejected(self):
        path=self.sources/'floor.glb';doc,binary=glb.parse(path.read_bytes());doc['accessors'][0]['min'][0]=-3
        path.write_bytes(glb_bytes(doc,binary))
        for m in self.catalog['modules']:m['preview_glb']['sha256']=digest(path)
        with self.assertRaisesRegex(ValueError,'binary vertex'):self.plan()

    def test_cell_footprint_and_pinned_hash_rejected(self):
        self.catalog['cell_m']=7
        with self.assertRaisesRegex(ValueError,'fit'):self.plan()
        self.catalog['cell_m']=8;self.catalog['modules'][0]['preview_glb']['sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'pinned'):self.plan()

    def test_grid_budget_recipe_limits_and_traversal(self):
        for change in (lambda s:s.update(start=s['goal']),lambda s:s.update(blocked=[s['start']]),lambda s:s.update(route_cells=[2,64]),
                       lambda s:s.update(seed=True),lambda s:s['player'].update(radius_m=float('nan')),lambda s:s.update(destination='/Game/Original')):
            value=recipe();change(value)
            with self.assertRaises(ValueError):levels.specification(value)
        self.catalog['modules'][0]['preview_glb']['file']='../escape.glb'
        with self.assertRaises(ValueError):self.plan()
        self.catalog['modules'][0]['preview_glb']['file']='floor.glb'
        spec=recipe();spec.update(grid={'width':8,'height':8},start=[0,0],goal=[7,0],waypoints=[],route_cells=[64,64],search_budget=128)
        spec['branches']['count']=0
        with self.assertRaisesRegex(ValueError,'budget'):levels.make_plan(spec,self.catalog,self.sources)

    def test_snapshot_survives_deleted_sources_and_tampering_is_rejected(self):
        out=self.root/'bundle';plan=levels.prepare(self.recipe,self.catalog,self.sources,out)
        shutil.rmtree(self.sources)
        self.assertEqual(levels.load_bundle(out),plan)
        (out/'sources/End.glb').write_bytes(b'tampered')
        with self.assertRaises(ValueError):levels.load_bundle(out)

    def test_generated_csv_and_director_recipe_preserve_units_and_yaw(self):
        plan=self.plan();rows=list(csv.DictReader(io.StringIO(levels.points_csv(plan))))
        for row,p in zip(rows,plan['placements']):
            self.assertAlmostEqual(float(row['x_cm']),p['position_m'][0]*100)
            self.assertAlmostEqual(float(row['y_cm']),p['position_m'][1]*100)
        generated=operations(levels.director(plan))
        self.assertEqual([o['position_cm'] for o in generated],[[v*100 for v in p['position_m']] for p in plan['placements']])
        self.assertEqual([o['yaw_deg'] for o in generated],[p['yaw_deg'] for p in plan['placements']])

    def test_existing_unreal_architecture_adapter_places_generated_review(self):
        plan=self.plan();game=self.root/'game';game.mkdir();write_json(game/'Game.uproject',{'FileVersion':3})
        editor=Editor(game)
        target=self.recipe['target_level'];editor.world=Obj(target+'.'+target.rsplit('/',1)[-1],'World')
        for m in self.catalog['modules']:editor.add(m['unreal_mesh'],'StaticMesh')
        path=self.root/'director-plan.json';write_json(path,make_plan(levels.director(plan),game))
        receipt=execute(path,self.root/'engine-receipt.json',apply=True,unreal_module=editor)
        self.assertEqual(len(editor.actors),len(plan['placements']));self.assertFalse(receipt['engine_validated'])

    def engine(self):
        game=self.root/'game';game.mkdir();write_json(game/'Game.uproject',{'FileVersion':3})
        editor=Editor(game);target=self.recipe['target_level']
        editor.world=Obj(target+'.'+target.rsplit('/',1)[-1],'World')
        for m in self.catalog['modules']:
            mesh=editor.add(m['unreal_mesh'],'StaticMesh')
            mesh.get_bounding_box=lambda:NS(min=NS(x=-400,y=-400,z=-25),max=NS(x=400,y=400,z=0))
        return editor

    def test_unreal_bounds_gate_then_existing_director_places_review(self):
        from cryptonyan_asset_studio.unreal_modular import review
        bundle=self.root/'bundle';plan=levels.prepare(self.recipe,self.catalog,self.sources,bundle)
        editor=self.engine()
        result=review(bundle,self.root/'review',apply=True,unreal_module=editor)
        self.assertEqual(len(result['bounds_checked']),len({p['module'] for p in plan['placements']}))
        self.assertEqual(len(editor.actors),len(plan['placements']))
        self.assertFalse(result['controller_validated'] or result['navmesh_validated'])

    def test_unreal_bound_mismatch_blocks_before_spawning_or_output(self):
        from cryptonyan_asset_studio.unreal_modular import review
        bundle=self.root/'bundle';levels.prepare(self.recipe,self.catalog,self.sources,bundle)
        editor=self.engine()
        for mesh in editor.objects.values():
            mesh.get_bounding_box=lambda:NS(min=NS(x=-399,y=-400,z=-25),max=NS(x=400,y=400,z=0))
        with self.assertRaisesRegex(ValueError,'bounds differ'):review(bundle,self.root/'review',apply=True,unreal_module=editor)
        self.assertEqual(editor.actors,[]);self.assertFalse((self.root/'review').exists())

    def test_unreal_dry_run_never_spawns(self):
        from cryptonyan_asset_studio.unreal_modular import review
        bundle=self.root/'bundle';levels.prepare(self.recipe,self.catalog,self.sources,bundle)
        editor=self.engine();result=review(bundle,self.root/'review',unreal_module=editor)
        self.assertEqual(editor.actors,[]);self.assertNotEqual(result['status'],'failed')

    def test_missing_unreal_mapping_keeps_preview_but_no_director(self):
        for m in self.catalog['modules']:m['unreal_mesh']=None
        plan=self.plan();self.assertIsNone(levels.director(plan))

    def test_derived_artifact_tampering_and_output_boundaries(self):
        out=self.root/'bundle';levels.prepare(self.recipe,self.catalog,self.sources,out)
        with self.assertRaises(FileExistsError):levels.prepare(self.recipe,self.catalog,self.sources,out)
        with self.assertRaises(ValueError):levels.prepare(self.recipe,self.catalog,self.sources,self.sources/'nested')
        (out/'level-points.csv').write_text('changed')
        with self.assertRaises(ValueError):levels.load_bundle(out)

    def test_preview_failure_records_no_success_artifacts(self):
        out=self.root/'bundle';levels.prepare(self.recipe,self.catalog,self.sources,out)
        with patch.object(levels,'run_process',side_effect=RuntimeError('worker failed')),self.assertRaises(RuntimeError):
            levels.preview(out,self.root/'preview',sys.executable)
        receipt=json.loads((self.root/'preview/operation.json').read_text())
        self.assertEqual(receipt['status'],'failed');self.assertNotIn('artifacts',receipt)

    def test_cli_prepare_check(self):
        write_json(self.root/'recipe.json',self.recipe);write_json(self.root/'catalog.json',self.catalog)
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')};prefix=[sys.executable,'-m','cryptonyan_asset_studio.modular_levels']
        for args in (['prepare',str(self.root/'recipe.json'),'--catalog',str(self.root/'catalog.json'),'--source-root',str(self.sources),'--output',str(self.root/'bundle')],['check',str(self.root/'bundle')]):
            r=subprocess.run(prefix+args,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIsInstance(json.loads(r.stdout),dict)


BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
@unittest.skipUnless(BLENDER,'Real Blender unavailable')
class BlenderTests(unittest.TestCase):
    def test_actual_imported_mesh_instances_sidebar_and_saved_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=root/'sources';sources.mkdir();cat=catalog(sources)
            write_json(root/'recipe.json',recipe());write_json(root/'catalog.json',cat)
            r=subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
                '--python',str(ROOT/'loopcut/harness/cryptonyan_modular_fixture.py'),'--',str(root)],capture_output=True,text=True,timeout=90)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('CRYPTONYAN_MODULAR_ASSERTIONS_PASSED',r.stdout)

    def test_generated_demo_rooms_prepare_and_preview_with_real_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=levels.demo(root/'sources',BLENDER)
            self.assertEqual(result['status'],'sources_created_review_required')
            cat=json.loads((root/'sources/catalog.json').read_text())
            spec=json.loads((root/'sources/recipe.json').read_text())
            self.assertEqual(len(cat['modules']),5)
            plan=levels.prepare(spec,cat,root/'sources',root/'bundle')
            self.assertIsNone(levels.director(plan))
            receipt=levels.preview(root/'bundle',root/'preview',BLENDER)
            self.assertEqual(receipt['status'],'preview_created_review_required')
            self.assertGreater((root/'preview/modular-preview.blend').stat().st_size,0)


if __name__=='__main__':unittest.main()
