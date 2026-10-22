# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional Claude context hook; configuration and session metadata stay outside Git."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid


def context(value, relay_config, *, source_root=None):
    """Return environment context only, never a mission, permission or model call."""
    path = Path(relay_config).absolute()
    if path.is_symlink() or path.stat().st_size > 16384:
        return None
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    if not settings.get('enabled'):
        return None
    event = value.get('hook_event_name')
    if event not in ('UserPromptSubmit', 'SessionStart'):
        return None
    identity = value.get('session_id', '')
    try:
        if str(uuid.UUID(identity)) != identity:
            return None
    except (ValueError, TypeError, AttributeError):
        return None
    queue_path = Path(settings['queue_config'])
    if not queue_path.is_absolute() or queue_path.is_symlink() or queue_path.stat().st_size > 16384:
        return None
    work = Path(json.loads(queue_path.read_text(encoding='utf-8-sig'))['work_root'])
    if not work.is_absolute():
        return None
    source = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[3]
    cwd = Path(value.get('cwd', '')).resolve()
    prompt = str(value.get('prompt', value.get('user_prompt', '')))
    relevant = bool(re.search(r'loopcut|orchestrat(?:eur|ion).{0,30}(?:3d|codex)|codex.{0,30}blender',
                              prompt, re.I | re.S))
    relevant = relevant or cwd.is_relative_to(work.resolve()) or cwd.is_relative_to(source.resolve())
    directory = path.resolve().parent
    # Retain only a session UUID and timestamp. No prompts, transcripts or credentials.
    db = sqlite3.connect(directory / 'claude-sync-sessions.sqlite3', timeout=2)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,seen REAL NOT NULL)')
            bound = db.execute('SELECT 1 FROM sessions WHERE id=?', (identity,)).fetchone() is not None
            if not relevant and not bound:
                return None
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)', (identity, time.time()))
    finally:
        db.close()
    protocol = directory / 'SYNCHRONISATION-AUTO.md'
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext':
        'A local 3D coordination relay is configured for this session. If the human authorized '
        'delegation to the existing Codex desktop chat, read the operator protocol at '
        f'{protocol} before using codex_desktop_submit/result or the documented CLI fallback. '
        'Keep waiting on the same request ID to retrieve its report; do not duplicate the mission '
        'on both desktop and native Loopcut routes. This hook only supplies environment context. '
        'It grants no authorization for a new task, overwrite, deletion, game asset change, '
        'TRELLIS edit, purchase or publication. Other projects and connections are unchanged.'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relay-config', required=True)
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) <= 1024 * 1024:
            output = context(json.loads(raw), args.relay_config)
            if output:
                print(json.dumps(output, ensure_ascii=False))
    except Exception:
        # Optional context must never block a human prompt or disclose its contents.
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
