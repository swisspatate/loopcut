"""Loopcut-only context limits and honest display before/after server usage events."""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'addons_core'))
sys.modules.setdefault('bpy', types.ModuleType('bpy'))
from loopcut import codex_app, config, conversations, state
from loopcut.ui import layout


class ContextLimitsTest(unittest.TestCase):
    def test_child_arguments_leave_global_configuration_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = home / 'config.toml'
            original = b'model = "my-existing-model"\n'
            settings.write_bytes(original)
            app = config.CodexApp('codex', context_window=872000, auto_compact_token_limit=780000)
            cmd = codex_app.command(app, home)
            self.assertIn('model_context_window=872000', cmd)
            self.assertIn('model_auto_compact_token_limit=780000', cmd)
            self.assertEqual(settings.read_bytes(), original)
            regular = codex_app.command(config.CodexApp('codex'), home)
            self.assertFalse(any(x.startswith(('model_context_window=', 'model_auto_compact_token_limit='))
                                 for x in regular))

    def test_settings_are_optional_and_invalid_thresholds_fail(self):
        values = {'LOOPCUT_CODEX_APP': 'true', 'LOOPCUT_CODEX_BIN': 'codex'}
        def get(key, default=''):
            return values.get(key, default)
        with mock.patch.object(config, '_getter', return_value=({}, get)):
            self.assertIsNone(config.codex_app().context_window)
            values.update(LOOPCUT_CODEX_CONTEXT_WINDOW='872000', LOOPCUT_CODEX_AUTO_COMPACT_TOKEN_LIMIT='780000')
            self.assertEqual(config.codex_app().context_window, 872000)
            values['LOOPCUT_CODEX_AUTO_COMPACT_TOKEN_LIMIT'] = '900000'
            with self.assertRaises(config.ConfigError):
                config.codex_app()

    def test_fresh_native_chat_does_not_claim_a_40k_capacity(self):
        ui = {'codex_mode': True, 'codex_context_window': 872000,
              'codex_auto_compact_token_limit': 780000}
        usage = state.new_session()['usage']
        shown = layout.display_usage(usage, ui)
        lines = '\n'.join(layout.usage_lines(shown, 40000, None))
        self.assertNotIn('40.0k', lines)
        self.assertIn('872.0k', lines)
        self.assertIn('780.0k', lines)
        self.assertIn('unavailable', lines)
        self.assertNotIn('context_source', usage, 'display must not invent a measured usage event')
        shown.update(context=650000, context_window=828400)
        self.assertIn('650.0k of 828.4k', '\n'.join(layout.usage_lines(shown, 40000, None)))
        self.assertAlmostEqual(layout.ring_shares(shown, 40000, None)[0][1], 650000 / 828400)

    def test_server_capacity_survives_reopen_and_legacy_codex_never_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'LOOPCUT_DATA_DIR': tmp}):
            session = state.new_session()
            session['items'].append(state.item_user('Test'))
            session['codex_thread'] = 'test-thread'
            session['usage'].update(context_source='codex', context_window=828400, context=650000)
            conversations.save(session)
            loaded = conversations.load(session['id'])
            self.assertEqual(loaded['usage']['context_window'], 828400)
            self.assertIn('828.4k', '\n'.join(layout.usage_lines(loaded['usage'], 40000, None)))
            path = conversations.root() / session['id'] / 'conversation.json'
            body = json.loads(path.read_text())
            body['usage'].pop('context_source')
            body['usage'].pop('context_window')
            path.write_text(json.dumps(body))
            old = conversations.load(session['id'])
            self.assertEqual(old['usage']['context_source'], 'codex')
            self.assertNotIn('40.0k', '\n'.join(layout.usage_lines(old['usage'], 40000, None)))


if __name__ == '__main__':
    unittest.main()
