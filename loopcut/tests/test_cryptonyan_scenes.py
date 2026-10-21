# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic recipes and strict editor protocol tests; no Unreal runtime claim."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio.scene_recipes import compile_level,compile_wardrobe,make_plan,load_plan,overlap
from cryptonyan_asset_studio.unreal_scenes import execute
from cryptonyan_asset_studio.storage import write_json
from test_cryptonyan_director import Editor,Obj,Actor,MAP
MESH='/Game/Block.Block'; MAT='/Game/Skin.Skin'; BODY='/Game/Body.Body'; SKEL='/Game/Rig.Rig'; CLIP='/Game/Run.Run'; CLOTH='/Game/Coat.Coat'
def level():
    theme=dict(sun_lux=10,fog_density=.01,weather='clear',materials={'Block':MAT},lights=[],sound=None,niagara=None)
    return dict(kind='level',target_level=MAP,seed=12,theme='Night',modules={'Block':dict(mesh=MESH,half_m=[.5,.5,.5])},
        themes={'Night':theme,'Snow':{**theme,'weather':'snow','sun_lux':1000}},clearances=[dict(min_m=[-1,-20,-1],max_m=[1,20,5])],
        buildings=[],landmarks=[],scatter=[dict(id='Props',min_m=[-10,-10,0],max_m=[10,10,0],count=20,modules=['Block'],scale_range=[.5,1])])
def wardrobe():
    outfit=dict(materials=[dict(slot=0,material=MAT)],accessories=[dict(id='Hat',mesh=MESH,socket='Head',offset_m=[0,0,.02],rotation_rpy_deg=[0,0,10],scale=[.5,.5,.5])],
       garments=[dict(id='Coat',mesh=CLOTH,materials=[dict(slot=0,material=MAT)])])
    return dict(kind='wardrobe',target_level=MAP,body=BODY,skeleton=SKEL,animations={'Run':CLIP},animation='Run',outfits={'Explorer':outfit},outfit='Explorer')
class Component(Obj):
    def __init__(self,editor,owner=None):
        super().__init__();self.editor=editor;self.owner=owner;self.materials={}
    def set_skeletal_mesh_asset(self,mesh):self.mesh=mesh
    def get_skinned_asset(self):return self.mesh
    def set_static_mesh(self,mesh):self.mesh=mesh;self.properties['static_mesh']=mesh;return True
    def does_socket_exist(self,name):return name in self.editor.sockets
    def get_num_materials(self):return self.mesh.properties.get('slots',1)
    def set_material(self,slot,material):self.materials[slot]=material
    def get_material(self,slot):return self.materials[slot]
    def set_collision_enabled(self,value):assert value=='none'
    def set_mobility(self,value):assert value=='movable'
    def set_simulate_physics(self,value):assert value is False
    def set_intensity(self,value):self.intensity=value
    def set_light_color(self,value,srgb):assert srgb is False;self.color=value
    def set_attenuation_radius(self,value):self.radius=value
    def set_sound(self,value):self.sound=value
    def set_asset(self,value):self.effect=value
    def override_animation_data(self,anim,looping,playing,position,rate):
        assert (looping,playing,position,rate)==(True,True,0,1);self.animation=anim
    def set_update_animation_in_editor(self,value):assert value is True
    def set_leader_pose_component(self,leader,force,tick):
        assert (force,tick)==(True,False);self.properties['leader_pose_component']=leader
class SceneActor(Actor):
    def __init__(self,path,location,rotation,editor,kind):
        super().__init__(path,location,rotation);self.component=Component(editor,self);self.actor_kind=kind
    def set_actor_rotation(self,value,teleport):assert teleport is True;self.rotation=value
    def attach_to_component(self,component,socket,location,rotation,scale,weld):
        assert (location,rotation,scale,weld)==('snap','snap','snap',False);self.parent=component.owner;self.socket=socket;return True
    def set_actor_relative_location(self,value,sweep,teleport):assert (sweep,teleport)==(False,True);self.offset=value
    def set_actor_relative_rotation(self,value,sweep,teleport):assert (sweep,teleport)==(False,True);self.relative_rotation=value
    def set_actor_relative_scale3d(self,value):self.relative_scale=value
    def get_attach_parent_actor(self):return self.parent
    def configure_atmosphere(self,lux,fog,weather):self.atmosphere=(lux,fog,weather)
    def configure_mechanism(self,kind,element,power,extent):self.mechanism=(kind,element,power,extent);return True
    def configure_platform(self,mesh,material,rest,collision,amplitude,period,phase):
        assert mesh and material and collision and 0<=amplitude<=300 and 0<=phase<period<=20
        self.platform=(rest,amplitude,period,phase);return True
class SceneEditor(Editor):
    PointLight='light';PointLightComponent='point_component';AmbientSound='sound';AudioComponent='audio_component';NiagaraActor='niagara';NiagaraComponent='niagara_component'
    LinearColor=staticmethod(lambda r,g,b,a:NS(r=r,g=g,b=b,a=a))
    SkeletalMeshActor='skeletal_mesh';CryptoNyanAtmosphere='atmosphere';CryptoNyanMechanism='mechanism';CryptoNyanPlatform='platform'
    CollisionEnabled=NS(NO_COLLISION='none');ComponentMobility=NS(MOVABLE='movable');AttachmentRule=NS(SNAP_TO_TARGET='snap')
    CryptoNyanWeather=NS(CLEAR='clear',SNOW='snow',RAIN='rain',ASH='ash')
    def SkeletalMeshComponent(self):return Component(self)
    def spawn(self,kind,location,rotation):
        if len(self.actors)==self.fail_spawn_at:return None
        actor=SceneActor('Actor_'+str(len(self.actors)),location,rotation,self,kind);self.actors.append(actor);return actor
class RecipeTests(unittest.TestCase):
    def test_seeded_scatter_clearances_and_themes_share_geometry(self):
        value=level();first,_=compile_level(copy.deepcopy(value));self.assertEqual(first,compile_level(copy.deepcopy(value))[0])
        for i,a in enumerate(first):
            self.assertFalse(overlap(a['declared_bounds'],[[-1,-20,-1],[1,20,5]]))
            self.assertTrue(all(not overlap(a['declared_bounds'],b['declared_bounds']) for b in first[:i]))
        value['theme']='Snow';self.assertEqual(first,compile_level(value)[0])
    def test_impossible_density_refuses_partial_level(self):
        value=level();value['scatter'][0].update(min_m=[-.1,-.1,0],max_m=[.1,.1,0])
        with self.assertRaisesRegex(ValueError,'density'):compile_level(value)
    def test_building_has_floors_roof_and_open_entrance(self):
        value=level();value.update(scatter=[],clearances=[],buildings=[dict(id='House',origin_m=[0,0,0],grid=[2,2,2],cell_m=[4,4,3],floor='Block',wall='Block',roof='Block')])
        ops,_=compile_level(value);self.assertEqual(len(ops),27)
        self.assertNotIn('House_W0_0_1',[o['id'] for o in ops]);self.assertIn('House_F2_1_1',[o['id'] for o in ops])
    def test_invalid_budget_and_clearance_intersection(self):
        value=level();value['scatter'][0]['count']=True
        with self.assertRaises(ValueError):compile_level(value)
        value=level();value['landmarks']=[dict(id='Tower',position_m=[0,0,0],parts=[dict(module='Block',offset_m=[0,0,0],yaw_deg=0,scale=[1,1,1])],mechanism=None)]
        with self.assertRaisesRegex(ValueError,'clearance'):compile_level(value)
    def test_platform_reuses_runtime_contract_and_reserves_swept_volume(self):
        value=level();value['platforms']=[dict(id='Lift',module='Block',position_m=[20,0,3],amplitude_m=2,period_s=4,phase_s=1)]
        op=next(o for o in compile_level(value)[0] if o['kind']=='platform')
        self.assertEqual(op['declared_bounds'],[[19.5,-.5,.5],[20.5,.5,5.5]])
        for key,v in [('amplitude_m',4),('period_s',21),('phase_s',4)]:
            bad=copy.deepcopy(value);bad['platforms'][0][key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):compile_level(bad)
    def test_wardrobe_rejects_duplicate_parts_slots_and_body_as_garment(self):
        for field,value in [('id','Hat'),('mesh',BODY)]:
            recipe=wardrobe();recipe['outfits']['Explorer']['garments'][0][field]=value
            with self.assertRaises(ValueError):compile_wardrobe(recipe)
        recipe=wardrobe();recipe['outfits']['Explorer']['materials']*=2
        with self.assertRaises(ValueError):compile_wardrobe(recipe)
class EditorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name);self.project=self.root/'game';self.project.mkdir()
        write_json(self.project/'Test.uproject',dict(FileVersion=3,EngineAssociation='5.8'))
        self.u=SceneEditor(self.project);self.u.sockets={'Head'}
        skeleton=self.u.add(SKEL,'Skeleton')
        for path,kind in [(BODY,'SkeletalMesh'),(CLOTH,'SkeletalMesh'),(CLIP,'AnimSequence')]:self.u.add(path,kind,skeleton=skeleton)
        mesh=self.u.add(MESH,'StaticMesh');mesh.get_bounding_box=lambda:NS(min=NS(x=-50,y=-50,z=-50),max=NS(x=50,y=50,z=50))
        self.u.add(MAT,'MaterialInstanceConstant');self.plan=self.root/'plan.json';self.report=self.root/'result.json'
    def execute(self,recipe,apply=True):
        write_json(self.plan,make_plan(recipe,self.project));return execute(self.plan,self.report,apply=apply,unreal_module=self.u)
    def test_outfit_links_skeleton_materials_accessories_and_single_node_animation(self):
        result=self.execute(wardrobe());self.assertEqual(result['status'],'placed_review_required',result)
        body,garment,hat=self.u.actors
        self.assertEqual(garment.component.properties['leader_pose_component'],body.component)
        self.assertEqual(hat.socket,'Head');self.assertEqual(hat.offset.z,2)
        self.assertIs(body.component.animation,self.u.objects[CLIP]);self.assertIs(body.component.materials[0],self.u.objects[MAT])
        self.assertEqual(self.u.saved,[]);self.assertFalse(result['engine_validated'])
    def test_levels_assign_meshes_theme_and_mechanisms(self):
        value=level();value['scatter'][0]['count']=2
        value['landmarks']=[dict(id='Beacon',position_m=[20,0,1],parts=[dict(module='Block',offset_m=[0,0,0],yaw_deg=0,scale=[1,1,1])],mechanism=dict(kind='beacon',element='fire',strength=1,half_m=[1,1,1]))]
        value['platforms']=[dict(id='Lift',module='Block',position_m=[30,0,3],amplitude_m=2,period_s=4,phase_s=1)]
        result=self.execute(value);self.assertEqual(result['status'],'placed_review_required',result)
        self.assertEqual(self.u.actors[-1].atmosphere,(10,.01,'clear'))
        self.assertEqual(sum(a.actor_kind=='mechanism' for a in self.u.actors),1)
        self.assertEqual(sum(a.actor_kind=='platform' for a in self.u.actors),1)
    def test_ambience_uses_explicit_lights_sound_and_niagara_assets(self):
        value=level();theme=value['themes']['Night']
        theme.update(lights=[dict(position_m=[3,4,5],color=[.1,.2,.3],intensity=1000,radius_m=10)],sound='/Game/Sound.Sound',niagara='/Game/FX.FX')
        self.u.add(theme['sound'],'SoundWave');self.u.add(theme['niagara'],'NiagaraSystem')
        result=self.execute(value);self.assertEqual(result['status'],'placed_review_required',result)
        light,sound,effect=self.u.actors[-3:]
        self.assertEqual(light.component.radius,1000);self.assertEqual(light.component.color.g,.2)
        self.assertIs(sound.component.sound,self.u.objects[theme['sound']]);self.assertIs(effect.component.effect,self.u.objects[theme['niagara']])
    def test_transform_readback_failure_rolls_back_placement(self):
        spawn=self.u.spawn
        def broken(*args):
            actor=spawn(*args);actor.get_actor_scale3d=lambda:NS(x=999,y=999,z=999);return actor
        self.u.spawn=broken;result=self.execute(level())
        self.assertEqual(result['error'],'scale_readback_failed');self.assertEqual(self.u.actors,[])
    def test_incompatible_source_roles_refuse_plan(self):
        value=wardrobe();value['skeleton']=value['body']
        with self.assertRaisesRegex(ValueError,'incompatible'):make_plan(value,self.project)
    def test_missing_socket_wrong_skeleton_and_slot_fail_before_spawning(self):
        for change in ('socket','skeleton','slot'):
            with self.subTest(change=change):
                recipe=wardrobe();self.u.sockets={'Head'};self.u.objects[CLOTH].properties['skeleton']=self.u.objects[SKEL]
                if change=='socket':self.u.sockets=set()
                elif change=='skeleton':self.u.objects[CLOTH].properties['skeleton']=Obj('/Game/Other.Other','Skeleton')
                else:recipe['outfits']['Explorer']['materials'][0]['slot']=5
                result=self.execute(recipe);self.assertEqual(result['status'],'failed');self.assertEqual(self.u.actors,[]);self.report.unlink()
    def test_failed_spawn_removes_only_owned_actors(self):
        self.u.fail_spawn_at=1;result=self.execute(wardrobe())
        self.assertEqual(result['status'],'failed');self.assertEqual(result['remaining_actors'],[])
        self.assertEqual(self.u.removed,['Actor_0']);self.assertEqual(self.u.saved,[])
    def test_nonempty_wrong_map_dirty_content_and_bad_bounds_refused(self):
        for case in ('nonempty','map','dirty','bounds'):
            with self.subTest(case=case):
                self.u.actors=[];self.u.dirty=[];self.u.world.path=MAP+'.DirectorTest'
                if case=='nonempty':self.u.actors=[Obj('Foreign','Actor')]
                elif case=='map':self.u.world.path='/Game/Existing.Existing'
                elif case=='dirty':self.u.dirty=['/Game/Body']
                else:self.u.objects[MESH].get_bounding_box=lambda:NS(min=NS(x=0,y=0,z=0),max=NS(x=100,y=100,z=100))
                result=self.execute(level());self.assertEqual(result['status'],'failed');self.assertEqual(result['owned_actors'],[]);self.report.unlink()
    def test_source_and_plan_tampering_are_rejected_and_dry_run_needs_no_engine(self):
        result=self.execute(wardrobe(),False);self.assertEqual(result['status'],'planned');self.assertEqual(self.u.actors,[])
        file=self.project/'Content/Body.uasset';file.write_bytes(b'changed')
        with self.assertRaises(ValueError):load_plan(self.plan)
        write_json(self.plan,make_plan(wardrobe(),self.project));plan=json.loads(self.plan.read_text());plan['operations'][0]['materials']=[];write_json(self.plan,plan)
        with self.assertRaises(ValueError):load_plan(self.plan)
class MechanismRulesTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++') or shutil.which('clang++'),'C++ compiler unavailable')
    def test_standalone_rules_compile_and_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'rules.cpp';binary=root/('rules.exe' if os.name=='nt' else 'rules')
            source.write_text('''#include "CryptoNyanMechanismRules.h"
#include <cassert>
#include <limits>
int main(){using namespace CryptoNyanMechanismRules;
assert(Valid(5,5,2000)); assert(!Valid(6,0,1)); assert(!Valid(0,0,std::numeric_limits<double>::infinity()));
assert(Activate(0,2,2,false));assert(Activate(1,2,2,false));assert(!Activate(0,2,3,false));assert(!Activate(0,2,2,true));assert(!Activate(3,2,2,false));
assert(Gravity(20)==2);assert(Gravity(.01)==.1);assert(WindImpulse(100,1)==10);assert(WindImpulse(100,-1)==0);
}''')
            compiler=shutil.which('g++') or shutil.which('clang++')
            result=subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'integrations/unreal/CryptoNyanRuntime/Source/CryptoNyanRuntime/Public'),str(source),'-o',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);subprocess.run([str(binary)],check=True,timeout=10)
if __name__=='__main__':unittest.main()
