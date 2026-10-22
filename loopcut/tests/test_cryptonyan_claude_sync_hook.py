"""The local context hook ignores unrelated Claude sessions and logs no prompts."""
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/addons_core'))
from cryptonyan_asset_studio import claude_sync_hook


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=self.root/'desktop-relay.json'
        self.queue=self.root/'queue.json'
        self.work=self.root/'work';self.work.mkdir()
        self.source=self.root/'source';self.source.mkdir()
        self.queue.write_text(json.dumps({'work_root':str(self.work)}))
        self.config.write_text(json.dumps({'enabled':True,'queue_config':str(self.queue)}))
        self.session=str(uuid.uuid4())

    def context(self,value):
        return claude_sync_hook.context(value,self.config,source_root=self.source)

    def event(self,prompt,session=None):
        return dict(hook_event_name='UserPromptSubmit',session_id=session or self.session,cwd=str(self.root/'unrelated'),prompt=prompt)

    def test_unrelated_session_ignored(self):
        self.assertIsNone(self.context(self.event('Corrige ma facture')))
        adjacent=self.event('Continue');adjacent['cwd']=str(self.root/'work-other')
        self.assertIsNone(self.context(adjacent))

    def test_orchestrator_bound_then_followup_without_cross_session_context(self):
        value=self.context(self.event('Utilise Loopcut pour cet asset'))
        self.assertIn('SYNCHRONISATION-AUTO.md',value['hookSpecificOutput']['additionalContext'])
        self.assertIsNotNone(self.context(self.event('Continue')))
        self.assertIsNone(self.context(self.event('Continue',str(uuid.uuid4()))))
        import sqlite3
        with contextlib.closing(sqlite3.connect(self.root/'claude-sync-sessions.sqlite3')) as db:
            self.assertEqual([x[1] for x in db.execute('PRAGMA table_info(sessions)')],['id','seen'])

    def test_disabled_and_invalid_identity_are_silent(self):
        value=self.event('Loopcut');value['session_id']='../outside'
        self.assertIsNone(self.context(value))
        self.config.write_text(json.dumps({'enabled':False}))
        self.assertIsNone(self.context(self.event('Loopcut')))

    def test_workshop_session_start_is_in_scope_without_a_keyword(self):
        value=self.event('');value.update(hook_event_name='SessionStart',cwd=str(self.work))
        self.assertIsNotNone(self.context(value))

    def test_cli_absolute_entry_point_is_silent_for_invalid_input(self):
        import subprocess
        result=subprocess.run([sys.executable,'-I',str(Path(claude_sync_hook.__file__)),
            '--relay-config',str(self.config)],input='invalid json',text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout,'')


if __name__=='__main__':unittest.main()
