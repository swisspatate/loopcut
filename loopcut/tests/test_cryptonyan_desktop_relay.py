"""Mailbox delegation, reports and single-consumer contracts; no scene changes."""
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from loopcut.brief_queue import BriefQueue,SCHEMA as BRIDGE_SCHEMA
from cryptonyan_asset_studio.desktop_relay import DesktopRelay,SCHEMA,extend_server


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.work=self.root/'work';self.thread=str(uuid.uuid4())
        for name,folder in [('bridge','native'),('desktop-queue','desktop')]:
            (self.root/(name+'.json')).write_text(json.dumps(dict(schema=BRIDGE_SCHEMA,
                root=str(self.work/folder),work_root=str(self.work),comfy_profiles=str(self.root/'profiles.json'),
                protected_roots=[str(self.root/'game')])) )
        self.cfg=self.root/'relay.json'
        self.cfg.write_text(json.dumps(dict(schema=SCHEMA,thread_id=self.thread,bridge_config=str(self.root/'bridge.json'),
            queue_config=str(self.root/'desktop-queue.json'),enabled=True)))
        self.relay=DesktopRelay(self.cfg)
        self.relay.bridge.heartbeat(dict(ready=True,native_codex=True,busy=False,session='native-one',scene=''))

    def submit(self,key='job-1'):return self.relay.submit(key,'Inspect only, no scene changes','native-one','')

    def report(self):return dict(summary='Read-only test passed',changes=[],objects=[],checks=[{'name':'protocol','passed':True}],
        remaining_errors=[],outputs=[],recommendations=[])

    def test_submission_deduplicates_and_never_dispatches_a_model(self):
        self.submit();self.submit()
        self.assertEqual(self.relay.status()['counts'],{'queued':1})
        self.assertEqual(self.relay.bridge.status()['counts'],{})
        with self.assertRaises(ValueError):self.relay.submit('job-1','Changed brief','native-one','')

    def test_queued_cancellation_and_wrong_thread(self):
        self.submit()
        with self.assertRaises(ValueError):self.relay.next(str(uuid.uuid4()))
        self.assertEqual(self.relay.call('codex_desktop_cancel',{'request_id':'job-1'})['status'],'cancelled')
        self.assertEqual(self.relay.next(self.thread)['status'],'idle')

    def test_changed_scene_fails_without_automatic_retarget(self):
        self.submit();self.relay.bridge.heartbeat(dict(ready=True,busy=False,session='different',scene=''))
        self.assertEqual(self.relay.next(self.thread)['status'],'idle')
        self.assertEqual(self.relay.get('job-1')['status'],'failed')

    def test_manual_blender_busy_is_not_interrupted(self):
        self.submit();self.relay.bridge.heartbeat(dict(ready=True,busy=True,session='native-one',scene=''))
        self.assertEqual(self.relay.next(self.thread)['status'],'waiting_for_blender')
        self.assertEqual(self.relay.get('job-1')['status'],'queued')

    def test_concurrent_consumers_return_one_active_claim(self):
        self.submit();self.submit('job-2')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.relay.next(self.thread),range(2)))
        self.assertEqual({r['job']['id'] for r in results},{'job-1'})
        self.assertEqual(self.relay.get('job-2')['status'],'queued')

    def test_progress_and_report_survive_a_new_client(self):
        self.submit();job=self.relay.next(self.thread)['job'];token=job['claim_token']
        self.relay.progress(job['id'],token,'native-job-1')
        with self.assertRaises(ValueError):self.relay.progress(job['id'],token,'different')
        new=DesktopRelay(self.cfg)
        self.assertEqual(new.next(self.thread)['status'],'resume_inspect_first')
        with self.assertRaises(ValueError):new.finish(job['id'],'wrong','succeeded',self.report())
        result=new.finish(job['id'],token,'succeeded',self.report())
        self.assertEqual(new.finish(job['id'],token,'succeeded',self.report()),result)
        self.assertNotIn('claim_token',new.get(job['id']))
        self.assertNotIn('claim_token',self.submit())
        with self.assertRaises(ValueError):new.finish(job['id'],token,'failed',self.report())
        self.assertEqual(new.get(job['id'])['report']['summary'],'Read-only test passed')

    def test_cancelled_running_job_cannot_be_reported_as_success(self):
        self.submit();job=self.relay.next(self.thread)['job']
        self.relay.call('codex_desktop_cancel',{'request_id':job['id']})
        with self.assertRaises(ValueError):self.relay.finish(job['id'],job['claim_token'],'succeeded',self.report())
        self.assertEqual(self.relay.finish(job['id'],job['claim_token'],'cancelled',self.report())['status'],'cancelled')

    def test_report_protects_game_and_wait_budget(self):
        self.submit();job=self.relay.next(self.thread)['job'];report=self.report()
        report['outputs']=[str(self.root/'game/asset.blend')]
        with self.assertRaises(ValueError):self.relay.finish(job['id'],job['claim_token'],'succeeded',report)
        with self.assertRaises(ValueError):self.relay.get(job['id'],46)
        with self.assertRaises(ValueError):self.relay.call('codex_desktop_result',{'request_id':job['id']})

    def test_new_mcp_tools_extend_without_changing_original_tools(self):
        from cryptonyan_asset_studio.native_loopcut_mcp import server_type
        server=extend_server(server_type(self.relay.bridge),self.relay)(None)
        def call(method,params={}):return server.handle(dict(jsonrpc='2.0',id=1,method=method,params=params))
        self.assertIn('+desktop-relay.1',call('initialize')['result']['serverInfo']['version'])
        names=[x['name'] for x in call('tools/list')['result']['tools']]
        self.assertIn('loopcut_brief_submit',names);self.assertIn('codex_desktop_submit',names)
        result=call('tools/call',{'name':'codex_desktop_status','arguments':{}})['result']
        self.assertFalse(result['isError'])


if __name__=='__main__':unittest.main()
