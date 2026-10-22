# SPDX-License-Identifier: GPL-3.0-or-later
"""Allowlisted MCP access to existing operations. No shell, arbitrary output or editor RPC."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from .animation_doctor import exact, read_json
from .image_workshop import identity
from .executors import BudgetExpired, Cancelled, checkpoint, execution_scope
from .storage import OwnerLock, digest, safe_path, write_json

# Required argument names/types. Existing modules own the detailed recipe schemas.
OPERATIONS = {
    'wardrobe_review': {'source':'path','specification':'object'},
    'garment_fit': {'source':'path','specification':'object'},
    'animation_audit': {'source':'path','specification':'object'},
    'rig_audit': {'source':'path','specification':'object'},
    'rig_repair_plan': {'bundle':'path','policy':'object'},
    'rig_repair_copy': {'plan':'path'},
    'level_prepare': {'recipe':'object','catalog':'object','source_root':'path'},
    'level_preview': {'bundle':'path'},
    'layers_prepare': {'recipe':'object','source_root':'path'},
    'layers_compose': {'bundle':'path'},
    'camera_prepare': {'recipe':'object'},
    'camera_preview': {'bundle':'path'},
    'image_prepare': {'reference':'path','recipe':'object','source_root':'path'},
    'image_build': {'bundle':'path'},
    'comparison_plan': {'recipe':'object'},
    'comparison_gallery': {'plan':'path','captures':'paths'},
    'director_plan': {'recipe':'object'},
    'unreal_handoff': {'kind':'kind','plan':'path'},
}
BLENDER_OPERATIONS = {'wardrobe_review','garment_fit','animation_audit','rig_audit','rig_repair_copy','level_preview','camera_preview','image_build'}
PROJECT_OPERATIONS = {'comparison_plan','comparison_gallery','director_plan','unreal_handoff'}
KINDS = ('comparison_stage','director_review','modular_review')
ACTIVE = frozenset(('queued', 'running', 'cancelling'))
MAX_PENDING = 16
EXECUTION_SECONDS = 600


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _Job:
    cancelled: threading.Event = field(default_factory=threading.Event)
    future: object = None


def operation_schema():
    branches = []
    for operation, fields in OPERATIONS.items():
        props = {}
        for key, kind in fields.items():
            props[key] = ({'type':'object'} if kind=='object' else {'type':'array','minItems':2,'maxItems':8,'items':{'type':'string'}} if kind=='paths'
                          else {'type':'string','enum':list(KINDS)} if kind=='kind' else {'type':'string','minLength':5,'maxLength':4096})
        branches.append({'properties':{'operation':{'enum':[operation]},'arguments':{
            'type':'object','additionalProperties':False,'required':list(fields),'properties':props}}})
    return {'type':'object','additionalProperties':False,'required':['request_id','operation','arguments'],
        'properties':{'request_id':{'type':'string','pattern':'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'},
                      'operation':{'type':'string','enum':list(OPERATIONS)},'arguments':{'type':'object'}},'oneOf':branches}


class StudioService:
    def __init__(self, workspace, asset_root, *, blender=None, project=None):
        self.workspace = Path(workspace).resolve(); self.assets = Path(asset_root).resolve(strict=True)
        if not self.assets.is_dir() or self.workspace.is_relative_to(self.assets) or self.assets.is_relative_to(self.workspace):
            raise ValueError('Use separate asset and operation workspaces')
        if project is not None and (self.workspace.is_relative_to(project.root) or project.root.is_relative_to(self.workspace)):
            raise ValueError('Keep the operation workspace outside the game project')
        self.root = safe_path(self.workspace, 'studio'); self.root.mkdir(parents=True, exist_ok=True)
        self.operations = safe_path(self.root, 'operations'); self.operations.mkdir(exist_ok=True)
        self.blender = Path(blender).resolve() if blender else None
        self.project = project
        self.closed=False
        self.lock = threading.RLock(); self.close_lock = threading.Lock(); self._jobs = {}; self.owner = OwnerLock(safe_path(self.root,'owner.lock'))
        try:
            folders = list(self.operations.iterdir())
            if len(folders)>1024: raise ValueError('Operation history capacity reached')
            # A restarted call is uncertain, never automatically retried.
            for folder in folders:
                if folder.is_symlink(): raise ValueError('Operation symlinks are not allowed')
                receipt = safe_path(folder, 'operation.json')
                if receipt.exists():
                    value = read_json(receipt)
                    if value.get('status') in ACTIVE:
                        value.update(status='interrupted', phase='review_partial_outputs', finished_at=_now(),
                                     error='service_restarted_review_partial_outputs'); write_json(receipt, value)
            # One Studio operation at a time; independent clients/mission queues are separate.
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cryptonyan-studio')
        except BaseException:
            self.owner.close(); raise

    def close(self):
        with self.close_lock:
            with self.lock:
                if self.closed: return
                self.closed = True
                for request_id in list(self._jobs): self._cancel_locked(request_id)
            # Keep ownership until children have stopped and final receipts are durable.
            try: self.executor.shutdown(wait=True)
            finally: self.owner.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def _folder(self, request_id):
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',request_id):
            raise ValueError('Use a stable portable request ID')
        return safe_path(self.operations, request_id)

    def _input(self, handle):
        if not isinstance(handle,str) or len(handle)>4096: raise ValueError('Expected an asset: or work: handle')
        prefix, sep, relative = handle.partition(':')
        if not sep or prefix not in ('asset','work'): raise ValueError('Use asset: or work: paths only')
        root = self.assets if prefix=='asset' else self.workspace
        path = safe_path(root, relative) if relative else root
        if not path.exists(): raise ValueError('Operation input is missing')
        return path

    def _approved_absolute(self, value):
        if not isinstance(value,str) or not Path(value).is_absolute(): raise ValueError('Expected a bound absolute bundle path')
        path=Path(value)
        for root in (self.assets,self.workspace):
            if path.is_relative_to(root): return self._input(('asset:' if root==self.assets else 'work:')+path.relative_to(root).as_posix())
        raise ValueError('Embedded bundle path is outside approved roots')

    def _bound_project(self, plan):
        if self.project is None or Path(plan.get('project_root','')).resolve()!=self.project.root:
            raise ValueError('Plan must use the configured game project')

    def _handle(self, path): return 'work:'+Path(path).relative_to(self.workspace).as_posix()

    def _context_identity(self):
        return identity(dict(assets=str(self.assets),workspace=str(self.workspace),blender=str(self.blender) if self.blender else None,
            project=self.project._project_identity() if self.project is not None else None))

    def operation(self, request_id):
        folder=self._folder(request_id); value=read_json(safe_path(folder,'operation.json'))
        if value.get('status')=='succeeded':
            for artifact in value['artifacts']:
                path=safe_path(folder,artifact['file'])
                if not path.is_file() or path.stat().st_size!=artifact['bytes'] or digest(path)!=artifact['sha256']: raise ValueError('Operation artifact changed')
        return value

    def submit(self, request_id, operation, arguments):
        """Accept once and return immediately; polling never starts or retries work."""
        record, _ = self._submit(request_id, operation, arguments)
        return record

    def execute(self, request_id, operation, arguments):
        """Compatibility API: join the same background job, including an existing ID."""
        record, future = self._submit(request_id, operation, arguments)
        if future is not None:
            try: future.result()
            except CancelledError: pass
            return self.operation(request_id)
        return record

    def _submit(self, request_id, operation, arguments):
        if not isinstance(operation,str) or operation not in OPERATIONS: raise ValueError('Unknown studio operation')
        fields=OPERATIONS[operation]; exact(arguments,fields)
        # Freeze caller-owned dictionaries before another thread can mutate them.
        arguments=json.loads(json.dumps(arguments, allow_nan=False))
        for key,kind in fields.items():
            value=arguments[key]
            if kind=='object' and not isinstance(value,dict): raise ValueError('Expected recipe object')
            if kind=='path' and not isinstance(value,str): raise ValueError('Expected an asset: or work: handle')
            if kind=='paths':
                if not isinstance(value,list) or not 2<=len(value)<=8: raise ValueError('Select 2 to 8 capture folders')
                if any(not isinstance(p,str) for p in value): raise ValueError('Expected input handles')
            if kind=='kind' and value not in KINDS: raise ValueError('Unsupported editor handoff kind')
        context=self._context_identity()
        fingerprint=identity(dict(operation=operation,arguments=arguments,context=context))
        with self.lock:
            if self.closed: raise RuntimeError('Studio service is closed')
            folder=self._folder(request_id)
            if folder.exists():
                previous=self.operation(request_id)
                if previous['request_identity']!=fingerprint: raise ValueError('Request ID already has different arguments')
                job=self._jobs.get(request_id)
                return previous, job.future if job else None
            if len(self._jobs)>=MAX_PENDING: raise ValueError('Studio queue capacity reached; poll or cancel existing operations')
            self._inputs(operation,arguments)
            if operation in BLENDER_OPERATIONS and (self.blender is None or not self.blender.is_file()):
                raise ValueError('Configure Blender before worker execution')
            if operation in PROJECT_OPERATIONS and self.project is None: raise ValueError('Configure the existing game project first')
            if len(list(self.operations.iterdir()))>=1024: raise ValueError('Operation history capacity reached')
            folder.mkdir(mode=0o700)
            record=dict(schema='cryptonyan.studio-operation/1',request_id=request_id,request_identity=fingerprint,
                context_identity=context,operation=operation,status='queued',phase='queued',created_at=_now(),output=self._handle(folder/'output'),artifacts=[],
                engine_validated=False,visual_quality_validated=False)
            write_json(folder/'request.json',dict(operation=operation,arguments=arguments))
            write_json(folder/'operation.json',record)
            job=_Job(); self._jobs[request_id]=job
            try:
                job.future=self.executor.submit(self._run,request_id,operation,arguments,job)
            except Exception:
                self._jobs.pop(request_id,None)
                record.update(status='failed',phase='stopped',error='submission_failed',finished_at=_now())
                write_json(folder/'operation.json',record)
                raise
            return record, job.future

    def _inputs(self, operation, arguments):
        inputs={}
        for key,kind in OPERATIONS[operation].items():
            if kind=='path': inputs[key]=self._input(arguments[key])
            if kind=='paths': inputs[key]=[self._input(p) for p in arguments[key]]
        return inputs

    def _run(self, request_id, operation, arguments, job):
        folder=self._folder(request_id); receipt=folder/'operation.json'
        with self.lock:
            record=read_json(receipt)
            if record['status']=='cancelled' or job.cancelled.is_set():
                if record['status']!='cancelled':
                    record.update(status='cancelled',phase='stopped',finished_at=_now(),error='cancelled_before_start')
                    write_json(receipt,record)
                self._jobs.pop(request_id,None); return
            record.update(status='running',phase='operation',started_at=_now())
            write_json(receipt,record)
        with execution_scope(job.cancelled,time.monotonic()+EXECUTION_SECONDS):
            try:
                checkpoint()
                if self._context_identity()!=record['context_identity']: raise ValueError('Configuration changed while operation was queued')
                inputs=self._inputs(operation,arguments)  # Revalidate after waiting; never follow a newly introduced symlink.
                result=self._dispatch(operation,arguments,inputs,folder/'output')
                checkpoint(); write_json(folder/'result.json',result)
                with self.lock:
                    checkpoint(); record.update(phase='indexing'); write_json(receipt,record)
                artifacts=[]; total=0
                for path in sorted(folder.rglob('*')):
                    checkpoint()
                    relative=path.relative_to(folder).as_posix(); safe_path(folder,relative)
                    if not path.is_file() or relative=='operation.json': continue
                    total+=path.stat().st_size
                    if len(artifacts)>=2048 or total>2*1024**3: raise ValueError('Operation artifact budget exceeded')
                    artifacts.append(dict(file=relative,bytes=path.stat().st_size,sha256=digest(path)))
                with self.lock:
                    checkpoint()
                    record.update(status='succeeded',phase='complete',artifacts=artifacts,result=self._handle(folder/'result.json'))
                    record['finished_at']=_now(); write_json(receipt,record)
            except Exception as error:
                with self.lock:
                    status='cancelled' if job.cancelled.is_set() or isinstance(error,Cancelled) else 'timed_out' if isinstance(error,BudgetExpired) else 'failed'
                    record=read_json(receipt)
                    record.update(status=status,phase='stopped',error=type(error).__name__,finished_at=_now(),
                                  partial_output=self._handle(folder/'output'))
                    write_json(receipt,record)
            finally:
                with self.lock: self._jobs.pop(request_id,None)

    def _cancel_locked(self, request_id):
        folder=self._folder(request_id); record=read_json(folder/'operation.json')
        if record['status'] not in ACTIVE: return record
        job=self._jobs.get(request_id)
        if job is None: raise RuntimeError('Active operation has no local worker; reopen the service for recovery')
        job.cancelled.set()
        if record['status']=='queued' and job.future.cancel():
            record.update(status='cancelled',phase='stopped',finished_at=_now(),error='cancelled_before_start')
            self._jobs.pop(request_id,None)
        else:
            record.update(status='cancelling',phase='cancellation_requested')
        record['cancel_requested_at']=_now(); write_json(folder/'operation.json',record)
        return record

    def cancel(self, request_id):
        """CPU cancellation is cooperative; cancelling is not yet a stopped worker."""
        with self.lock:
            if self.closed: raise RuntimeError('Studio service is closed')
            return self._cancel_locked(request_id)

    def jobs(self, limit):
        """Bounded recent receipt summaries for reconnects; no artifact verification."""
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100:
            raise ValueError('Use a history limit from 1 to 100')
        with self.lock:
            values=[read_json(safe_path(folder,'operation.json')) for folder in self.operations.iterdir()]
            values.sort(key=lambda r:(r.get('created_at',''),r['request_id']),reverse=True)
            counts={}
            for value in values: counts[value['status']]=counts.get(value['status'],0)+1
            keys=('request_id','operation','status','phase','created_at','started_at','finished_at','output')
            return dict(schema='cryptonyan.studio-jobs/1',total=len(values),counts=counts,
                        pending_limit=MAX_PENDING,workers=1,execution_seconds=EXECUTION_SECONDS,
                        artifacts_verified=False,items=[{k:v[k] for k in keys if k in v} for v in values[:limit]])

    def artifact(self, request_id, file):
        record=self.operation(request_id)
        if record['status']!='succeeded': raise ValueError('Operation has no completed artifacts')
        selected=next((a for a in record['artifacts'] if a['file']==file),None)
        if selected is None: raise ValueError('Select a listed operation artifact')
        path=safe_path(self._folder(request_id),file)
        if path.suffix.lower()=='.png':
            import base64
            from .materials import read_png
            if selected['bytes']>2*1024*1024: raise ValueError('Image exceeds the 2 MiB MCP display budget')
            data,_=read_png(path)
            if len(data)>2*1024*1024 or hashlib.sha256(data).hexdigest()!=selected['sha256']: raise ValueError('Image changed during display')
            return dict(type='image',mimeType='image/png',data=base64.b64encode(data).decode('ascii'))
        if path.suffix.lower() not in ('.json','.txt','.csv','.py','.html','.svg') or selected['bytes']>262144:
            raise ValueError('Use a text artifact up to 256 KiB; binary bundles remain local files')
        with path.open('rb') as stream: raw=stream.read(262145)
        if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=selected['sha256']: raise ValueError('Operation artifact changed during read')
        text=raw.decode('utf-8')
        return dict(file=file,handle=self._handle(path),text=text,content_is_data=True)

    def _dispatch(self, op, args, paths, output):
        if op in ('wardrobe_review','garment_fit','animation_audit','rig_audit'):
            from . import wardrobe_review, garment_fit, animation_doctor, rig_doctor
            function={'wardrobe_review':wardrobe_review.run,'garment_fit':garment_fit.run,
                      'animation_audit':animation_doctor.capture_blender,'rig_audit':rig_doctor.capture_blender}[op]
            return function(paths['source'],args['specification'],output,self.blender,timeout=180)
        if op.startswith('rig_repair_'):
            from . import rig_repair
            if op=='rig_repair_plan':
                result=rig_repair.make_plan(paths['bundle'],args['policy']); output.mkdir(); write_json(output/'plan.json',result); return result
            self._approved_absolute(read_json(paths['plan'])['bundle'])
            return rig_repair.execute(paths['plan'],output,self.blender,apply=True,timeout=180)
        if op.startswith('level_'):
            from . import modular_levels
            return modular_levels.prepare(args['recipe'],args['catalog'],paths['source_root'],output) if op=='level_prepare' else modular_levels.preview(paths['bundle'],output,self.blender,timeout=180)
        if op.startswith('layers_'):
            from . import material_layers
            return material_layers.prepare(args['recipe'],paths['source_root'],output) if op=='layers_prepare' else material_layers.compose(paths['bundle'],output)
        if op.startswith('camera_'):
            from . import camera_moves
            return camera_moves.prepare(args['recipe'],output) if op=='camera_prepare' else camera_moves.preview(paths['bundle'],output,self.blender,timeout=180)
        if op.startswith('image_'):
            from . import image_workshop
            return image_workshop.prepare(paths['reference'],args['recipe'],output,paths['source_root']) if op=='image_prepare' else image_workshop.run(paths['bundle'],output,self.blender,timeout=180)
        if op in ('comparison_plan','director_plan'):
            from . import comparison_review, creative_director
            result=(comparison_review if op=='comparison_plan' else creative_director).make_plan(args['recipe'],self.project.root)
            output.mkdir(); write_json(output/'plan.json',result); return result
        if op=='comparison_gallery':
            from .comparison_review import compare
            self._bound_project(read_json(paths['plan']))
            return compare(paths['plan'],paths['captures'],output)
        if op=='unreal_handoff': return self._handoff(args['kind'],paths['plan'],output)
        raise ValueError('Unimplemented studio operation')

    def _handoff(self, kind, plan_path, output):
        if kind=='comparison_stage':
            from .comparison_review import load_plan
            self._bound_project(read_json(plan_path)); load_plan(plan_path)
            call='comparison.create(PLAN, OUTPUT, apply=True)'
            imports='from cryptonyan_asset_studio import unreal_comparison as comparison'
        elif kind=='director_review':
            from .creative_director import load_plan
            self._bound_project(read_json(plan_path)); load_plan(plan_path)
            call='director.execute(PLAN, OUTPUT, apply=True)'
            imports='from cryptonyan_asset_studio import unreal_director as director'
        else:
            from .modular_levels import load_bundle
            load_bundle(plan_path); call='modular.review(PLAN, OUTPUT, apply=True)'
            imports='from cryptonyan_asset_studio import unreal_modular as modular'
        output.mkdir(); target=output/('editor-result.json' if kind=='director_review' else 'editor-result')
        source=('# SPDX-License-Identifier: GPL-3.0-or-later\n# Run explicitly inside the configured Unreal 5.8 editor; this file is inert until run.\n'
            'import sys\nimport unreal\n'
            'sys.path.insert(0, '+repr(str(Path(__file__).resolve().parents[1]))+')\n'
            'from cryptonyan_asset_studio.unreal_material_variants import _runtime\n'
            '_, project = _runtime(unreal)\n'
            'if project._project_identity() != '+repr(self.project._project_identity())+':\n    raise ValueError("Wrong active game project")\n'
            +imports+'\nPLAN = '+repr(str(plan_path))+'\nOUTPUT = '+repr(str(target))+'\nresult = '+call+'\nprint(result)\n')
        (output/'unreal-handoff.py').write_text(source,encoding='utf-8')
        return dict(schema='cryptonyan.unreal-handoff/1',kind=kind,script=self._handle(output/'unreal-handoff.py'),
                    requires_local_unreal=True,editor_executed=False,automatic_execution=False)
