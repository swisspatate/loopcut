# SPDX-License-Identifier: GPL-3.0-or-later
"""Private, durable Claude <-> an operator-selected Codex desktop chat mailbox."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

SCHEMA = 'cryptonyan.desktop-relay/1'
REPORT_FIELDS = {'summary', 'changes', 'objects', 'checks', 'remaining_errors', 'outputs', 'recommendations'}
INSTRUCTIONS = (
    '\nFor human-authorized delegation by a Claude orchestrator, use the existing operator-selected desktop chat. '
    'codex_desktop_submit queues one bounded mission for that chat, not for another model or a new thread. '
    'The scheduled chat checks the mailbox; codex_desktop_result waits up to 45 seconds and returns its report. '
    'Keep waiting with the same ID while it is active. Existing native loopcut_brief tools remain separate. '
    'Choose one executor, never submit the same mission to both routes. No overwrites/deletions, game asset '
    'changes, TRELLIS edits, purchases, or publication are authorized by a mailbox message. '
    'Read the operator protocol beside the private relay configuration before delegating. '
)


def tools():
    identity = {'type': 'string', 'pattern': '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'}
    specs = [
        ('codex_desktop_status', 'Read the configured desktop chat, scheduled-consumer heartbeat, live Blender and mailbox counts. No model or generation.', {}),
        ('codex_desktop_submit', 'Queue an authorized non-destructive 3D mission to the existing Codex desktop chat. Pin the live Blender session/scene. Stable ID and exact arguments deduplicate; scheduled delivery is not instantaneous.',
         {'request_id': identity, 'brief': {'type': 'string', 'minLength': 1, 'maxLength': 16000},
          'expected_session': {'type': 'string', 'minLength': 1, 'maxLength': 64},
          'expected_scene': {'type': 'string', 'maxLength': 4096}}),
        ('codex_desktop_result', 'Read a mission and its structured final report. Optionally wait at most 45 seconds; repeat for the same ID rather than ending orchestration prematurely. Does not wake or restart another model.',
         {'request_id': identity, 'wait_seconds': {'type': 'integer', 'minimum': 0, 'maximum': 45}}),
        ('codex_desktop_cancel', 'Cancel a queued mission or request cancellation of its owned work. Active cancellation remains pending until the consumer confirms it; never globally interrupts Blender or ComfyUI.', {'request_id': identity}),
    ]
    return [dict(name=n, description=d, inputSchema=dict(type='object', additionalProperties=False,
        properties=p, required=list(p))) for n,d,p in specs]


class DesktopRelay:
    def __init__(self, path):
        from loopcut.brief_queue import BriefQueue
        from .storage import safe_path
        self.path = Path(path).absolute()
        if self.path.is_symlink() or self.path.stat().st_size > 16384: raise ValueError('Invalid relay config')
        value = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if set(value) != {'schema','thread_id','bridge_config','queue_config','enabled'} or value['schema'] != SCHEMA:
            raise ValueError('Invalid relay config schema')
        if str(uuid.UUID(value['thread_id'])) != value['thread_id'] or type(value['enabled']) is not bool:
            raise ValueError('Invalid desktop target')
        self.config = value
        self.bridge = BriefQueue(value['bridge_config'])
        self.queue = BriefQueue(value['queue_config'])
        if self.queue.root == self.bridge.root or self.queue.work != self.bridge.work:
            raise ValueError('Use a separate desktop mailbox below the same workshop')
        self.consumer_file = safe_path(self.queue.root, 'consumer.json')

    def status(self):
        live = self.bridge.status()
        consumer = json.loads(self.consumer_file.read_text()) if self.consumer_file.exists() else {}
        return dict(enabled=self.config['enabled'], target_thread_id=self.config['thread_id'],
            live_blender=live, counts=self.queue.status()['counts'], consumer=consumer,
            consumer_recent=bool(consumer.get('checked_at') and 0 <= time.time()-consumer['checked_at'] < 180),
            output_root=str(self.queue.root), delivery='scheduled_current_chat')

    def submit(self, request_id, brief, expected_session, expected_scene):
        if not self.config['enabled']: raise ValueError('Desktop relay disabled')
        self.queue.heartbeat(self.bridge.status())
        self.queue.submit(request_id, brief, expected_session, expected_scene)
        value = self.get(request_id)
        return {**value, 'target_thread_id':self.config['thread_id']}

    def get(self, request_id, wait_seconds=0):
        from loopcut.brief_queue import TERMINAL
        if type(wait_seconds) is not int or not 0 <= wait_seconds <= 45: raise ValueError('Wait must be 0-45 seconds')
        deadline=time.monotonic()+wait_seconds
        while True:
            value=self.queue.get(request_id)
            if value['status'] in TERMINAL | {'needs_input'} or time.monotonic()>=deadline: break
            time.sleep(min(.25,max(0,deadline-time.monotonic())))
        return {k:v for k,v in value.items() if k!='claim_token'}

    def next(self, thread_id):
        from loopcut.brief_queue import TERMINAL
        from .storage import write_json
        if thread_id != self.config['thread_id']: raise ValueError('Not the configured desktop chat')
        write_json(self.consumer_file,dict(thread_id=thread_id,checked_at=time.time()))
        if not self.config['enabled']: return dict(status='disabled')
        live=self.bridge.status()
        # A persisted active claim is resumed for inspection, never silently requeued.
        with self.queue.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=[json.loads(r[0]) for r in c.execute('SELECT record FROM jobs ORDER BY rowid')]
            active=next((x for x in rows if x['status'] not in TERMINAL | {'queued','needs_input'}),None)
            if active: return dict(status='resume_inspect_first',job=active)
            if not live['ready'] or live['busy']: return dict(status='waiting_for_blender',jobs=len(rows))
            for value in rows:
                if value['status']!='queued':continue
                if value['expected_session']!=live.get('session') or value['expected_scene']!=live.get('scene'):
                    value.update(status='failed',error='Pinned native scene/session changed; no automatic retarget',updated=time.time())
                    c.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(value),value['id']))
                    continue
                value.update(status='running',claim_token=uuid.uuid4().hex,claimed_by=thread_id,updated=time.time())
                c.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(value),value['id']))
                return dict(status='claimed',job=value)
        return dict(status='idle')

    def progress(self, request_id, token, native_request_id):
        from loopcut.brief_queue import identifier
        identifier(native_request_id)
        with self.queue.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            value=self._owned(c,request_id,token)
            if value.get('native_request_id') not in (None,native_request_id): raise ValueError('Native ID already pinned')
            value.update(native_request_id=native_request_id,updated=time.time())
            c.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(value),request_id))
        return self.get(request_id)

    def _owned(self, c, request_id, token):
        from loopcut.brief_queue import identifier
        row=c.execute('SELECT record FROM jobs WHERE id=?',(identifier(request_id),)).fetchone()
        if row is None:raise ValueError('Unknown desktop mission')
        value=json.loads(row[0])
        if not token or value.get('claim_token')!=token:raise ValueError('Claim token mismatch')
        return value

    def finish(self, request_id, token, status, report):
        from loopcut.brief_queue import TERMINAL
        from .storage import write_json
        if status not in TERMINAL | {'needs_input'} or not isinstance(report,dict) or set(report)!=REPORT_FIELDS:
            raise ValueError('Use a terminal status and the documented report schema')
        if (not isinstance(report['summary'],str) or any(not isinstance(report[k],list) for k in REPORT_FIELDS-{'summary'})
                or len(json.dumps(report,allow_nan=False))>64000): raise ValueError('Invalid or oversized report')
        for output in report['outputs']:
            if not isinstance(output,str) or not Path(output).is_absolute() or not self.queue.scene_allowed(output):
                raise ValueError('Report outputs must stay in the workshop')
        digest=hashlib.sha256(json.dumps(report,sort_keys=True,allow_nan=False).encode()).hexdigest()
        with self.queue.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            value=self._owned(c,request_id,token)
            if value['status'] in TERMINAL | {'needs_input'}:
                if value.get('report_sha256')!=digest or value['status']!=status:raise ValueError('Existing final report is immutable')
            else:
                if value.get('cancel_requested') and status=='succeeded':raise ValueError('Confirm cancellation before reporting success')
                value.update(status=status,report=report,report_sha256=digest,updated=time.time())
                c.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(value),request_id))
        folder=self.queue.output(request_id).parent;folder.mkdir(parents=True,exist_ok=True)
        public=self.get(request_id)
        write_json(folder/'receipt.json',public)
        return public

    def call(self,name,arguments):
        spec=next((x for x in tools() if x['name']==name),None)
        if not spec or not isinstance(arguments,dict) or set(arguments)!=set(spec['inputSchema']['required']):
            raise ValueError('Invalid desktop relay arguments')
        if name=='codex_desktop_status':return self.status()
        if name=='codex_desktop_submit':return self.submit(**arguments)
        if name=='codex_desktop_result':return self.get(**arguments)
        value=self.queue.cancel(arguments['request_id'])
        return {k:v for k,v in value.items() if k!='claim_token'}


def extend_server(parent, relay):
    class DesktopMCP(parent):
        def handle(self,message):
            if (isinstance(message,dict) and message.get('jsonrpc')=='2.0' and 'id' in message
                    and message.get('method')=='tools/call' and self.initialized):
                params=message.get('params',{})
                if isinstance(params,dict) and params.get('name') in {x['name'] for x in tools()}:
                    try:
                        value=relay.call(params['name'],params.get('arguments',{}))
                        result=dict(content=[dict(type='text',text=json.dumps(value))],isError=False)
                    except (ValueError,OSError,RuntimeError) as exc:
                        result=dict(content=[dict(type='text',text=str(exc))],isError=True)
                    return dict(jsonrpc='2.0',id=message['id'],result=result)
            result=super().handle(message)
            if result and 'result' in result:
                if message.get('method')=='initialize':
                    result['result']['instructions']+=INSTRUCTIONS
                    result['result']['serverInfo']['version']+='+desktop-relay.1'
                elif message.get('method')=='tools/list':result['result']['tools']+=tools()
            return result
    return DesktopMCP


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    # Import by package even for an absolute-file entry point.
    from cryptonyan_asset_studio.desktop_relay import DesktopRelay
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('action',choices=('status','submit','get','cancel','next','progress','finish'))
    parser.add_argument('--request-id');parser.add_argument('--brief-file');parser.add_argument('--thread-id')
    parser.add_argument('--expected-session');parser.add_argument('--expected-scene',default='')
    parser.add_argument('--wait-seconds',type=int,default=0);parser.add_argument('--claim-token')
    parser.add_argument('--native-request-id');parser.add_argument('--report-file');parser.add_argument('--status')
    args=parser.parse_args(argv);relay=DesktopRelay(args.config)
    if args.action=='status':value=relay.status()
    elif args.action=='submit':
        path=Path(args.brief_file).resolve()
        if not relay.queue.scene_allowed(str(path)) or path.stat().st_size>64000:raise ValueError('Use a workshop brief file')
        value=relay.submit(args.request_id,path.read_text(encoding='utf-8-sig'),args.expected_session,args.expected_scene)
    elif args.action=='get':value=relay.get(args.request_id,args.wait_seconds)
    elif args.action=='cancel':value=relay.call('codex_desktop_cancel',dict(request_id=args.request_id))
    elif args.action=='next':value=relay.next(args.thread_id)
    elif args.action=='progress':value=relay.progress(args.request_id,args.claim_token,args.native_request_id)
    else:
        path=Path(args.report_file).resolve()
        if not relay.queue.scene_allowed(str(path)) or path.stat().st_size>64000:raise ValueError('Use a bounded workshop report file')
        value=relay.finish(args.request_id,args.claim_token,args.status,json.loads(path.read_text(encoding='utf-8-sig')))
    print(json.dumps(value,indent=2,ensure_ascii=False));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(status='failed',error=str(exc))),file=sys.stderr);raise SystemExit(2)
