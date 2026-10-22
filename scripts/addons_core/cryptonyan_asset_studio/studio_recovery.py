# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit, pinned workflow snapshots. Never resumes an interrupted worker."""
import copy
import re

from .animation_doctor import exact, read_json
from .image_workshop import identity
from .publication import _hash
from .storage import digest, safe_path

TERMINAL=frozenset(('succeeded','failed','cancelled','timed_out'))
MAX_LINEAGE=8
PIN_FIELDS=('source_request_id','source_request_identity','source_context_identity','source_workflow_identity')


def validate_reuse(value, steps):
    exact(value,PIN_FIELDS+('steps',))
    if not isinstance(value['source_request_id'],str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',value['source_request_id']):
        raise ValueError('Use a portable source request ID')
    for key in PIN_FIELDS[1:]:_hash(value[key])
    selected=value['steps']
    if not isinstance(selected,list) or not 1<=len(selected)<=len(steps):raise ValueError('Reuse must select a nonempty workflow prefix')
    for pin,step in zip(selected,steps):
        exact(pin,('id','receipt_sha256'));_hash(pin['receipt_sha256'])
        if pin['id']!=step['id']:raise ValueError('Reuse must select consecutive initial step IDs')


def reuse_schema():
    hashes={key:{'type':'string','pattern':'^[a-f0-9]{64}$'} for key in PIN_FIELDS[1:]}
    return dict(type='object',additionalProperties=False,required=list(PIN_FIELDS)+['steps'],properties=dict(
        source_request_id={'type':'string','pattern':'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'},**hashes,
        steps={'type':'array','minItems':1,'maxItems':8,'items':{'type':'object','additionalProperties':False,
            'required':['id','receipt_sha256'],'properties':{'id':{'type':'string'},'receipt_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}}}}))


class Snapshots:
    """A bounded verification pass; no cache survives a public tool call."""
    def __init__(self, service):
        self.service=service;self.parents={};self.verified={}

    def parent(self, request_id):
        if request_id in self.parents:return self.parents[request_id]
        from .studio_workflows import validate
        folder=self.service._folder(request_id)
        with self.service.lock:
            record=read_json(safe_path(folder,'operation.json'))
            request=read_json(safe_path(folder,'request.json'))
        if record.get('request_id')!=request_id or record.get('operation')!='workflow_run' or request.get('operation')!='workflow_run':
            raise ValueError('Select a workflow operation')
        if identity(dict(operation=request['operation'],arguments=request['arguments'],context=record['context_identity']))!=record['request_identity']:
            raise ValueError('Workflow request identity changed')
        workflow=validate(request['arguments']['workflow'])
        captured=safe_path(folder,'output/workflow.json')
        if captured.exists() and identity(read_json(captured))!=identity(workflow):raise ValueError('Captured workflow changed')
        self.parents[request_id]=(record,workflow,folder)
        return self.parents[request_id]

    def _source(self, descriptor, context):
        record,workflow,folder=self.parent(descriptor['source_request_id'])
        if (record['request_identity']!=descriptor['source_request_identity'] or
            record['context_identity']!=descriptor['source_context_identity'] or
            identity(workflow)!=descriptor['source_workflow_identity']):raise ValueError('Pinned workflow source changed')
        if record['context_identity']!=context:raise ValueError('Snapshot configuration differs from this workflow')
        return record,workflow,folder

    def step(self, request_id, step_id, expected=None, trail=()):
        key=(request_id,step_id)
        if key in trail or len(trail)>MAX_LINEAGE:raise ValueError('Workflow snapshot lineage exceeds its bound or contains a cycle')
        if key in self.verified:
            result=self.verified[key]
            if expected is not None and result['receipt_sha256']!=expected:raise ValueError('Pinned step receipt changed')
            return result
        record,workflow,parent=self.parent(request_id)
        if record['status'] not in TERMINAL:raise ValueError('Only stopped, non-interrupted workflows expose verified snapshots')
        specification=next((s for s in workflow['steps'] if s['id']==step_id),None)
        if specification is None:raise ValueError('Unknown workflow step ID')
        folder=safe_path(parent,'output/steps/'+step_id);path=safe_path(folder,'step.json')
        before=digest(path);receipt=read_json(path)
        if expected is not None and before!=expected:raise ValueError('Pinned step receipt changed')
        if record['status']=='succeeded':
            listed=next((a for a in record['artifacts'] if a['file']=='output/steps/'+step_id+'/step.json'),None)
            if listed is None or listed['sha256']!=before:raise ValueError('Parent manifest does not confirm this step receipt')
        if receipt.get('schema')!='cryptonyan.studio-workflow-step/1' or receipt.get('id')!=step_id or receipt.get('operation')!=specification['operation']:
            raise ValueError('Workflow step receipt differs from its specification')
        captured=receipt.get('artifacts')
        if not isinstance(captured,list) or not captured or not any(a['file']=='result.json' for a in captured):
            raise ValueError('Step has no captured result manifest')
        if receipt['status'] not in ('succeeded','reused') and receipt.get('execution_completed') is not True:
            raise ValueError('Step execution did not complete artifact capture')
        self.service._verify_artifacts(folder,captured,exclude=('step.json',))
        result=dict(folder=folder,receipt=receipt,receipt_sha256=before,origin_folder=folder,origin_receipt=receipt,
                    source_request_id=request_id,source_step_id=step_id,depth=0)
        if receipt['status']=='reused':
            descriptor=workflow.get('reuse')
            if descriptor is None:raise ValueError('Reused step has no workflow provenance')
            pin=next((p for p in descriptor['steps'] if p['id']==step_id),None)
            if pin is None:raise ValueError('Reused step is outside the pinned prefix')
            expected_ref={k:descriptor[k] for k in PIN_FIELDS};expected_ref.update(step_id=step_id,receipt_sha256=pin['receipt_sha256'])
            if receipt.get('reuse')!=expected_ref:raise ValueError('Step provenance changed')
            _,source,_=self._source(descriptor,record['context_identity'])
            count=len(descriptor['steps'])
            if identity(workflow['steps'][:count])!=identity(source['steps'][:count]):raise ValueError('Reused prefix specification changed')
            origin=self.step(descriptor['source_request_id'],step_id,pin['receipt_sha256'],trail+(key,))
            if not origin['reusable']:raise ValueError('Referenced step is not reusable')
            for field in ('origin_folder','origin_receipt','source_request_id','source_step_id'):result[field]=origin[field]
            result['depth']=origin['depth']+1
        from .studio_workflows import evaluate_checks
        checks=evaluate_checks(read_json(safe_path(result['origin_folder'],'result.json')),specification['checks'])
        result.update(checks=checks,reusable=receipt['status'] in ('succeeded','reused') and
                      specification['operation']!='unreal_handoff' and all(c['matched'] for c in checks))
        if digest(path)!=before:raise ValueError('Step receipt changed during verification')
        self.verified[key]=result
        return result

    def plan(self, workflow, context):
        descriptor=workflow.get('reuse')
        if descriptor is None:return {}
        validate_reuse(descriptor,workflow['steps'])
        record,source,_=self._source(descriptor,context)
        if record['status'] not in TERMINAL:raise ValueError('Source workflow must be stopped and not interrupted')
        count=len(descriptor['steps'])
        if identity(workflow['steps'][:count])!=identity(source['steps'][:count]):raise ValueError('Reused prefix must retain identical operations, arguments and checks')
        selected={}
        for pin in descriptor['steps']:
            item=self.step(descriptor['source_request_id'],pin['id'],pin['receipt_sha256'])
            if not item['reusable']:raise ValueError('Only successful checked steps are reusable; regenerate Unreal handoffs')
            if item['depth']>=MAX_LINEAGE:raise ValueError('Snapshot lineage limit reached; fork from the original workflow')
            selected[pin['id']]=item
        return selected


def verify_plan(service, workflow, context=None):
    return Snapshots(service).plan(workflow,service._context_identity() if context is None else context)


def inspect(service, request_id):
    snapshots=Snapshots(service);record,workflow,_=snapshots.parent(request_id)
    retry=copy.deepcopy(workflow);retry.pop('reuse',None)
    result=dict(schema='cryptonyan.studio-workflow-inspection/1',request_id=request_id,status=record['status'],
        workflow=retry,context_matches=record['context_identity']==service._context_identity(),
        snapshot_reuse_only=True,source_freshness_validated=False,reusable_prefix_steps=0,steps=[])
    prefix=True
    for specification in workflow['steps']:
        item=dict(id=specification['id'],operation=specification['operation'],verified=False,reusable=False)
        try:
            selected=snapshots.step(request_id,specification['id'])
            artifacts=selected['origin_receipt']['artifacts']
            visible=[a for a in artifacts if a['file']=='result.json']+[a for a in artifacts if a['file']!='result.json'][:31]
            item.update(verified=True,reusable=selected['reusable'] and result['context_matches'] and selected['depth']<MAX_LINEAGE,
                status=selected['receipt']['status'],receipt_sha256=selected['receipt_sha256'],checks=selected['checks'],
                artifact_count=len(artifacts),artifacts=visible,artifacts_truncated=len(artifacts)>len(visible),
                output=service._handle(selected['origin_folder']/'output'),lineage_depth=selected['depth'],
                origin=dict(request_id=selected['source_request_id'],step_id=selected['source_step_id']))
        except (ValueError,OSError,KeyError,TypeError):item['reason']='snapshot_unavailable_or_changed'
        prefix=prefix and item['reusable']
        if prefix:result['reusable_prefix_steps']+=1
        result['steps'].append(item)
    return result


def fork(service, source_request_id, workflow, reuse_steps):
    from .studio_workflows import validate
    workflow=validate(workflow)
    if 'reuse' in workflow:raise ValueError('Supply a plain workflow; the fork tool creates provenance')
    if type(reuse_steps) is not int or not 1<=reuse_steps<=len(workflow['steps']):raise ValueError('Select 1 to 8 initial steps to reuse')
    snapshots=Snapshots(service);record,source,_=snapshots.parent(source_request_id)
    descriptor={key:record[field] for key,field in (('source_request_id','request_id'),
        ('source_request_identity','request_identity'),('source_context_identity','context_identity'))}
    descriptor.update(source_workflow_identity=identity(source),steps=[])
    for step in workflow['steps'][:reuse_steps]:
        selected=snapshots.step(source_request_id,step['id'])
        descriptor['steps'].append(dict(id=step['id'],receipt_sha256=selected['receipt_sha256']))
    workflow['reuse']=descriptor
    snapshots.plan(workflow,service._context_identity())
    return dict(workflow=workflow,execution_started=False,snapshot_reuse_only=True,source_freshness_validated=False,
                original_history_required=True,new_request_id_required=True)


def step_artifact(service, request_id, step_id, file):
    snapshot=Snapshots(service).step(request_id,step_id)
    return service._read_artifact(snapshot['origin_folder'],snapshot['origin_receipt']['artifacts'],file)
