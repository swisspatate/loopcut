# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual CPU chains, stdio, interruption guards and optional Blender pipelines."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import agent_connect as connect, capabilities as caps, studio_workflows as workflows
from cryptonyan_asset_studio import studio_service as studio
from cryptonyan_asset_studio.executors import checkpoint
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.materials import pack_material
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.png_pixels import decode
from cryptonyan_asset_studio.storage import digest, write_json
from test_cryptonyan_agent_connect import LocalPeer
from test_cryptonyan_camera_moves import recipe as camera_recipe
from test_cryptonyan_comparison import spec as comparison_recipe, MAP, MESH, MAT, SKIN
from test_cryptonyan_materials import png
from test_cryptonyan_image_workshop import recipe as image_recipe
from test_cryptonyan_modular_levels import recipe as level_recipe, catalog as level_catalog
from test_cryptonyan_rig_repair import SPEC as RIG_SPEC, POLICY as RIG_POLICY
BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')


def workflow():
    return dict(schema=workflows.SCHEMA,id='two-shots',steps=[dict(id=name,operation='camera_prepare',arguments={'recipe':camera_recipe()}) for name in ('first','second')])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="workflow é '-")
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.assets=self.root/'assets';self.assets.mkdir();self.work=self.root/'work'
        self.service=studio.StudioService(self.work,self.assets);self.addCleanup(self.service.close)
    def submit(self,value=None,name='flow'):
        return self.service.submit(name,'workflow_run',{'workflow':value or workflow()})
    def finish(self,name='flow',timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=self.service.operation(name)
            if value['status'] not in studio.ACTIVE:return value
            threading.Event().wait(.01)
        self.fail('Workflow did not reach a terminal state')
    def execute(self,value=None,name='flow'):
        value=self.service.execute(name,'workflow_run',{'workflow':value or workflow()})
        self.assertEqual(value['status'],'succeeded',value);return value
    def output(self,name='flow'):return self.service.operations/name/'output'
    def material_inputs(self):
        for key,color,rough,normal in (('base',(0,0,0),0,(128,128,255)),('snow',(255,255,255),255,(180,128,244))):
            folder=self.assets/key;folder.mkdir()
            for role,rgb in {'base_color':color,'roughness':(rough,)*3,'normal':normal}.items():(folder/(role+'.png')).write_bytes(png(rgb))
            pack_material(folder,{r:r+'.png' for r in ('base_color','roughness','normal')},self.assets/(key+'-pbr'))
        (self.assets/'mask.png').write_bytes(png((128,)*3))
        def binding(p):return dict(file=p,sha256=digest(self.assets/p))
        recipe=dict(schema='cryptonyan.material-layers/1',id='snow',base=binding('base-pbr/material.json'),layers=[
            dict(id='snow',material=binding('snow-pbr/material.json'),mask=binding('mask.png'),opacity=1,
                 channels=['base_color','roughness','normal'],blend='mix')])
        return dict(recipe=recipe,source_root='asset:')
    def project(self):
        game=self.root/'game';game.mkdir();(game/'Cat.uproject').write_text('{"FileVersion":3}',encoding='utf-8')
        for asset in (MESH,MAT,SKIN):
            p=game/('Content/'+asset[6:].split('.')[0]+'.uasset');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'opaque fixture package')
        path=game/('Content/'+MAP[6:]+'.umap');path.parent.mkdir(parents=True);path.write_bytes(b'opaque fixture map')
        self.service.project=GameProject(game)
    def held_first(self):
        started=threading.Event();release=threading.Event();real=self.service._dispatch
        def dispatch(op,args,paths,output):
            if op!='workflow_run' and output.parent.name in ('first','hold'):
                started.set()
                if not release.wait(5):raise AssertionError('Controlled operation was not released')
            return real(op,args,paths,output)
        p=patch.object(self.service,'_dispatch',side_effect=dispatch);p.start()
        self.addCleanup(p.stop);self.addCleanup(release.set)
        return started,release

    def test_graph_validation_refuses_cycles_nested_workflows_and_unsafe_bindings(self):
        bad=[]
        for name in ('../escape','UPPER','a/b','x'*33,'con','aux','com1','lpt9'):
            value=workflow();value['steps'][0]['id']=name;bad.append(value)
        value=workflow();value['steps'][1]['id']='first';bad.append(value)
        value=workflow();value['steps']*=5;bad.append(value)
        value=workflow();value['steps'][0]['operation']='workflow_run';value['steps'][0]['arguments']={'workflow':workflow()};bad.append(value)
        for earlier,file in (('later',''),('first','../outside'),('first','/absolute'),('first','a\\b'),('first','a:b')):
            value=workflow();value['steps'][1].update(operation='layers_compose',arguments={'bundle':dict(from_step=earlier,file=file)});bad.append(value)
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):workflows.validate(value)
        self.assertEqual(list(self.service.operations.iterdir()),[])

    def test_schema_and_guidance_advertise_bindings_and_all_templates(self):
        schema=workflows.schema();self.assertEqual(schema['properties']['steps']['maxItems'],8)
        self.assertEqual(len(schema['properties']['steps']['items']['oneOf']),18)
        guide=caps.guide('workflow_automation');self.assertEqual(guide['workflow_schema'],schema)
        self.assertEqual(len(guide['workflow_templates']['templates']),5)
        self.assertEqual(caps.route('Enchaîne plusieurs opérations avec un workflow Studio.')['primary'],'workflow_automation')
        self.assertEqual(caps.route('Chain operations in a Studio workflow.')['primary'],'workflow_automation')
        names={t['name'] for t in tool_list(studio=True)};self.assertIn('studio_workflow_template',names)

    def test_templates_copy_explicit_inputs_without_execution(self):
        cases=dict(camera_preview={'recipe':camera_recipe()},material_layers={'recipe':{},'source_root':'asset:'},
                   modular_preview={'recipe':{},'catalog':{},'source_root':'asset:'},image_preview={'reference':'asset:ref.png','recipe':{},'source_root':'asset:'},
                   rig_repair_copy={'source':'asset:rig.blend','specification':RIG_SPEC,'policy':RIG_POLICY})
        for template,inputs in cases.items():
            result=self.service.workflow_template(template,inputs);value=result['workflow']
            self.assertFalse(result['execution_started']);self.assertFalse(result['domain_recipes_validated'])
            self.assertEqual([s['operation'] for s in value['steps']],workflows.TEMPLATE_OPERATIONS[template])
            self.assertEqual(workflows.validate(value),value)
        with self.assertRaises(ValueError):self.service.workflow_template('shell',{})
        with self.assertRaises(ValueError):self.service.workflow_template('camera_preview',dict(recipe={},command='ignored'))
        self.assertEqual(list(self.service.operations.iterdir()),[])

    def test_real_cli_builds_and_validates_a_workflow_without_running_it(self):
        inputs=self.root/'inputs.json';write_json(inputs,{'recipe':camera_recipe()})
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        base=[sys.executable,'-m','cryptonyan_asset_studio.studio_workflows']
        result=subprocess.run(base+['make','camera_preview',str(inputs)],env=env,capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);value=json.loads(result.stdout);path=self.root/'workflow.json';write_json(path,value)
        result=subprocess.run(base+['validate',str(path)],env=env,capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(json.loads(result.stdout)['execution_started'])

    def test_real_cpu_steps_have_durable_journals_progress_and_verified_artifacts(self):
        record=self.execute();self.assertEqual(record['workflow']['completed_steps'],2)
        self.assertEqual(record['workflow']['status'],'succeeded');self.assertIsNone(record['workflow']['current_step'])
        result=json.loads(self.service.artifact('flow','output/workflow-status.json')['text'])
        self.assertEqual([s['status'] for s in result['steps']],['succeeded','succeeded'])
        child=json.loads(self.service.artifact('flow','output/steps/first/step.json')['text'])
        self.assertEqual(child['status'],'succeeded');self.assertTrue(child['artifacts'])
        with patch.object(self.service,'_dispatch',side_effect=AssertionError('must not retry')):
            self.assertEqual(self.submit(),record)
        self.assertEqual(list(self.assets.iterdir()),[])

    def test_real_pbr_chain_binds_frozen_maps_and_keeps_sources_unchanged(self):
        value=workflows.make_template('material_layers',self.material_inputs())
        before={p.relative_to(self.assets).as_posix():digest(p) for p in self.assets.rglob('*') if p.is_file()}
        self.execute(value);folder=self.output()/'steps/compose/output'
        self.assertEqual(tuple(decode((folder/'base_color.png').read_bytes())[1][:3]),(188,)*3)
        self.assertEqual(tuple(decode((folder/'roughness.png').read_bytes())[1][:3]),(128,)*3)
        bound=json.loads((self.output()/'steps/compose/request.json').read_text(encoding='utf-8'))['arguments']['bundle']
        self.assertEqual(bound,'work:studio/operations/flow/output/steps/prepare/output')
        self.assertEqual(before,{p.relative_to(self.assets).as_posix():digest(p) for p in self.assets.rglob('*') if p.is_file()})

    def test_all_prerequisites_are_checked_before_creating_a_job(self):
        value=workflows.make_template('camera_preview',{'recipe':camera_recipe()})
        with self.assertRaises(ValueError):self.submit(value)
        value=workflow();value['steps'][1].update(operation='layers_compose',arguments={'bundle':'asset:missing'})
        with self.assertRaises(ValueError):self.submit(value)
        value=workflow();value['steps'][1].update(operation='comparison_plan',arguments={'recipe':{}})
        with self.assertRaises(ValueError):self.submit(value)
        self.assertEqual(list(self.service.operations.iterdir()),[])

    def test_completed_retry_uses_the_frozen_result_after_sources_are_removed(self):
        value=workflows.make_template('material_layers',self.material_inputs());result=self.execute(value)
        for path in self.assets.iterdir():
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink()
        with patch.object(self.service,'_dispatch',side_effect=AssertionError('must not execute again')):
            self.assertEqual(self.submit(value),result)

    def test_result_check_shape_is_closed_and_bounded(self):
        for check in (dict(path=[],equals=0),dict(path=['x'],equals={}),dict(path=['x'],equals=[]),
                      dict(path=['x.y'],equals=0),dict(path=['x'],equals='x'*257),dict(path=['x'],equals=0,command='no')):
            value=workflow();value['steps'][0]['checks']=[check]
            with self.subTest(check=check),self.assertRaises(ValueError):workflows.validate(value)
        value=workflow();value['steps'][0]['checks']=[dict(path=['x'],equals=0)]*9
        with self.assertRaises(ValueError):workflows.validate(value)

    def test_path_lists_resolve_only_verified_previous_step_outputs(self):
        self.project();write_json(self.assets/'plan.json',{})
        value=workflow();value['steps'].append(dict(id='compare',operation='comparison_gallery',arguments={
            'plan':'asset:plan.json','captures':[dict(from_step='first',file=''),dict(from_step='second',file='')]}))
        real=self.service._dispatch;captures=[]
        def dispatch(op,args,paths,output):
            if op!='comparison_gallery':return real(op,args,paths,output)
            captures.extend(paths['captures']);output.mkdir();write_json(output/'comparison.json',{'fixture':True});return {'fixture':True}
        with patch.object(self.service,'_dispatch',side_effect=dispatch):self.execute(value)
        self.assertEqual(captures,[self.output()/'steps/first/output',self.output()/'steps/second/output'])

    def test_configuration_changes_between_steps_block_the_next_operation(self):
        original=self.service._workflow_progress
        def progress(folder,value):
            original(folder,value)
            if value['completed_steps']==1:self.service.blender=Path(sys.executable).resolve()
        with patch.object(self.service,'_workflow_progress',side_effect=progress):self.submit();result=self.finish()
        self.assertEqual(result['status'],'failed');self.assertEqual(result['workflow']['steps'][1]['status'],'failed')
        self.assertFalse((self.output()/'steps/second/output').exists())

    def test_failed_first_step_blocks_every_following_step_and_is_not_retried(self):
        value=workflow();value['steps'][0]['arguments']['recipe']={'invalid':'recipe'}
        self.submit(value);result=self.finish();self.assertEqual(result['status'],'failed')
        self.assertEqual([s['status'] for s in result['workflow']['steps']],['failed','blocked'])
        self.assertFalse((self.output()/'steps/second').exists())
        self.assertEqual(self.submit(value),result)

    def test_explicit_result_check_can_reject_a_completed_audit(self):
        value=workflow();value['steps'][0]['checks']=[dict(path=['recipe','fps'],equals=999)]
        self.submit(value);result=self.finish();self.assertEqual(result['error'],'WorkflowRejected')
        self.assertEqual([s['status'] for s in result['workflow']['steps']],['rejected','blocked'])
        self.assertEqual(result['workflow']['steps'][0]['checks'],[dict(path=['recipe','fps'],matched=False)])
        self.assertTrue((self.output()/'steps/first/output/cinematic.json').is_file());self.assertEqual(result['artifacts'],[])

    def test_result_checks_distinguish_boolean_number_and_missing_fields(self):
        real=self.service._dispatch
        def dispatch(op,args,paths,output):
            if op=='workflow_run':return real(op,args,paths,output)
            output.mkdir();write_json(output/'report.json',{'ready':True});return {'ready':True,'array':[False]}
        with patch.object(self.service,'_dispatch',side_effect=dispatch):
            for i,(path,expected,passed) in enumerate(((['ready'],True,True),(['ready'],1,False),(['absent'],None,False),(['array','0'],False,True))):
                value=workflow();value['steps'][0]['checks']=[dict(path=path,equals=expected)]
                self.submit(value,'checks-'+str(i));result=self.finish('checks-'+str(i))
                self.assertEqual(result['status'],'succeeded' if passed else 'failed',result)

    def test_running_cancellation_stops_before_the_next_step(self):
        started,release=self.held_first();self.submit();self.assertTrue(started.wait(2))
        record=self.service.operation('flow');self.assertEqual(record['workflow']['current_step'],'first')
        self.assertEqual(record['phase'],'workflow');self.assertEqual(self.service.cancel('flow')['status'],'cancelling')
        release.set();result=self.finish();self.assertEqual(result['status'],'cancelled')
        self.assertEqual([s['status'] for s in result['workflow']['steps']],['cancelled','blocked'])
        self.assertFalse((self.output()/'steps/second').exists())

    def test_cancelling_a_queued_workflow_never_starts_any_step(self):
        started,release=self.held_first();self.service.submit('hold','camera_prepare',{'recipe':camera_recipe()});self.assertTrue(started.wait(2))
        self.submit();result=self.service.cancel('flow');self.assertEqual(result['status'],'cancelled')
        self.assertEqual(result['workflow']['status'],'cancelled')
        self.assertTrue(all(s['status']=='blocked' for s in result['workflow']['steps']))
        self.assertFalse(self.output().exists());release.set()

    def test_early_cancel_or_configuration_failure_blocks_unstarted_steps(self):
        original=self.service._run
        for mode in ('cancel','configuration'):
            entered=threading.Event();start=threading.Event();self.service.blender=None
            def gated(*args):
                entered.set()
                if not start.wait(5):raise AssertionError('Worker start was not released')
                return original(*args)
            with patch.object(self.service,'_run',side_effect=gated):
                try:
                    self.submit(name=mode);self.assertTrue(entered.wait(2))
                    if mode=='cancel':self.assertEqual(self.service.cancel(mode)['status'],'cancelling')
                    else:self.service.blender=Path(sys.executable).resolve()
                    start.set();result=self.finish(mode)
                    self.assertEqual(result['status'],'cancelled' if mode=='cancel' else 'failed')
                    self.assertTrue(all(s['status']=='blocked' for s in result['workflow']['steps']),result)
                    self.assertFalse(self.output(mode).exists())
                finally:start.set()

    def test_total_execution_budget_is_shared_by_all_steps(self):
        real=self.service._dispatch
        def dispatch(op,args,paths,output):
            if op=='workflow_run':return real(op,args,paths,output)
            while True:checkpoint();threading.Event().wait(.005)
        with patch.object(self.service,'_dispatch',side_effect=dispatch),patch.object(studio,'EXECUTION_SECONDS',.05):
            self.submit();result=self.finish()
        self.assertEqual(result['status'],'timed_out');self.assertEqual(result['workflow']['steps'][1]['status'],'blocked')

    def test_modified_added_and_replaced_upstream_outputs_block_a_consumer(self):
        value=workflows.make_template('material_layers',self.material_inputs());original=self.service._workflow_progress
        for index,mode in enumerate(('changed','added','receipt','symlink')):
            name='tamper-'+str(index);changed=[]
            def progress(folder,record):
                original(folder,record)
                if record['completed_steps']==1 and record['current_step']=='prepare' and not changed:
                    changed.append(True);step=folder/'output/steps/prepare';target=next((step/'output').glob('*.json'))
                    if mode=='added':(step/'output/extra.txt').write_text('extra',encoding='utf-8')
                    elif mode=='receipt':
                        receipt=json.loads((step/'step.json').read_text(encoding='utf-8'));receipt['status']='changed';write_json(step/'step.json',receipt)
                    elif mode=='symlink':
                        outside=self.root/('outside-'+str(index));outside.write_text('{}',encoding='utf-8');target.unlink()
                        try:target.symlink_to(outside)
                        except OSError:target.write_text('{}',encoding='utf-8')
                    else:target.write_text('{}',encoding='utf-8')
            with patch.object(self.service,'_workflow_progress',side_effect=progress):self.submit(value,name);result=self.finish(name)
            self.assertEqual(result['status'],'failed',result)
            self.assertFalse((self.output(name)/'steps/compose/output').exists())

    def test_a_missing_bound_file_fails_without_invoking_the_consumer(self):
        original=self.service._workflow_progress;dispatch=self.service._dispatch
        def progress(folder,value):
            original(folder,value)
            if value['completed_steps']==1:(folder/'output/steps/first/output/empty').mkdir(exist_ok=True)
        for file in ('missing','empty'):
            value=workflow();value['steps'][1].update(operation='layers_compose',arguments={'bundle':dict(from_step='first',file=file)})
            with patch.object(self.service,'_workflow_progress',side_effect=progress),patch.object(self.service,'_dispatch',wraps=dispatch) as called:
                self.submit(value,file);result=self.finish(file)
                self.assertFalse(any(c.args[0]=='layers_compose' for c in called.call_args_list))
            self.assertEqual(result['status'],'failed');self.assertEqual(result['workflow']['completed_steps'],1)
            self.assertFalse((self.output(file)/'steps/second/output').exists())

    def test_final_verification_detects_a_consumer_modifying_its_input(self):
        value=workflows.make_template('material_layers',self.material_inputs());real=self.service._dispatch
        def dispatch(op,args,paths,output):
            result=real(op,args,paths,output)
            if op=='layers_compose':next(paths['bundle'].glob('*.json')).write_text('{}',encoding='utf-8')
            return result
        with patch.object(self.service,'_dispatch',side_effect=dispatch):self.submit(value);result=self.finish()
        self.assertEqual(result['status'],'failed');self.assertEqual(result['artifacts'],[])

    def test_literal_recipe_text_is_never_interpolated_as_a_binding(self):
        value=workflow();value['steps'][0]['arguments']['recipe']['note']='{{steps.first.output}} $(whoami)'
        # A domain schema error, not a template evaluation or command execution.
        self.submit(value);result=self.finish();self.assertEqual(result['status'],'failed')
        captured=json.loads((self.output()/'steps/first/request.json').read_text(encoding='utf-8'))
        self.assertEqual(captured['arguments']['recipe']['note'],'{{steps.first.output}} $(whoami)')

    def test_restart_marks_parent_and_step_journals_interrupted_without_resuming(self):
        value=workflow();value['steps'].append(dict(id='third',operation='camera_prepare',arguments={'recipe':camera_recipe()}));self.execute(value)
        root=self.service.operations/'flow';receipt=json.loads((root/'operation.json').read_text(encoding='utf-8'));receipt['status']='running';write_json(root/'operation.json',receipt)
        status=json.loads((self.output()/'workflow-status.json').read_text(encoding='utf-8'));status.update(status='running',current_step='second')
        status['steps'][1]['status']='running';status['steps'][2]['status']='pending';write_json(self.output()/'workflow-status.json',status)
        step=self.output()/'steps/second/step.json';record=json.loads(step.read_text(encoding='utf-8'));record['status']='running';write_json(step,record)
        shutil.rmtree(self.output()/'steps/third');self.service.close()
        with patch.object(studio.StudioService,'_dispatch',side_effect=AssertionError('not resumed')):
            with studio.StudioService(self.work,self.assets) as reopened:
                result=reopened.submit('flow','workflow_run',{'workflow':value})
                self.assertEqual(result['status'],'interrupted');self.assertEqual(result['workflow']['status'],'interrupted')
                self.assertEqual([s['status'] for s in result['workflow']['steps']],['succeeded','interrupted','blocked'])
                self.assertEqual(json.loads(step.read_text(encoding='utf-8'))['status'],'interrupted')

    def test_prepared_comparison_binds_its_plan_to_an_inert_unreal_handoff(self):
        self.project();value=dict(schema=workflows.SCHEMA,id='comparison',steps=[
            dict(id='plan',operation='comparison_plan',arguments={'recipe':comparison_recipe()}),
            dict(id='handoff',operation='unreal_handoff',arguments={'kind':'comparison_stage','plan':dict(from_step='plan',file='plan.json')})])
        self.execute(value)
        source=self.service.artifact('flow','output/steps/handoff/output/unreal-handoff.py')['text']
        self.assertIn('comparison.create',source);self.assertFalse((self.output()/'steps/handoff/output/editor-result').exists())
        self.assertFalse(self.service.operation('flow')['engine_validated'])

    def test_real_stdio_builds_submits_and_reads_a_complete_workflow(self):
        path=self.root/'connection.json';connect.save_config(path,dict(schema=connect.SCHEMA,executor='mock',python=sys.executable,
            workspace=str(self.root/'peer'),asset_root=str(self.assets),blender='',comfy_profiles='',game_project=''))
        peer=LocalPeer(path,'codex');self.addCleanup(peer.close);peer.call('initialize')
        built=peer.tool('studio_workflow_template',dict(template='material_layers',inputs=self.material_inputs()))
        self.assertFalse(built['execution_started']);args=dict(request_id='stdio',operation='workflow_run',arguments={'workflow':built['workflow']})
        self.assertEqual(peer.tool('studio_submit',args)['status'],'queued')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=peer.tool('studio_operation',{'request_id':'stdio'})
            if result['status'] not in studio.ACTIVE:break
            threading.Event().wait(.01)
        self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual(peer.tool('studio_submit',args)['workflow']['completed_steps'],2)
        artifact=peer.tool('studio_artifact',dict(request_id='stdio',file='output/workflow-status.json'))
        self.assertEqual(json.loads(artifact['text'])['status'],'succeeded')

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_real_blender_camera_template_runs_both_steps_on_the_existing_queue(self):
        self.service.blender=Path(BLENDER).resolve();value=workflows.make_template('camera_preview',{'recipe':camera_recipe()})
        self.submit(value);result=self.finish(timeout=30);self.assertEqual(result['status'],'succeeded',result)
        self.assertTrue((self.output()/'steps/preview/output/camera-preview.blend').is_file())
        self.assertEqual(result['workflow']['completed_steps'],2);self.assertFalse(result['visual_quality_validated'])

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_real_blender_modular_template_uses_actual_frozen_glb_modules(self):
        self.service.blender=Path(BLENDER).resolve();source=self.assets/'kit';source.mkdir();catalog=level_catalog(source)
        value=workflows.make_template('modular_preview',dict(recipe=level_recipe(),catalog=catalog,source_root='asset:kit'))
        self.submit(value);result=self.finish(timeout=30);self.assertEqual(result['status'],'succeeded',result)
        self.assertTrue(list((self.output()/'steps/preview/output').glob('*.blend')))

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_real_blender_rig_template_creates_only_a_verified_candidate_copy(self):
        self.service.blender=Path(BLENDER).resolve();source=self.assets/'rig.blend'
        command=[BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1','--python',
                 str(ROOT/'loopcut/harness/cryptonyan_rig_fixture.py'),'--',str(source),'--repair']
        result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30);self.assertEqual(result.returncode,0)
        before=digest(source);value=workflows.make_template('rig_repair_copy',dict(source='asset:rig.blend',specification=RIG_SPEC,
            policy={'max_influences':4,'max_removed_fraction':.25}))
        self.submit(value);result=self.finish(timeout=30);self.assertEqual(result['status'],'succeeded',result)
        report=json.loads((self.output()/'steps/repair/result.json').read_text(encoding='utf-8'))
        self.assertTrue(report['verified_after_reopen']);self.assertEqual(digest(source),before)
        self.assertTrue((self.output()/'steps/repair/output/candidate.blend').is_file())

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_real_blender_image_template_renders_and_exports_an_explicit_recipe(self):
        self.service.blender=Path(BLENDER).resolve();reference=self.assets/'reference.png'
        reference.write_bytes(png(width=64,height=64));before=digest(reference)
        value=workflows.make_template('image_preview',dict(reference='asset:reference.png',recipe=image_recipe(),source_root='asset:'))
        self.submit(value);result=self.finish(timeout=60);self.assertEqual(result['status'],'succeeded',result)
        output=self.output()/'steps/build/output'
        self.assertTrue((output/'render.png').is_file());self.assertTrue(list(output.glob('*.glb')))
        self.assertEqual(digest(reference),before);self.assertFalse(result['engine_validated'])


if __name__=='__main__':unittest.main()
