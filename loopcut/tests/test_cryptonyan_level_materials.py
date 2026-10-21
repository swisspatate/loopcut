# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict Unreal protocol doubles and durable restoration tests; no engine runtime."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio.level_materials import make_plan, load_plan, comparison_html
from cryptonyan_asset_studio.unreal_level_materials import inspect_selection, execute, restore, operation
from cryptonyan_asset_studio.storage import digest, write_json
from test_cryptonyan_unreal_materials import Object

WORLD='/Game/Maps/Garden.Garden'
MESH='/Game/Props/Wall.Wall'
BASE='/Game/Materials/Original.Original'
OLD='/Game/Materials/Override.Override'
NEW='/Game/Materials/Candidate.Candidate'
FOREIGN='/Game/Materials/Foreign.Foreign'


class Component(Object):
    def __init__(self, actor, mesh, overrides=None):
        kind='StaticMeshComponent' if mesh.kind=='StaticMesh' else 'SkeletalMeshComponent'
        super().__init__(actor.path+'.Mesh',kind,creation_method='native',override_materials=overrides or [],static_mesh=mesh)
        self.actor, self.mesh, self.writes, self.on_write = actor, mesh, 0, None
    def get_owner(self):return self.actor
    def get_skinned_asset(self):return self.mesh
    def get_num_materials(self):return len(self.mesh.properties['static_materials' if self.mesh.kind=='StaticMesh' else 'materials'])
    def get_material(self, i):
        overrides=self.properties['override_materials']
        return overrides[i] if i<len(overrides) and overrides[i] is not None else self.mesh.properties['static_materials' if self.mesh.kind=='StaticMesh' else 'materials'][i].properties['material_interface']
    def modify(self):return self.actor.u.transaction_depth > 0
    def set_editor_property(self, name, value):
        assert name=='override_materials'
        self.writes+=1
        if self.on_write:self.on_write(value)
        self.properties[name]=value
        self.actor.u.dirty_maps=[Object(WORLD.split('.')[0],'Package')]


class Actor(Object):
    def __init__(self,u,name,mesh,guid=1,overrides=None):
        super().__init__(WORLD+':PersistentLevel.'+name,'StaticMeshActor',actor_guid=NS(to_string=lambda:f'{guid:032x}'))
        self.u=u;self.level=Object(WORLD+':PersistentLevel','Level')
        self.components=[Component(self,mesh,overrides)]
    def is_package_external(self):return self.properties.get('external',False)
    def get_level(self):return self.level
    def get_components_by_class(self,kind):assert kind=='mesh';return self.components


class Transaction:
    def __init__(self,u,name):self.u=u;self.name=name
    def __enter__(self):self.u.transactions.append(self.name);self.u.transaction_depth+=1;return self
    def __exit__(self,*args):self.u.transaction_depth-=1;return False


class Editor:
    MeshComponent='mesh';LevelEditorSubsystem='level';UnrealEditorSubsystem='editor';EditorActorSubsystem='actors'
    ComponentCreationMethod=NS(NATIVE='native',INSTANCE='instance')
    def __init__(self,root):
        self.root=root;self.objects={};self.actors=[];self.selected=[];self.dirty=[];self.dirty_maps=[];self.playing=False;self.transactions=[];self.transaction_depth=0
        self.world=Object(WORLD,'World')
        self.SystemLibrary=NS(get_engine_version=lambda:'5.8.3-test')
        self.Paths=NS(project_dir=lambda:str(root))
        self.EditorLoadingAndSavingUtils=NS(get_dirty_content_packages=lambda:self.dirty,get_dirty_map_packages=lambda:self.dirty_maps)
    def get_editor_subsystem(self,kind):
        if kind=='level':return NS(is_in_play_in_editor=lambda:self.playing)
        if kind=='editor':return NS(get_editor_world=lambda:self.world)
        assert kind=='actors';return NS(get_selected_level_actors=lambda:self.selected,get_all_level_actors=lambda:self.actors)
    def ScopedEditorTransaction(self,name):return Transaction(self,name)
    def load_asset(self,path):return self.objects.get(path)
    def add(self,path,kind,**props):
        obj=Object(path,kind,**props);self.objects[path]=obj
        file=self.root/('Content/'+path.split('.')[0][6:]+'.uasset');file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(('Opaque '+path).encode())
        return obj


class LevelMaterialsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.game=self.root/'game';(self.game/'Content/Maps').mkdir(parents=True)
        write_json(self.game/'Game.uproject',dict(FileVersion=3,EngineAssociation='5.8'))
        self.map=self.game/'Content/Maps/Garden.umap';self.map.write_bytes(b'opaque map')
        self.u=Editor(self.game)
        self.base=self.u.add(BASE,'Material');self.old=self.u.add(OLD,'MaterialInstanceConstant')
        self.new=self.u.add(NEW,'MaterialInstanceConstant');self.foreign=self.u.add(FOREIGN,'MaterialInstanceConstant')
        slots=[Object('','Slot',material_slot_name=n,material_interface=self.base) for n in ('Stone','Trim')]
        mesh=self.u.add(MESH,'StaticMesh',static_materials=slots)
        self.actor=Actor(self.u,'Wall_1',mesh);self.other=Actor(self.u,'Wall_2',mesh,2,[None,self.old])
        self.u.actors=[self.actor,self.other];self.u.selected=[self.actor,self.other]
        self.capture=self.root/'capture.json';self.plan_path=self.root/'plan.json';self.out=self.root/'apply'
    @property
    def component(self):return self.actor.components[0]
    def plan(self, two=False):
        capture=inspect_selection(self.capture,unreal_module=self.u)
        assignments=[dict(component=self.component.path,slot=1,material=NEW)]
        if two:assignments.append(dict(component=self.other.components[0].path,slot=0,material=NEW))
        plan=make_plan(capture,assignments);write_json(self.plan_path,plan);return plan
    def apply(self):return execute(self.plan_path,self.out,apply=True,unreal_module=self.u)
    def undo(self,name='restore'):return restore(self.out,self.root/name,apply=True,unreal_module=self.u)
    def test_read_only_capture_and_deterministic_plan_preserve_inherited_slots(self):
        plan=self.plan();capture=json.loads(self.capture.read_text())
        self.assertEqual(plan,make_plan(capture,plan['assignments']))
        self.assertEqual(plan['operations'][0]['before']['overrides'],[])
        self.assertEqual(plan['operations'][0]['after']['overrides'],[None,NEW])
        self.assertEqual(self.component.writes,0);self.assertEqual(self.u.transactions,[])
    def test_apply_restore_exact_override_array_and_unselected_actor(self):
        before=digest(self.map);mesh_before=digest(self.game/'Content/Props/Wall.uasset');self.plan()
        result=self.apply();self.assertEqual(result['status'],'applied_review_required',result)
        self.assertEqual(self.component.properties['override_materials'],[None,self.new])
        self.assertEqual(self.other.components[0].writes,0)
        restored=self.undo();self.assertEqual(restored['status'],'restored_review_required',restored)
        self.assertEqual(self.component.properties['override_materials'],[])
        self.assertEqual(digest(self.map),before);self.assertEqual(digest(self.game/'Content/Props/Wall.uasset'),mesh_before)
        self.assertEqual(len(self.u.transactions),2)
    def test_existing_null_holes_and_overrides_restore_without_losing_inheritance(self):
        self.component.properties['override_materials']=[None,self.old];self.plan();self.apply();self.undo()
        self.assertEqual(self.component.properties['override_materials'],[None,self.old])
        self.assertIs(self.component.get_material(0),self.base)
    def test_skeletal_component_uses_same_reversible_path(self):
        mesh=self.u.add('/Game/Cat.Cat','SkeletalMesh',materials=self.component.mesh.properties['static_materials'])
        self.actor.components=[Component(self.actor,mesh)];self.plan()
        self.assertEqual(self.apply()['status'],'applied_review_required');self.assertEqual(self.undo()['status'],'restored_review_required')
    def test_dry_run_needs_no_editor_and_never_owns_changes(self):
        self.plan();result=execute(self.plan_path,self.out)
        self.assertEqual(result['status'],'planned');self.assertEqual(result['attempted'],[])
        self.assertEqual(restore(self.out,self.root/'dry')['status'],'planned');self.assertEqual(self.component.writes,0)
    def test_duplicate_noop_unknown_component_and_invalid_slot_refused(self):
        plan=self.plan();capture=plan['capture'];original=plan['assignments'][0]
        for changes in ({'material':BASE},{'component':'unknown'},{'slot':True},{'slot':2}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):make_plan(capture,[{**original,**changes}])
        with self.assertRaises(ValueError):make_plan(capture,[original,original])
    def test_capture_rejects_dynamic_material_construction_components_and_empty_selection(self):
        for case in ('dynamic','construction','empty','streaming','external'):
            with self.subTest(case=case):
                self.u.selected=[self.actor];self.component.properties['creation_method']='native';self.component.properties['override_materials']=[];self.actor.level.path=WORLD+':PersistentLevel';self.actor.properties['external']=False
                if case=='dynamic':self.component.properties['override_materials']=[Object('/Engine/Transient.MID','MaterialInstanceDynamic')]
                if case=='construction':self.component.properties['creation_method']='simple_construction_script'
                if case=='empty':self.u.selected=[]
                if case=='external':self.actor.properties['external']=True
                if case=='streaming':self.actor.level.path='/Game/Maps/Sub.Sub:PersistentLevel'
                with self.assertRaises(ValueError):inspect_selection(self.capture,unreal_module=self.u)
                self.assertFalse(self.capture.exists())
    def test_pie_dirty_map_and_dirty_content_block_capture(self):
        for field,value in [('playing',True),('dirty_maps',[Object('map','Package')]),('dirty',[Object('asset','Package')])]:
            setattr(self.u,field,value)
            with self.assertRaises(ValueError):inspect_selection(self.capture,unreal_module=self.u)
            setattr(self.u,field,False if field=='playing' else [])
    def test_map_and_asset_and_plan_drift_fail_offline(self):
        plan=self.plan()
        for path in (self.map,self.game/'Content/Materials/Candidate.uasset'):
            original=path.read_bytes();path.write_bytes(b'changed')
            with self.subTest(path=path),self.assertRaises(ValueError):load_plan(self.plan_path)
            path.write_bytes(original)
        plan['operations'][0]['after']['overrides']=[];write_json(self.plan_path,plan)
        with self.assertRaises(ValueError):load_plan(self.plan_path)
    def test_wrong_world_pie_dirty_maps_and_missing_candidate_do_not_mutate(self):
        self.plan()
        for case in ('map','pie','dirty','missing'):
            if case=='map':self.u.world.path='/Game/Maps/Other.Other'
            if case=='pie':self.u.playing=True
            if case=='dirty':self.u.dirty_maps=[Object('map','Package')]
            if case=='missing':del self.u.objects[NEW]
            result=execute(self.plan_path,self.root/case,apply=True,unreal_module=self.u)
            self.assertEqual(result['status'],'failed');self.assertEqual(result['attempted'],[])
            self.u.world.path=WORLD;self.u.playing=False;self.u.dirty_maps=[]
        self.assertEqual(self.component.writes,0)
    def test_guid_mesh_slot_or_effective_material_changes_block_all_targets(self):
        self.plan(two=True);component=self.other.components[0]
        component.properties['override_materials']=[self.foreign,self.old]
        result=self.apply();self.assertEqual(result['status'],'failed');self.assertEqual(self.component.writes,0)
        self.assertEqual(component.writes,0)
    def test_same_actor_path_with_different_guid_is_not_the_original(self):
        self.plan();self.actor.properties['actor_guid']=NS(to_string=lambda:'f'*32)
        self.assertEqual(self.apply()['status'],'failed');self.assertEqual(self.component.writes,0)
    def test_intent_is_persisted_before_each_mutation_and_recovery_handles_interruption(self):
        self.plan()
        def crash(value):
            receipt=json.loads((self.out/'operation.json').read_text())
            self.assertEqual(receipt['attempted'],[self.component.path])
            self.component.properties['override_materials']=value
            raise KeyboardInterrupt('simulate interruption after mutation')
        self.component.on_write=crash
        with self.assertRaises(KeyboardInterrupt):self.apply()
        self.component.on_write=None
        self.assertEqual(operation(self.out)[1]['status'],'applying')
        self.assertEqual(self.undo()['status'],'restored_review_required');self.assertEqual(self.component.properties['override_materials'],[])
    def test_partial_batch_failure_rolls_back_only_attempted_known_states(self):
        self.plan(two=True)
        def fail(value):raise RuntimeError('simulated setter failure')
        self.other.components[0].on_write=fail
        result=self.apply();self.assertEqual(result['status'],'failed',result)
        self.assertFalse(result['recovery_required']);self.assertEqual(self.component.properties['override_materials'],[])
        self.assertEqual(self.other.components[0].properties['override_materials'],[None,self.old])
    def test_unknown_partial_write_is_preserved_for_manual_recovery(self):
        self.plan()
        def foreign(value):
            self.component.properties['override_materials']=[self.foreign]
            raise RuntimeError('unexpected intermediate state')
        self.component.on_write=foreign;result=self.apply()
        self.assertTrue(result['recovery_required']);self.assertEqual(result['conflicts'],[self.component.path])
        self.assertEqual(self.component.properties['override_materials'],[self.foreign])
    def test_restore_preflights_entire_batch_before_touching_any_component(self):
        self.plan(two=True);self.apply();self.other.components[0].properties['override_materials']=[self.foreign,self.old]
        result=self.undo();self.assertEqual(result['status'],'failed')
        self.assertEqual(self.component.properties['override_materials'],[None,self.new]);self.assertEqual(self.component.writes,1)
    def test_restore_after_map_save_and_idempotent_second_restore(self):
        self.plan();self.apply();self.map.write_bytes(b'manually saved candidate map');self.u.dirty_maps=[]
        result=self.undo();self.assertEqual(result['status'],'restored_review_required',result)
        count=self.component.writes;again=self.undo('again')
        self.assertEqual(again['already_original'],[self.component.path]);self.assertEqual(self.component.writes,count)
    def test_restore_does_not_overwrite_new_mesh_or_recreated_actor(self):
        self.plan();self.apply();self.actor.properties['actor_guid']=NS(to_string=lambda:'b'*32)
        result=self.undo();self.assertEqual(result['status'],'failed');self.assertEqual(self.component.writes,1)
    def test_failed_restore_can_resume_from_original_journal(self):
        self.plan(two=True);self.apply()
        def fail(value):raise RuntimeError('transient failure')
        self.component.on_write=fail;first=self.undo()
        self.assertEqual(first['status'],'failed');self.assertEqual(first['restored'],[self.other.components[0].path])
        self.component.on_write=None;second=self.undo('retry')
        self.assertEqual(second['status'],'restored_review_required');self.assertEqual(second['already_original'],[self.other.components[0].path])
    def test_journal_identity_tampering_and_unowned_paths_are_rejected(self):
        self.plan();self.apply();path=self.out/'operation.json';receipt=json.loads(path.read_text())
        for update in ({'plan_identity':'f'*64},{'attempted':['foreign']},{'status':'planned'}):
            write_json(path,{**receipt,**update})
            with self.subTest(update=update),self.assertRaises(ValueError):operation(self.out)
    def test_outputs_are_exclusive_and_outside_project(self):
        self.plan();execute(self.plan_path,self.out)
        with self.assertRaises(FileExistsError):execute(self.plan_path,self.out)
        with self.assertRaises(ValueError):execute(self.plan_path,self.game/'operation')
        with self.assertRaises(FileExistsError):inspect_selection(self.capture,unreal_module=self.u)
    def test_comparison_html_escapes_slot_names_and_has_no_network_resources(self):
        self.component.mesh.properties['static_materials'][1].properties['material_slot_name']='<script>alert(1)</script>'
        plan=self.plan();page=comparison_html(plan)
        self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>',page);self.assertIn(NEW,page);self.assertNotIn('src=',page)
    def test_changed_mesh_and_slot_names_are_not_material_only_edits(self):
        self.plan();original=self.component.mesh
        alternate=self.u.add('/Game/Other.Other','StaticMesh',static_materials=original.properties['static_materials'])
        self.component.properties['static_mesh']=alternate
        result=execute(self.plan_path,self.root/'changed-mesh',apply=True,unreal_module=self.u)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.component.writes,0)
        self.component.properties['static_mesh']=original
        original.properties['static_materials'][1].properties['material_slot_name']='Renamed'
        result=execute(self.plan_path,self.root/'changed-slots',apply=True,unreal_module=self.u)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.component.writes,0)
    def test_silent_setter_failure_is_detected_by_effective_and_override_readback(self):
        self.plan()
        self.component.set_editor_property=lambda name,value:None
        result=self.apply();self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error'],'override_readback_failed');self.assertFalse(result['recovery_required'])
    def test_lfs_map_pointer_is_rejected(self):
        self.map.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:'+'0'*64+'\nsize 10\n')
        with self.assertRaisesRegex(ValueError,'downloaded'):inspect_selection(self.capture,unreal_module=self.u)
    def test_unrelated_actor_transform_edits_are_preserved_during_restore(self):
        self.plan();self.apply();self.actor.properties['test_location']=[10,20,30]
        result=self.undo();self.assertEqual(result['status'],'restored_review_required')
        self.assertEqual(self.actor.properties['test_location'],[10,20,30])
    def test_repeated_slot_names_are_safe_because_assignments_use_pinned_indices(self):
        for slot in self.component.mesh.properties['static_materials']:
            slot.properties['material_slot_name']='None'
        self.plan();result=self.apply();self.assertEqual(result['status'],'applied_review_required')
        self.assertIs(self.component.get_material(0),self.base);self.assertIs(self.component.get_material(1),self.new)
        self.assertEqual(self.undo()['status'],'restored_review_required')
    def test_offline_cli_creates_reviewable_json_and_html(self):
        plan=self.plan();assignments=self.root/'assignments.json';write_json(assignments,plan['assignments'])
        import os
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        result=subprocess.run([sys.executable,'-m','cryptonyan_asset_studio.level_materials',str(self.capture),str(assignments),'--output',str(self.root/'cli.json'),'--html',str(self.root/'review.html')],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(load_plan(self.root/'cli.json'),plan);self.assertTrue((self.root/'review.html').is_file())


if __name__=='__main__':unittest.main()
