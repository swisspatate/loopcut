# SPDX-License-Identifier: GPL-3.0-or-later
"""Background lifecycle, real stdio, process trees and optional real Blender."""
from concurrent.futures import ThreadPoolExecutor
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
from cryptonyan_asset_studio import agent_connect as connect
from cryptonyan_asset_studio import studio_service as studio
from cryptonyan_asset_studio.executors import ExecutionContext, checkpoint, run_process, stop_process
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.storage import write_json
from test_cryptonyan_agent_connect import LocalPeer
from test_cryptonyan_camera_moves import recipe
BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
ACTIVE=studio.ACTIVE


def wait_for(predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value: return value
        threading.Event().wait(0.01)
    raise AssertionError('Timed out waiting for local worker')


class JobTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="studio jobs é '-")
        self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.assets=self.root/'assets';self.assets.mkdir();self.work=self.root/'work'
        self.service=studio.StudioService(self.work,self.assets);self.addCleanup(self.service.close)
        self.server=MCPServer(None,studio=self.service)
        self.server.handle(dict(jsonrpc='2.0',id=1,method='initialize'))

    def args(self):return dict(recipe=recipe())
    def submit(self,name='shot'):return self.service.submit(name,'camera_prepare',self.args())
    def terminal(self,name='shot'):
        return wait_for(lambda: (v if (v:=self.service.operation(name))['status'] not in ACTIVE else None))
    def tool(self,name,args):
        result=self.server.handle(dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name=name,arguments=args)))['result']
        self.assertFalse(result['isError'],result)
        return json.loads(result['content'][0]['text'])
    def blocked(self):
        started=threading.Event();release=threading.Event();calls=[]
        # Cleanup runs before patch removal and before closing the service.
        real=self.service._dispatch
        def dispatch(op,args,paths,output):
            calls.append(args);started.set()
            if not release.wait(5):raise AssertionError('Test worker was not released')
            return real(op,args,paths,output)
        mock=patch.object(self.service,'_dispatch',side_effect=dispatch);mock.start()
        self.addCleanup(mock.stop);self.addCleanup(release.set)
        return started,release,calls

    def test_submit_keeps_mcp_responsive_and_reports_real_queue_states(self):
        started,release,calls=self.blocked()
        first=self.tool('studio_submit',dict(request_id='one',operation='camera_prepare',arguments=self.args()))
        self.assertEqual(first['status'],'queued');self.assertTrue(started.wait(2))
        second=self.submit('two');self.assertEqual(second['status'],'queued')
        self.assertEqual(self.tool('studio_operation',{'request_id':'one'})['status'],'running')
        history=self.tool('studio_jobs',{'limit':20})
        self.assertEqual(history['counts'],{'running':1,'queued':1});self.assertFalse(history['artifacts_verified'])
        self.assertEqual(self.server.handle(dict(jsonrpc='2.0',id=3,method='ping'))['result'],{})
        release.set();self.assertEqual(self.terminal('one')['status'],'succeeded')
        self.assertEqual(self.terminal('two')['status'],'succeeded');self.assertEqual(len(calls),2)
        self.assertEqual(self.service.operation('one')['phase'],'complete')
        self.assertIn('cinematic.json',self.service.artifact('one','output/cinematic.json')['handle'])

    def test_request_id_is_shared_by_submit_execute_and_concurrent_callers(self):
        started,release,calls=self.blocked();self.submit();self.assertTrue(started.wait(2))
        with ThreadPoolExecutor(max_workers=8) as clients:
            replies=list(clients.map(lambda _:self.submit(),range(8)))
            self.assertTrue(all(r['status']=='running' for r in replies))
            joined=clients.submit(self.service.execute,'shot','camera_prepare',self.args())
            self.assertFalse(joined.done());release.set()
            self.assertEqual(joined.result(timeout=5)['status'],'succeeded')
        self.assertEqual(len(calls),1)
        self.assertEqual(self.submit()['status'],'succeeded')
        changed=self.args();changed['recipe']['id']='Other'
        with self.assertRaises(ValueError):self.service.submit('shot','camera_prepare',changed)

    def test_arguments_are_frozen_before_the_caller_can_change_them(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2))
        args=self.args();self.service.submit('two','camera_prepare',args)
        args['recipe']['id']='Mutated';release.set();self.terminal('two')
        frozen=json.loads((self.service.operations/'two/request.json').read_text(encoding='utf-8'))
        self.assertNotEqual(frozen['arguments']['recipe']['id'],'Mutated')
        self.assertEqual(calls[1]['recipe'],frozen['arguments']['recipe'])

    def test_queued_cancel_never_starts_work_and_releases_capacity(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2));self.submit('two')
        cancelled=self.tool('studio_cancel',{'request_id':'two'})
        self.assertEqual(cancelled['status'],'cancelled');self.assertNotIn('started_at',cancelled)
        self.assertEqual(self.service.cancel('two'),cancelled)
        release.set();self.terminal('one');self.assertEqual(len(calls),1)
        self.assertFalse((self.service.operations/'two/output').exists())
        self.assertEqual(self.submit('two'),cancelled)

    def test_running_cpu_cancel_is_cooperative_and_preserves_partial_outputs(self):
        started,release,calls=self.blocked();self.submit();self.assertTrue(started.wait(2))
        cancelled=self.service.cancel('shot');self.assertEqual(cancelled['status'],'cancelling')
        self.assertEqual(self.service.operation('shot')['phase'],'cancellation_requested')
        with self.assertRaises(ValueError):self.service.artifact('shot','output/cinematic.json')
        release.set();value=self.terminal();self.assertEqual(value['status'],'cancelled')
        self.assertIn('cancel_requested_at',value);self.assertEqual(value['artifacts'],[])
        self.assertTrue((self.service.operations/'shot/output/cinematic.json').is_file())
        self.assertEqual(self.submit(),value);self.assertEqual(len(calls),1)

    def test_cancel_during_artifact_indexing_never_publishes_a_manifest(self):
        started=threading.Event();release=threading.Event();original=studio.digest
        def digest(path):
            if path.name=='cinematic.json':
                started.set()
                if not release.wait(5):raise AssertionError('Indexing was not released')
            return original(path)
        with patch.object(studio,'digest',side_effect=digest):
            try:
                self.submit();self.assertTrue(started.wait(2))
                self.assertEqual(self.service.operation('shot')['phase'],'indexing')
                self.assertEqual(self.service.cancel('shot')['status'],'cancelling')
                release.set();value=self.terminal()
                self.assertEqual(value['status'],'cancelled');self.assertEqual(value['artifacts'],[])
            finally:release.set()

    def test_queue_is_bounded_and_idempotent_retries_work_at_capacity(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2))
        for i in range(studio.MAX_PENDING-1):self.submit('queued-'+str(i))
        with self.assertRaises(ValueError):self.submit('overflow')
        self.assertFalse((self.service.operations/'overflow').exists())
        self.assertEqual(self.submit('one')['status'],'running')
        self.service.cancel('queued-0');self.assertEqual(self.submit('replacement')['status'],'queued')
        for value in self.service.jobs(100)['items']:
            if value['status']=='queued':self.service.cancel(value['request_id'])
        release.set();self.terminal('one');self.assertEqual(len(calls),1)

    def test_queued_paths_are_rechecked_before_dispatch(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2))
        source=self.assets/'bundle';source.mkdir()
        self.service.submit('late','layers_compose',{'bundle':'asset:bundle'})
        source.rmdir();outside=self.root/'outside';outside.mkdir()
        try:source.symlink_to(outside,target_is_directory=True)
        except OSError:pass  # Missing input still must fail before dispatch on restricted Windows.
        release.set();value=self.terminal('late')
        self.assertEqual(value['status'],'failed');self.assertEqual(value['error'],'ValueError')
        self.assertEqual(len(calls),1);self.assertEqual(list(outside.iterdir()),[])

    def test_queued_configuration_is_bound_to_accepted_request(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2));self.submit('two')
        self.service.blender=Path(sys.executable).resolve();release.set()
        self.assertEqual(self.terminal('two')['status'],'failed');self.assertEqual(len(calls),1)

    def test_budget_timeout_releases_worker_and_does_not_leak_control_to_next_job(self):
        real=self.service._dispatch
        def controlled(op,args,paths,output):
            if output.parent.name=='timeout':
                while True:checkpoint();threading.Event().wait(.005)
            return real(op,args,paths,output)
        with patch.object(self.service,'_dispatch',side_effect=controlled),patch.object(studio,'EXECUTION_SECONDS',.05):
            self.submit('timeout');self.assertEqual(self.terminal('timeout')['status'],'timed_out')
        self.assertEqual(self.service.execute('next','camera_prepare',self.args())['status'],'succeeded')
        checkpoint()  # This calling thread has no Studio scope.
        self.assertEqual(self.submit('timeout')['status'],'timed_out')

    def test_background_failures_are_durable_and_not_retried(self):
        with patch.object(self.service,'_dispatch',side_effect=ValueError('fixture error')) as dispatch:
            self.submit();value=self.terminal();self.assertEqual(value['status'],'failed')
            self.assertEqual(value['error'],'ValueError');self.assertEqual(self.submit(),value)
            self.assertEqual(dispatch.call_count,1)

    def test_graceful_close_waits_for_running_cpu_stage_and_cancels_the_queue(self):
        started,release,calls=self.blocked();self.submit('one');self.assertTrue(started.wait(2));self.submit('two')
        closer=threading.Thread(target=self.service.close);closer.start()
        try:
            wait_for(lambda:self.service.operation('one')['status']=='cancelling')
            self.assertTrue(closer.is_alive())
            with self.assertRaises(RuntimeError):studio.StudioService(self.work,self.assets)
            release.set();closer.join(5);self.assertFalse(closer.is_alive())
            self.assertEqual(self.service.operation('one')['status'],'cancelled')
            self.assertEqual(self.service.operation('two')['status'],'cancelled')
            with studio.StudioService(self.work,self.assets) as reopened:self.assertEqual(reopened.jobs(10)['counts'],{'cancelled':2})
        finally:release.set();closer.join(5)

    def test_restart_interrupts_all_unfinished_receipts_and_never_resumes(self):
        for name in ('queued','running','cancelling'):
            self.service.execute(name,'camera_prepare',self.args())
            path=self.service.operations/name/'operation.json'
            value=json.loads(path.read_text(encoding='utf-8'));value['status']=name;write_json(path,value)
        self.service.close()
        with patch.object(studio.StudioService,'_dispatch',side_effect=AssertionError('must not resume')):
            with studio.StudioService(self.work,self.assets) as reopened:
                self.assertEqual(reopened.jobs(10)['counts'],{'interrupted':3})
                for name in ('queued','running','cancelling'):
                    value=reopened.submit(name,'camera_prepare',self.args())
                    self.assertEqual(value['status'],'interrupted');self.assertEqual(value['phase'],'review_partial_outputs')

    def test_history_limits_are_bounded_and_terminal_cancel_does_not_change_receipt(self):
        for value in (True,0,101,'20',None):
            with self.assertRaises(ValueError):self.service.jobs(value)
        for name in ('first','second','third'):self.service.execute(name,'camera_prepare',self.args())
        history=self.service.jobs(2);self.assertEqual(history['total'],3)
        self.assertEqual([x['request_id'] for x in history['items']],['third','second'])
        value=self.service.operation('first');self.assertEqual(self.service.cancel('first'),value)
        self.assertFalse(history['artifacts_verified'])

    def test_async_tools_are_allowlisted_and_configuration_aware(self):
        names={t['name'] for t in tool_list(studio=True)}
        self.assertTrue({'studio_submit','studio_cancel','studio_jobs'}<=names)
        self.assertNotIn('studio_submit',{t['name'] for t in tool_list()})
        for args in (dict(request_id='bad',operation='shell',arguments={'command':'echo nope'}),
                     dict(request_id='bad',operation='camera_prepare',arguments={**self.args(),'output':'/outside'})):
            result=self.server.handle(dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='studio_submit',arguments=args)))['result']
            self.assertTrue(result['isError'])
        self.assertEqual(list(self.service.operations.iterdir()),[])

    def test_exported_launcher_submits_polls_lists_and_reads_over_real_stdio(self):
        path=self.root/'connection.json'
        connect.save_config(path,dict(schema=connect.SCHEMA,executor='mock',python=sys.executable,
            workspace=str(self.root/'peer'),asset_root=str(self.assets),blender='',comfy_profiles='',game_project=''))
        peer=LocalPeer(path,'codex');self.addCleanup(peer.close);peer.call('initialize')
        value=peer.tool('studio_submit',dict(request_id='stdio',operation='camera_prepare',arguments=self.args()))
        self.assertEqual(value['status'],'queued')
        value=wait_for(lambda: (v if (v:=peer.tool('studio_operation',{'request_id':'stdio'}))['status'] not in ACTIVE else None))
        self.assertEqual(value['status'],'succeeded')
        self.assertEqual(peer.tool('studio_jobs',{'limit':10})['items'][0]['request_id'],'stdio')
        self.assertEqual(peer.tool('studio_cancel',{'request_id':'stdio'})['status'],'succeeded')
        result=peer.tool('studio_artifact',dict(request_id='stdio',file='output/cinematic.json'))
        self.assertEqual(json.loads(result['text'])['kind'],'cinematic')

    def test_running_cancel_reaches_existing_process_context_and_stops_descendants(self):
        processes=[];real=self.service._dispatch
        grandchild="from pathlib import Path; import time; p=Path('heartbeat'); deadline=time.monotonic()+15;\nwhile time.monotonic()<deadline: p.write_text(str(time.time()),encoding='utf-8'); time.sleep(.02)"
        parent="import subprocess,sys,time; from pathlib import Path; child=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); Path('child-pid').write_text(str(child.pid),encoding='utf-8'); time.sleep(15)"
        def spawn(*args,**kwargs):
            process=subprocess.Popen(*args,**kwargs);processes.append(process);return process
        def dispatch(op,args,paths,output):
            if output.parent.name!='process':return real(op,args,paths,output)
            output.mkdir()
            ctx=ExecutionContext(output,output,(),threading.Event(),time.monotonic()+30)
            run_process([sys.executable,'-c',parent,grandchild],ctx,popen=spawn)
            return {}
        with patch.object(self.service,'_dispatch',side_effect=dispatch):
            self.submit('process');output=self.service.operations/'process/output';heartbeat=output/'heartbeat'
            try:
                wait_for(lambda: heartbeat.is_file() and (output/'child-pid').is_file())
                self.assertEqual(self.service.cancel('process')['status'],'cancelling')
                self.assertEqual(self.terminal('process')['status'],'cancelled')
                self.assertIsNotNone(processes[0].poll())
                before=heartbeat.read_bytes();threading.Event().wait(.25)
                self.assertEqual(heartbeat.read_bytes(),before,'Descendant survived process-tree cancellation')
            finally:
                for process in processes:stop_process(process)

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_real_blender_camera_operation_can_run_asynchronously(self):
        self.service.blender=Path(BLENDER).resolve()
        self.submit('program');self.assertEqual(self.terminal('program')['status'],'succeeded')
        self.service.submit('preview','camera_preview',{'bundle':'work:studio/operations/program/output'})
        result=wait_for(lambda:(v if (v:=self.service.operation('preview'))['status'] not in ACTIVE else None),timeout=30)
        self.assertEqual(result['status'],'succeeded',result)
        self.assertTrue((self.service.operations/'preview/output/camera-preview.blend').is_file())
        self.assertFalse(result['engine_validated']);self.assertFalse(result['visual_quality_validated'])

    @unittest.skipUnless(BLENDER,'Blender executable unavailable')
    def test_actual_blender_is_stopped_and_its_partial_copy_is_not_published(self):
        self.service.blender=Path(BLENDER).resolve();self.service.execute('program','camera_prepare',self.args())
        processes=[]
        def spawn(*args,**kwargs):
            process=subprocess.Popen(*args,**kwargs);processes.append(process);return process
        def long_worker(command,context):
            # Replace only the finite camera workload with an explicitly long Blender fixture.
            command=list(command);command[command.index('--python')+1]=str(ROOT/'loopcut/harness/cryptonyan_studio_cancel_fixture.py')
            return run_process(command,context,popen=spawn)
        with patch('cryptonyan_asset_studio.camera_moves.run_process',side_effect=long_worker):
            self.service.submit('blender','camera_preview',{'bundle':'work:studio/operations/program/output'})
            output=self.service.operations/'blender/output'
            try:
                wait_for(lambda:(output/'blender-ready.txt').is_file(),timeout=30)
                self.assertEqual(self.service.cancel('blender')['status'],'cancelling')
                result=self.terminal('blender');self.assertEqual(result['status'],'cancelled')
                self.assertIsNotNone(processes[0].poll());self.assertTrue((output/'partial.blend').is_file())
                self.assertEqual(result['artifacts'],[])
                with self.assertRaises(ValueError):self.service.artifact('blender','output/partial.blend')
                self.assertEqual(list(self.assets.iterdir()),[])
            finally:
                self.service.cancel('blender')
                for process in processes:stop_process(process)


if __name__=='__main__':unittest.main()
