# SPDX-License-Identifier: GPL-3.0-or-later
"""Verified failed-step inspection and explicit prefix reuse, CPU/stdio/Blender."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import test_cryptonyan_studio_workflows as fixtures
from cryptonyan_asset_studio import agent_connect as connect, studio_workflows as workflows, studio_service as studio
from cryptonyan_asset_studio import studio_recovery as recovery
from cryptonyan_asset_studio import executors
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.png_pixels import decode
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.storage import digest, write_json


class ReuseTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    material_inputs=fixtures.WorkflowTests.material_inputs
    project=fixtures.WorkflowTests.project
    output=fixtures.WorkflowTests.output
    finish=fixtures.WorkflowTests.finish

    def run_flow(self, value, name='flow'):
        return self.service.execute(name,'workflow_run',{'workflow':value})

    def failed(self):
        value=fixtures.workflow();value['steps'][1]['arguments']['recipe']={}
        self.assertEqual(self.run_flow(value)['status'],'failed')
        return self.service.workflow_inspect('flow')['workflow']

    def fixed(self):
        value=self.failed();value['steps'][1]['arguments']['recipe']=fixtures.camera_recipe()
        return value

    def fork(self,value,count=1,source='flow'):
        return self.service.workflow_fork(source,value,count)['workflow']

    def test_failed_parent_exposes_only_verified_step_snapshots(self):
        self.failed();result=self.service.workflow_inspect('flow')
        self.assertEqual(result['reusable_prefix_steps'],1);self.assertTrue(result['context_matches'])
        self.assertFalse(result['source_freshness_validated']);self.assertTrue(result['snapshot_reuse_only'])
        self.assertTrue(result['steps'][0]['verified']);self.assertFalse(result['steps'][1]['verified'])
        report=self.service.workflow_step_artifact('flow','first','result.json')
        self.assertEqual(json.loads(report['text'])['recipe']['fps'],30)
        with self.assertRaises(ValueError):self.service.artifact('flow','output/steps/first/result.json')
        with self.assertRaises(ValueError):self.service.workflow_step_artifact('flow','second','result.json')

    def test_new_attempt_reuses_prefix_without_dispatch_and_keeps_original_receipts(self):
        value=self.fixed();original=digest(self.service.operations/'flow/operation.json')
        planned=self.service.workflow_fork('flow',value,1)
        self.assertFalse(planned['execution_started']);self.assertTrue(planned['new_request_id_required'])
        self.assertEqual(len(list(self.service.operations.iterdir())),1)
        with self.assertRaises(ValueError):self.run_flow(planned['workflow'])
        real=self.service._dispatch;calls=[]
        def dispatch(op,args,paths,output):
            calls.append((op,output.parent.name));return real(op,args,paths,output)
        with patch.object(self.service,'_dispatch',side_effect=dispatch):result=self.run_flow(planned['workflow'],'retry')
        self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual([s['status'] for s in result['workflow']['steps']],['reused','succeeded'])
        self.assertEqual(result['workflow']['completed_steps'],2);self.assertEqual(result['workflow']['reused_steps'],1)
        self.assertEqual([op for op,name in calls if op!='workflow_run'],['camera_prepare'])
        self.assertEqual(digest(self.service.operations/'flow/operation.json'),original)
        note=self.service.artifact('retry','output/steps/first/result.json')
        self.assertTrue(json.loads(note['text'])['snapshot_reused'])
        actual=self.service.workflow_step_artifact('retry','first','result.json')
        self.assertEqual(json.loads(actual['text'])['recipe']['fps'],30)

    def test_actual_pbr_composition_uses_frozen_maps_after_original_sources_are_removed(self):
        value=workflows.make_template('material_layers',self.material_inputs())
        value['steps'][1]['arguments']['bundle']['file']='missing'
        self.assertEqual(self.run_flow(value)['status'],'failed')
        value=self.service.workflow_inspect('flow')['workflow'];value['steps'][1]['arguments']['bundle']['file']=''
        for path in self.assets.iterdir():
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink()
        planned=self.fork(value);real=self.service._dispatch
        def dispatch(op,*args):
            if op=='layers_prepare':raise AssertionError('Must reuse the captured maps')
            return real(op,*args)
        with patch.object(self.service,'_dispatch',side_effect=dispatch):result=self.run_flow(planned,'retry')
        self.assertEqual(result['status'],'succeeded',result)
        output=self.output('retry')/'steps/compose/output'
        self.assertEqual(tuple(decode((output/'base_color.png').read_bytes())[1][:3]),(188,)*3)
        self.assertEqual(tuple(decode((output/'roughness.png').read_bytes())[1][:3]),(128,)*3)
        self.assertFalse(read_json(self.service.operations/'retry/result.json')['source_freshness_validated'])

    def test_rejected_quality_check_has_readable_diagnostics_but_cannot_be_reused(self):
        value=fixtures.workflow();value['steps'][0]['checks']=[dict(path=['recipe','fps'],equals=999)]
        result=self.run_flow(value);self.assertEqual(result['error'],'WorkflowRejected')
        inspection=self.service.workflow_inspect('flow');self.assertEqual(inspection['reusable_prefix_steps'],0)
        self.assertTrue(inspection['steps'][0]['verified']);self.assertEqual(inspection['steps'][0]['status'],'rejected')
        self.assertEqual(json.loads(self.service.workflow_step_artifact('flow','first','result.json')['text'])['recipe']['fps'],30)
        with self.assertRaises(ValueError):self.fork(value)
        value['steps'][0]['checks']=[]
        with self.assertRaises(ValueError):self.fork(value)

    def test_changed_prefix_or_gates_are_rejected_but_suffix_can_change(self):
        good=self.fixed()
        for field in ('id','arguments','operation','checks'):
            value=copy.deepcopy(good)
            if field=='id':value['steps'][0][field]='different'
            elif field=='arguments':value['steps'][0][field]['recipe']['fps']=60
            elif field=='operation':value['steps'][0].update(operation='director_plan',arguments={'recipe':{}})
            else:value['steps'][0]['checks']=[dict(path=['recipe','fps'],equals=30)]
            with self.subTest(field=field),self.assertRaises(ValueError):self.fork(value)
        good['id']='new-attempt';good['steps'][1]['arguments']['recipe']['fps']=60
        self.assertEqual(self.run_flow(self.fork(good),'retry')['status'],'succeeded')

    def test_reuse_count_and_descriptor_have_closed_bounded_schemas(self):
        value=self.fixed()
        for count in (0,True,-1,3,9,1.0):
            with self.subTest(count=count),self.assertRaises(ValueError):self.fork(value,count)
        planned=self.fork(value)
        for key,new in (('source_request_id','../bad'),('source_request_identity','bad'),('steps',[]),('extra',True)):
            altered=copy.deepcopy(planned);altered['reuse'][key]=new
            with self.subTest(key=key),self.assertRaises(ValueError):workflows.validate(altered)
        with self.assertRaises(ValueError):self.fork(planned)

    def test_active_and_interrupted_parents_are_never_snapshot_sources(self):
        self.fixed();folder=self.service.operations/'flow';original=read_json(folder/'operation.json')
        for status in ('queued','running','cancelling','interrupted'):
            record=copy.deepcopy(original);record['status']=status;write_json(folder/'operation.json',record)
            inspection=self.service.workflow_inspect('flow');self.assertEqual(inspection['reusable_prefix_steps'],0)
            self.assertFalse(any(s['verified'] for s in inspection['steps']))
            with self.subTest(status=status),self.assertRaises(ValueError):self.fork(inspection['workflow'])
            with self.assertRaises(ValueError):self.service.workflow_step_artifact('flow','first','result.json')
        write_json(folder/'operation.json',original)

    def test_real_cancelled_and_timed_out_parents_can_reuse_the_completed_prefix(self):
        original=self.service._workflow_progress
        for mode in ('cancelled','timed_out'):
            def progress(folder,value):
                original(folder,value)
                if value['completed_steps']==1 and value['current_step']=='first':
                    if mode=='cancelled':self.service.cancel(mode)
                    else:
                        # Expire the actual worker scope only after its first
                        # snapshot is durable, independent of Windows fsync speed.
                        cancelled,_=executors._execution_scope.get()
                        executors._execution_scope.set((cancelled,0))
            with patch.object(self.service,'_workflow_progress',side_effect=progress):
                result=self.run_flow(fixtures.workflow(),mode)
            self.assertEqual(result['status'],mode,result)
            inspection=self.service.workflow_inspect(mode);self.assertEqual(inspection['reusable_prefix_steps'],1)
            self.assertEqual(self.run_flow(self.fork(inspection['workflow'],source=mode),mode+'-retry')['status'],'succeeded')

    def test_changed_artifact_added_file_receipt_or_symlink_blocks_reuse(self):
        value=self.fixed();folder=self.output()/'steps/first';target=folder/'result.json';raw=target.read_bytes()
        for mode in ('changed','added','receipt','symlink'):
            step=read_json(folder/'step.json');extra=folder/'extra.txt';outside=self.root/'outside.json'
            if mode=='changed':target.write_text('{}',encoding='utf-8')
            elif mode=='added':extra.write_text('extra',encoding='utf-8')
            elif mode=='receipt':changed=copy.deepcopy(step);changed['operation']='layers_prepare';write_json(folder/'step.json',changed)
            else:
                target.unlink();outside.write_bytes(raw)
                try:target.symlink_to(outside)
                except OSError:target.write_text('{}',encoding='utf-8')
            with self.subTest(mode=mode),self.assertRaises((ValueError,OSError)):self.fork(value)
            self.assertEqual(self.service.workflow_inspect('flow')['reusable_prefix_steps'],0)
            if target.is_symlink():target.unlink()
            target.write_bytes(raw);extra.unlink(missing_ok=True);write_json(folder/'step.json',step)

    def test_pin_detects_receipt_changes_after_planning_even_if_artifacts_match(self):
        planned=self.fork(self.fixed());path=self.output()/'steps/first/step.json'
        value=read_json(path);value['extra']='changed';write_json(path,value)
        with self.assertRaises(ValueError):self.run_flow(planned,'retry')
        self.assertFalse((self.service.operations/'retry').exists())

    def test_source_is_rechecked_after_waiting_in_the_queue(self):
        planned=self.fork(self.fixed());started=threading.Event();release=threading.Event();real=self.service._dispatch
        def dispatch(op,args,paths,output):
            if output.parent.name=='hold':
                started.set()
                if not release.wait(5):raise AssertionError('Worker was not released')
            return real(op,args,paths,output)
        with patch.object(self.service,'_dispatch',side_effect=dispatch):
            try:
                self.service.submit('hold','camera_prepare',{'recipe':fixtures.camera_recipe()});self.assertTrue(started.wait(2))
                self.service.submit('retry','workflow_run',{'workflow':planned})
                (self.output()/'steps/first/result.json').write_text('{}',encoding='utf-8');release.set()
                self.assertEqual(self.finish('retry')['status'],'failed')
                self.assertFalse((self.output('retry')/'steps/first').exists())
            finally:release.set()

    def test_context_change_blocks_new_reuse_but_preserves_historical_reading(self):
        value=self.fixed();planned=self.fork(value);self.service.blender=Path(sys.executable).resolve()
        inspection=self.service.workflow_inspect('flow');self.assertFalse(inspection['context_matches'])
        self.assertEqual(inspection['reusable_prefix_steps'],0);self.assertTrue(inspection['steps'][0]['verified'])
        self.assertIn('recipe',json.loads(self.service.workflow_step_artifact('flow','first','result.json')['text']))
        with self.assertRaises(ValueError):self.fork(value)
        with self.assertRaises(ValueError):self.run_flow(planned,'retry')

    def test_successful_retry_replay_checks_ancestors_and_never_reexecutes(self):
        planned=self.fork(self.fixed());result=self.run_flow(planned,'retry')
        with patch.object(self.service,'_dispatch',side_effect=AssertionError('No retry execution')):
            self.assertEqual(self.run_flow(planned,'retry'),result)
        (self.output()/'steps/first/output/cinematic.json').write_text('{}',encoding='utf-8')
        for method in (lambda:self.service.operation('retry'),lambda:self.run_flow(planned,'retry'),
                       lambda:self.service.artifact('retry','result.json')):
            with self.assertRaises(ValueError):method()

    def test_derived_forks_have_bounded_verified_lineage_and_require_original_history(self):
        value=self.fixed();source='flow'
        for index in range(recovery.MAX_LINEAGE):
            planned=self.fork(value,source=source);source='retry-'+str(index)
            self.assertEqual(self.run_flow(planned,source)['status'],'succeeded')
            inspection=self.service.workflow_inspect(source);value=inspection['workflow']
            self.assertEqual(inspection['steps'][0]['lineage_depth'],index+1)
        self.assertFalse(inspection['steps'][0]['reusable'])
        with self.assertRaises(ValueError):self.fork(value,source=source)
        shutil.rmtree(self.service.operations/'retry-0')
        with self.assertRaises((ValueError,OSError)):self.service.operation(source)
        self.assertFalse(self.service.workflow_inspect(source)['steps'][0]['verified'])

    def test_legacy_successful_step_receipts_remain_reusable(self):
        value=self.fixed();path=self.output()/'steps/first/step.json';receipt=read_json(path);receipt.pop('execution_completed')
        write_json(path,receipt)
        self.assertEqual(self.run_flow(self.fork(value),'retry')['status'],'succeeded')

    def test_old_unmanifested_failed_outputs_are_not_exposed(self):
        self.failed();folder=self.output()/'steps/second';write_json(folder/'result.json',{'unsafe':'partial'})
        with self.assertRaises(ValueError):self.service.workflow_step_artifact('flow','second','result.json')
        self.assertFalse(self.service.workflow_inspect('flow')['steps'][1]['verified'])

    def test_reused_snapshot_artifacts_count_toward_total_workflow_budget(self):
        planned=self.fork(self.fixed());real=recovery.verify_plan
        def enlarged(*args,**kwargs):
            selected=real(*args,**kwargs)
            for item in selected.values():
                item['origin_receipt']=copy.deepcopy(item['origin_receipt']);item['origin_receipt']['artifacts'][0]['bytes']=2*1024**3+1
            return selected
        with patch.object(recovery,'verify_plan',side_effect=enlarged):result=self.run_flow(planned,'retry')
        self.assertEqual(result['status'],'failed');self.assertFalse((self.output('retry')/'steps/second').exists())

    def test_unreal_handoff_is_regenerated_with_new_destination(self):
        self.project();value=dict(schema=workflows.SCHEMA,id='comparison',steps=[
            dict(id='plan',operation='comparison_plan',arguments={'recipe':fixtures.comparison_recipe()}),
            dict(id='handoff',operation='unreal_handoff',arguments={'kind':'comparison_stage','plan':dict(from_step='plan',file='plan.json')})])
        self.assertEqual(self.run_flow(value)['status'],'succeeded')
        inspection=self.service.workflow_inspect('flow');self.assertEqual(inspection['reusable_prefix_steps'],1)
        with self.assertRaises(ValueError):self.fork(inspection['workflow'],2)
        self.assertEqual(self.run_flow(self.fork(inspection['workflow']),'retry')['status'],'succeeded')
        source=self.service.workflow_step_artifact('retry','handoff','output/unreal-handoff.py')['text']
        self.assertIn(str(self.output('retry')/'steps/handoff/output/editor-result').replace('\\','\\\\'),source)
        self.assertFalse((self.output('retry')/'steps/handoff/output/editor-result').exists())
        self.assertFalse(self.service.operation('retry')['engine_validated'])

    def test_mcp_native_png_and_read_limits_work_with_failed_parent(self):
        reference=self.assets/'reference.png';reference.write_bytes(fixtures.png(width=64,height=64))
        value=fixtures.workflow();value['steps'][0].update(operation='image_prepare',arguments=dict(
            reference='asset:reference.png',recipe=fixtures.image_recipe(),source_root='asset:'))
        value['steps'][1]['arguments']['recipe']={};self.assertEqual(self.run_flow(value)['status'],'failed')
        server=MCPServer(None,studio=self.service)
        server.handle({'jsonrpc':'2.0','id':0,'method':'initialize'})
        result=server.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'studio_workflow_step_artifact',
            'arguments':dict(request_id='flow',step_id='first',file='output/reference.png')}})
        self.assertFalse(result['result']['isError'],result);self.assertEqual(result['result']['content'][0]['type'],'image')
        for file in ('../operation.json','step.json','output/unknown.png'):
            with self.assertRaises(ValueError):self.service.workflow_step_artifact('flow','first',file)
        self.assertEqual(len(tool_list(studio=True)),18)

    def test_full_successful_prefix_can_be_reused_without_any_primitive_execution(self):
        value=workflows.make_template('material_layers',self.material_inputs())
        self.assertEqual(self.run_flow(value)['status'],'succeeded')
        planned=self.fork(self.service.workflow_inspect('flow')['workflow'],2);real=self.service._dispatch
        def dispatch(op,*args):
            if op!='workflow_run':raise AssertionError('No primitive should execute')
            return real(op,*args)
        with patch.object(self.service,'_dispatch',side_effect=dispatch):result=self.run_flow(planned,'retry')
        self.assertEqual(result['status'],'succeeded',result);self.assertEqual(result['workflow']['reused_steps'],2)
        report=self.service.workflow_step_artifact('retry','compose','result.json')
        self.assertIn('text',report)

    def test_successful_parent_manifest_rejects_changed_step_receipt(self):
        self.assertEqual(self.run_flow(fixtures.workflow())['status'],'succeeded')
        path=self.output()/'steps/first/step.json';receipt=read_json(path);receipt['extra']='changed';write_json(path,receipt)
        self.assertEqual(self.service.workflow_inspect('flow')['reusable_prefix_steps'],0)
        with self.assertRaises(ValueError):self.fork(fixtures.workflow())

    def test_real_stdio_inspects_forks_submits_and_reads_failed_parent_reports(self):
        config=self.root/'connection.json';connect.save_config(config,dict(schema=connect.SCHEMA,executor='mock',python=sys.executable,
            workspace=str(self.root/'peer'),asset_root=str(self.assets),blender='',comfy_profiles='',game_project=''))
        peer=fixtures.LocalPeer(config,'codex');self.addCleanup(peer.close);peer.call('initialize')
        value=fixtures.workflow();value['steps'][1]['arguments']['recipe']={}
        self.assertEqual(peer.tool('studio_execute',dict(request_id='bad',operation='workflow_run',arguments={'workflow':value}))['status'],'failed')
        inspection=peer.tool('studio_workflow_inspect',{'request_id':'bad'});self.assertEqual(inspection['reusable_prefix_steps'],1)
        artifact=peer.tool('studio_workflow_step_artifact',dict(request_id='bad',step_id='first',file='result.json'))
        self.assertEqual(json.loads(artifact['text'])['recipe']['fps'],30)
        workflow=inspection['workflow'];workflow['steps'][1]['arguments']['recipe']=fixtures.camera_recipe()
        plan=peer.tool('studio_workflow_fork',dict(source_request_id='bad',workflow=workflow,reuse_steps=1))
        self.assertFalse(plan['execution_started'])
        result=peer.tool('studio_execute',dict(request_id='good',operation='workflow_run',arguments={'workflow':plan['workflow']}))
        self.assertEqual(result['status'],'succeeded',result);self.assertEqual(result['workflow']['reused_steps'],1)

    @unittest.skipUnless(fixtures.BLENDER,'Blender executable unavailable')
    def test_real_blender_reuses_completed_rig_audit_and_repairs_a_candidate_copy(self):
        self.service.blender=Path(fixtures.BLENDER).resolve();source=self.assets/'rig.blend'
        command=[fixtures.BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
            '--python',str(fixtures.ROOT/'loopcut/harness/cryptonyan_rig_fixture.py'),'--',str(source),'--repair']
        created=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30);self.assertEqual(created.returncode,0)
        before=digest(source);value=workflows.make_template('rig_repair_copy',dict(source='asset:rig.blend',specification=fixtures.RIG_SPEC,
            policy={'max_influences':0,'max_removed_fraction':.25}))
        self.assertEqual(self.run_flow(value)['status'],'failed')
        inspection=self.service.workflow_inspect('flow');self.assertEqual(inspection['reusable_prefix_steps'],1)
        value=inspection['workflow'];value['steps'][1]['arguments']['policy']['max_influences']=4
        planned=self.fork(value);real=self.service._dispatch
        def dispatch(op,*args):
            if op=='rig_audit':raise AssertionError('The completed Blender audit must not run again')
            return real(op,*args)
        with patch.object(self.service,'_dispatch',side_effect=dispatch):result=self.run_flow(planned,'retry')
        self.assertEqual(result['status'],'succeeded',result)
        self.assertTrue(read_json(self.output('retry')/'steps/repair/result.json')['verified_after_reopen'])
        self.assertEqual(digest(source),before);self.assertTrue((self.output('retry')/'steps/repair/output/candidate.blend').is_file())


if __name__=='__main__':unittest.main()
