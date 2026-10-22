"""Queue contracts plus the actual receiver with a small live-agent double."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

ADDONS = Path(__file__).resolve().parents[2] / 'scripts/addons_core'
sys.path.insert(0, str(ADDONS))
from loopcut.brief_queue import BriefQueue, SCHEMA


class BridgeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root/'bridge.json'
        self.config.write_text(json.dumps(dict(schema=SCHEMA, root=str(self.root/'work/bridge'),
            work_root=str(self.root/'work'), comfy_profiles=str(self.root/'profiles.json'),
            protected_roots=[str(self.root/'game')])))
        self.q = BriefQueue(self.config)
        self.q.heartbeat(dict(ready=True, session='session-one', scene='', busy=False, native_codex=True))

    def tearDown(self): self.tmp.cleanup()

    def submit(self, key='test-1'):
        return self.q.submit(key, 'Read scene only', 'session-one', '')


class QueueTests(BridgeFixture):
    def test_duplicate_is_exactly_once_and_changed_payload_is_rejected(self):
        self.submit(); self.submit()
        self.assertEqual(self.q.status()['counts'], {'queued':1})
        with self.assertRaises(ValueError): self.q.submit('test-1','Different','session-one','')

    def test_concurrent_clients_deduplicate(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            values=list(pool.map(lambda _:self.submit(), range(2)))
        self.assertEqual([x['status'] for x in values], ['queued','queued'])
        self.assertEqual(self.q.status()['counts'], {'queued':1})

    def test_old_session_and_disconnected_receiver_cannot_submit(self):
        with self.assertRaises(ValueError):self.q.submit('old','Read','other','')
        self.q.heartbeat(dict(ready=False,session='session-one',scene=''))
        with self.assertRaises(ValueError):self.submit()

    def test_queued_brief_is_not_retargeted(self):
        self.submit()
        self.assertIsNone(self.q.claim('other-session',''))
        self.assertEqual(self.q.get('test-1')['status'],'failed')

    def test_dispatched_job_is_interrupted_on_restart_never_requeued(self):
        self.submit();self.q.claim('session-one','')
        self.q.recover()
        self.assertEqual(self.q.get('test-1')['status'],'interrupted')
        self.assertIsNone(self.q.claim('session-one',''))
        self.assertEqual(self.submit()['status'],'interrupted')

    def test_cancel_queued_and_inflight_have_distinct_states(self):
        self.submit();self.assertEqual(self.q.cancel('test-1')['status'],'cancelled')
        self.submit('running');self.q.claim('session-one','')
        self.assertEqual(self.q.cancel('running')['status'],'cancelling')

    def test_paths_and_queue_capacity(self):
        with self.assertRaises(ValueError):self.q.output('../bad')
        with self.assertRaises(ValueError):self.q.submit('bad','Read','session-one',str(self.root/'game/a.blend'))
        for i in range(16):self.submit('job-'+str(i))
        with self.assertRaises(ValueError):self.submit('full')

    def test_single_receiver_os_lock(self):
        lock=self.q.consumer_lock()
        try:
            with self.assertRaises(RuntimeError):self.q.consumer_lock()
        finally:lock.close()
        self.q.consumer_lock().close()

    def test_mcp_native_discovery_and_argument_validation(self):
        from cryptonyan_asset_studio.native_loopcut_mcp import server_type
        server=server_type(self.q)(None)
        def call(method,params={}):return server.handle(dict(jsonrpc='2.0',id=1,method=method,params=params))
        self.assertIn('error',call('tools/list'))
        self.assertIn('+native-briefs.1',call('initialize')['result']['serverInfo']['version'])
        names=[x['name'] for x in call('tools/list')['result']['tools']]
        self.assertIn('loopcut_brief_submit',names)
        self.assertTrue(call('tools/call',dict(name='loopcut_brief_status',arguments={}))['result']['isError'])

    def test_native_cli_returns_unicode_receipts_under_a_windows_codepage(self):
        import os, subprocess
        self.submit()
        self.q.update('test-1', status='succeeded', response='Lotus terminé — angle −45° 🌸')
        script=ADDONS/'cryptonyan_asset_studio/native_brief_cli.py'
        result=subprocess.run([sys.executable,'-I',str(script),'--bridge-config',str(self.config),
            'get','--request-id','test-1'],capture_output=True,timeout=10,
            env={**os.environ,'PYTHONIOENCODING':'cp1252'})
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        self.assertEqual(json.loads(result.stdout.decode('utf-8'))['response'],'Lotus terminé — angle −45° 🌸')


class ReceiverTests(BridgeFixture):
    def setUp(self):
        super().setUp()
        import loopcut
        self.session=dict(id='session-one',busy=False,turn=None,turn_outcome='',attachments=[],items=[],usage={})
        self.turn=types.SimpleNamespace(cancel=threading.Event(),outcome='running',thread=types.SimpleNamespace(is_alive=lambda:True))
        self.sent=[]
        def send(text):
            self.sent.append(text)
            self.session.update(busy=True,turn=self.turn,turn_outcome='running')
            self.session['items'].append({'kind':'user','text':text})
            return True
        agent=types.SimpleNamespace(send=send)
        state=types.SimpleNamespace(session=lambda:self.session)
        cfg=types.SimpleNamespace(codex_app=lambda:object())
        bpy=types.ModuleType('bpy');bpy.data=types.SimpleNamespace(filepath='',objects=[])
        handlers=types.ModuleType('bpy.app.handlers');handlers.persistent=lambda f:f
        with mock.patch.dict(sys.modules, {'bpy':bpy,'bpy.app':types.ModuleType('bpy.app'),'bpy.app.handlers':handlers}), \
             mock.patch.multiple(loopcut,agent=agent,state=state,config=cfg,create=True):
            spec=importlib.util.spec_from_file_location('loopcut._receiver_test_subject',ADDONS/'loopcut/native_brief_receiver.py')
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.receiver=self.module.Receiver(self.config)
        self.receiver.tick()

    def tearDown(self):
        self.receiver.close()
        super().tearDown()

    def test_receiver_does_not_inject_a_manual_busy_turn(self):
        self.submit(); self.session['busy']=True
        self.receiver.tick();self.assertFalse(self.sent)
        self.session['busy']=False;self.receiver.tick();self.assertEqual(len(self.sent),1)

    def test_native_turn_completion_with_cleared_session_turn_is_recorded(self):
        self.submit();self.receiver.tick();self.receiver.tick();self.assertEqual(len(self.sent),1)
        self.session['items'].append({'kind':'assistant','text':'Measured scene: zero meshes.'})
        self.session.update(busy=False,turn=None,turn_outcome='completed')
        self.turn.outcome='completed';self.turn.thread.is_alive=lambda:False
        self.receiver.tick()
        receipt=self.q.get('test-1')
        self.assertEqual(receipt['status'],'succeeded')
        self.assertIn('zero meshes',receipt['response'])
        self.assertFalse(receipt['quality_verified'])
        self.receiver.tick();self.assertEqual(len(self.sent),1)

    def test_cancellation_targets_owned_turn_never_manual_replacement(self):
        self.submit();self.receiver.tick();self.q.cancel('test-1')
        manual=types.SimpleNamespace(cancel=threading.Event())
        self.session['turn']=manual
        self.receiver.tick()
        self.assertTrue(self.turn.cancel.is_set());self.assertFalse(manual.cancel.is_set())
        self.assertEqual(self.q.get('test-1')['status'],'cancelling')
        self.turn.outcome='cancelled';self.turn.thread.is_alive=lambda:False
        self.receiver.tick();self.assertEqual(self.q.get('test-1')['status'],'cancelled')

    def test_receiver_error_keeps_ownership_until_its_native_thread_has_stopped(self):
        self.submit();self.receiver.tick()
        with mock.patch.object(self.receiver,'live',side_effect=RuntimeError('fixture error')):
            self.receiver.tick()
        self.assertTrue(self.turn.cancel.is_set())
        self.assertEqual(self.q.get('test-1')['status'],'cancelling')
        self.assertIsNotNone(self.receiver.active)
        self.submit('test-2')
        self.receiver.tick();self.assertEqual(len(self.sent),1)
        self.turn.outcome='cancelled';self.turn.thread.is_alive=lambda:False
        self.receiver.tick();self.assertEqual(self.q.get('test-1')['status'],'interrupted')

    def test_uninstall_refuses_to_release_a_live_owned_turn(self):
        self.submit();self.receiver.tick()
        self.module._receiver=self.receiver
        with self.assertRaisesRegex(RuntimeError,'owned native turn'):
            self.module.uninstall()
        self.assertIs(self.module._receiver,self.receiver)

    def test_owned_save_as_inside_job_output_does_not_cancel_the_turn(self):
        self.submit();self.receiver.tick()
        scene=str(self.q.output('test-1')/'candidate.blend')
        self.module.bpy.data.filepath=scene
        self.receiver.note_saved_scene();self.receiver.tick()
        self.assertFalse(self.turn.cancel.is_set())
        self.assertEqual(self.q.get('test-1')['saved_scene_path'],scene)
        self.session.update(busy=False,turn=None)
        self.turn.outcome='completed';self.turn.thread.is_alive=lambda:False
        self.receiver.tick();self.assertEqual(self.q.get('test-1')['status'],'succeeded')

    def test_opening_another_file_is_not_authorized_by_its_output_location(self):
        self.submit();self.receiver.tick()
        # No save_post event: a file load/manual target change must still cancel.
        self.module.bpy.data.filepath=str(self.q.output('test-1')/'other.blend')
        self.receiver.tick();self.assertTrue(self.turn.cancel.is_set())
        self.turn.outcome='cancelled';self.turn.thread.is_alive=lambda:False
        self.receiver.tick();self.assertEqual(self.q.get('test-1')['status'],'interrupted')

    def test_save_as_outside_owned_output_is_not_a_retarget(self):
        self.submit();self.receiver.tick()
        self.module.bpy.data.filepath=str(self.root/'work/other-mission.blend')
        self.receiver.note_saved_scene();self.receiver.tick()
        self.assertTrue(self.turn.cancel.is_set())
        self.assertNotIn('saved_scene_path',self.q.get('test-1'))


if __name__=='__main__':unittest.main()
