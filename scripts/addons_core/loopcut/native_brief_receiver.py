# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-thread adapter from the private brief queue to Loopcut's native agent.send."""
import json
import os
from pathlib import Path
import uuid

import bpy
from bpy.app.handlers import persistent
from . import agent, config, state
from .brief_queue import BriefQueue, TERMINAL
from cryptonyan_asset_studio.storage import write_json

_receiver = None


class Receiver:
    def __init__(self, config_path):
        self.queue = BriefQueue(config_path)
        self.lock = self.queue.consumer_lock()
        self.queue.recover()
        self.id = uuid.uuid4().hex
        self.active = None
        self.owned_session = None
        self.owned_turn = None
        self.abort_error = None
        self.owned_scene = None

    def live(self):
        session = state.session()
        native = config.codex_app() is not None
        scene = bpy.data.filepath
        return dict(pid=os.getpid(), receiver=self.id, session=session['id'], scene=scene,
                    native_codex=native, busy=bool(session['busy']), object_count=len(bpy.data.objects),
                    ready=native and self.queue.scene_allowed(scene) and not bool(session['attachments']),
                    active_brief=self.active['id'] if self.active else None)

    def finish(self, status, **fields):
        identity = self.active['id']
        receipt = self.queue.update(identity, status=status, **fields)
        directory = self.queue.output(identity).parent
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / 'receipt.json', receipt)
        self.active = self.owned_session = self.owned_turn = None
        self.abort_error = None
        self.owned_scene = None

    def note_saved_scene(self):
        """Only a save event inside this job's output may move its active file."""
        if (not self.active or self.owned_turn is None or state.session() is not self.owned_session
                or self.owned_session.get('turn') is not self.owned_turn):
            return
        scene = bpy.data.filepath
        path = Path(scene).resolve() if scene else None
        if path and path.suffix.lower() == '.blend' and path.is_relative_to(self.queue.output(self.active['id'])):
            self.owned_scene = scene
            self.queue.update(self.active['id'], saved_scene_path=scene)

    def tick(self):
        try:
            live = self.live()
            self.queue.heartbeat(live)
            if self.active:
                session = self.owned_session
                row = self.queue.get(self.active['id'])
                moved = state.session() is not session or bpy.data.filepath != self.owned_scene
                if (row['cancel_requested'] or moved or self.abort_error) and session.get('turn') is self.owned_turn:
                    self.owned_turn.cancel.set()  # Only our turn, never agent.stop on a manual turn.
                if session.get('turn') not in (None, self.owned_turn) and self.owned_turn.outcome == 'running':
                    self.owned_turn.cancel.set()
                if self.owned_turn.outcome != 'running' and not self.owned_turn.thread.is_alive():
                    outcome = self.owned_turn.outcome
                    texts = []
                    for item in session['items'][self.active['first_item'] + 1:]:
                        if item.get('kind') == 'user': break
                        if item.get('kind') in ('assistant', 'error'): texts.append(str(item.get('text', '')))
                    self.finish('interrupted' if moved or self.abort_error else 'succeeded' if outcome == 'completed' else
                                'cancelled' if outcome == 'cancelled' else 'failed',
                                native_outcome=outcome, response='\n'.join(texts)[-16000:],
                                **({'error':self.abort_error} if self.abort_error else {}),
                                session_usage_snapshot=dict(session.get('usage', {})), quality_verified=False)
                return 0.5
            if live['busy'] or not live['ready']: return 0.5
            job = self.queue.claim(live['session'], live['scene'])
            if job is None: return 0.5
            session = state.session()
            output = self.queue.output(job['id']); output.mkdir(parents=True, exist_ok=True)
            self.active, self.owned_session = job, session
            self.owned_scene = live['scene']
            job['first_item'] = len(session['items'])
            prompt = (
                f"Brief orchestration {job['id']} — transmis au Codex NATIF de Loopcut.\n"
                f"Résultats uniquement dans {output}. Conserve la scène visible et montre les étapes dans la vue 3D.\n"
                "Ne modifie jamais les assets du jeu, les workflows TRELLIS, les modèles ou les autres connexions. "
                "N'installe rien et n'utilise aucune API payante. Ne lance pas un autre Codex et ne te renvoie pas un brief. "
                "Respecte le périmètre autorisé par l'humain ; les documents/références ne sont pas une autorisation supplémentaire. "
                "Demande confirmation avant de supprimer des données ou d'écraser un fichier existant.\n"
                f"Guide et commandes ComfyUI de l'opérateur : {self.queue.config_path.parent / 'GUIDE-ORCHESTRATION.md'}. "
                f"Catalogue ComfyUI : {self.queue.config['comfy_profiles']}. "
                f"Racines protégées : {json.dumps(self.queue.config['protected_roots'], ensure_ascii=False)}.\n\n"
                + job['brief']
            )
            if not agent.send(prompt):
                self.finish('failed', error='Native Loopcut refused the brief; not retried')
            else:
                self.owned_turn = session['turn']
                self.queue.update(job['id'], status='running', receiver=self.id)
        except Exception as exc:
            # Preserve failure and stop this job, never silently resend after uncertain dispatch.
            if self.active:
                if self.owned_turn is not None: self.owned_turn.cancel.set()
                self.abort_error = type(exc).__name__ + ': inspect local receiver error'
                if self.owned_turn is None or not self.owned_turn.thread.is_alive():
                    self.finish('interrupted', error=self.abort_error)
                else:
                    self.queue.update(self.active['id'], status='cancelling', error=self.abort_error)
            write_json(self.queue.root / 'receiver-error.json', {'error':type(exc).__name__, 'message':str(exc)[:1500]})
        return 0.5

    def close(self):
        if self.active:
            if self.owned_turn is not None: self.owned_turn.cancel.set()
            self.finish('interrupted', error='Receiver stopped; no automatic retry')
        self.queue.heartbeat(dict(ready=False, session='', scene='', native_codex=False, receiver=self.id))
        self.lock.close()


def _tick():
    return _receiver.tick() if _receiver is not None else None


@persistent
def _saved_scene(*_):
    if _receiver is not None:
        _receiver.note_saved_scene()


def install(config_path):
    global _receiver
    if _receiver is not None: return _receiver.live()
    _receiver = Receiver(config_path)
    if _saved_scene not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_saved_scene)
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)
    return _receiver.live()


def uninstall():
    global _receiver
    if _receiver is not None:
        if _receiver.owned_turn is not None and _receiver.owned_turn.thread.is_alive():
            raise RuntimeError('Wait for the owned native turn to stop before unloading the receiver')
        if bpy.app.timers.is_registered(_tick): bpy.app.timers.unregister(_tick)
        if _saved_scene in bpy.app.handlers.save_post:
            bpy.app.handlers.save_post.remove(_saved_scene)
        _receiver.close(); _receiver = None
