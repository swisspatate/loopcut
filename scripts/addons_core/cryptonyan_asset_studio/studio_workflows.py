# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded sequential recipes over existing Studio operations, without a second queue."""
import argparse
import copy
import json
import math
from pathlib import Path
import re

from .animation_doctor import exact, read_json
from .executors import BudgetExpired, Cancelled, checkpoint
from .image_workshop import identity
from .storage import safe_path, write_json

SCHEMA='cryptonyan.studio-workflow/1'
MAX_STEPS=8
ID=re.compile(r'[a-z][a-z0-9_-]{0,31}')
RESERVED={'con','prn','aux','nul'}|{prefix+str(i) for prefix in ('com','lpt') for i in range(1,10)}
TEMPLATES={
    'camera_preview': {'recipe':'object'},
    'material_layers': {'recipe':'object','source_root':'path'},
    'modular_preview': {'recipe':'object','catalog':'object','source_root':'path'},
    'image_preview': {'reference':'path','recipe':'object','source_root':'path'},
    'rig_repair_copy': {'source':'path','specification':'object','policy':'object'},
}
TEMPLATE_OPERATIONS={
    'camera_preview':['camera_prepare','camera_preview'],
    'material_layers':['layers_prepare','layers_compose'],
    'modular_preview':['level_prepare','level_preview'],
    'image_preview':['image_prepare','image_build'],
    'rig_repair_copy':['rig_audit','rig_repair_plan','rig_repair_copy'],
}


class WorkflowRejected(ValueError):
    """An explicit result check rejected a completed step; nothing else is run."""


def _relative(value, limit=512):
    if not isinstance(value,str) or len(value)>limit or any(c in value for c in ('\\',':','\x00')):
        raise ValueError('Use a clean relative workflow file path')
    if value and any(p in ('','.','..') for p in value.split('/')):
        raise ValueError('Workflow bindings cannot escape a step output')
    return value


def _handle(value):
    if not isinstance(value,str) or len(value)>4096: raise ValueError('Expected an asset: or work: handle')
    prefix,sep,relative=value.partition(':')
    if not sep or prefix not in ('asset','work'): raise ValueError('Use asset: or work: handles')
    _relative(relative,limit=4096)


def _path(value, previous):
    if isinstance(value,str):_handle(value);return
    exact(value,('from_step','file'))
    if not isinstance(value['from_step'],str) or value['from_step'] not in previous:
        raise ValueError('A workflow binding must select an earlier completed step')
    _relative(value['file'])


def validate(value):
    """Pure syntax validation; detailed domain recipes are validated by their cores."""
    from .studio_service import OPERATIONS, KINDS
    exact(value,('schema','id','steps'))
    if value['schema']!=SCHEMA or not isinstance(value['id'],str) or not ID.fullmatch(value['id']) or value['id'] in RESERVED:
        raise ValueError('Use a workflow schema and lowercase portable ID')
    steps=value['steps']
    if not isinstance(steps,list) or not 1<=len(steps)<=MAX_STEPS: raise ValueError('Use 1 to 8 ordered workflow steps')
    result=json.loads(json.dumps(value,allow_nan=False));previous=set()
    for step in result['steps']:
        exact(step,('id','operation','arguments'),('checks',))
        if not isinstance(step['id'],str) or not ID.fullmatch(step['id']) or step['id'] in previous or step['id'] in RESERVED:
            raise ValueError('Step IDs must be unique lowercase portable names')
        op=step['operation']
        if not isinstance(op,str) or op not in OPERATIONS or op=='workflow_run':
            raise ValueError('Select an existing primitive Studio operation; nested workflows are refused')
        fields=OPERATIONS[op];args=step['arguments'];exact(args,fields)
        for key,kind in fields.items():
            item=args[key]
            if kind=='path':_path(item,previous)
            elif kind=='paths':
                if not isinstance(item,list) or not 2<=len(item)<=8: raise ValueError('Select 2 to 8 input folders')
                for path in item:_path(path,previous)
            elif kind=='object' and not isinstance(item,dict): raise ValueError('Expected a literal recipe object')
            elif kind=='kind' and item not in KINDS: raise ValueError('Unsupported editor handoff kind')
        checks=step.setdefault('checks',[])
        if not isinstance(checks,list) or len(checks)>8: raise ValueError('Use up to 8 explicit result checks')
        for check in checks:
            exact(check,('path','equals'))
            path=check['path'];expected=check['equals']
            if not isinstance(path,list) or not 1<=len(path)<=8 or any(not isinstance(p,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',p) for p in path):
                raise ValueError('Result checks use 1 to 8 literal field names or array indices')
            if expected is not None and type(expected) not in (str,bool,int,float): raise ValueError('A result check compares a JSON scalar')
            if isinstance(expected,str) and len(expected)>256: raise ValueError('Result check text budget exceeded')
            if type(expected) is float and not math.isfinite(expected): raise ValueError('Result checks must be finite')
        previous.add(step['id'])
    return result


def templates():
    from .studio_service import BLENDER_OPERATIONS, PROJECT_OPERATIONS
    return dict(schema='cryptonyan.studio-workflow-templates/1',templates=[dict(id=k,inputs=dict(v),operations=list(TEMPLATE_OPERATIONS[k]),
                blender_required=bool(set(TEMPLATE_OPERATIONS[k])&BLENDER_OPERATIONS),
                project_required=bool(set(TEMPLATE_OPERATIONS[k])&PROJECT_OPERATIONS)) for k,v in TEMPLATES.items()],
                maximum_steps=MAX_STEPS,execution_started=False,recipes_inferred=False)


def schema():
    from .studio_service import OPERATIONS, argument_schema
    primitives=[op for op in OPERATIONS if op!='workflow_run']
    step=dict(type='object',additionalProperties=False,required=['id','operation','arguments'],properties={
        'id':{'type':'string','pattern':'^[a-z][a-z0-9_-]{0,31}$','not':{'enum':sorted(RESERVED)}},'operation':{'type':'string','enum':primitives},
        'arguments':{'type':'object'},'checks':{'type':'array','maxItems':8,'items':{'type':'object','additionalProperties':False,
            'required':['path','equals'],'properties':{'path':{'type':'array','minItems':1,'maxItems':8,'items':{'type':'string','pattern':'^[a-zA-Z0-9_-]{1,64}$'}},
            'equals':{'type':['string','number','boolean','null'],'maxLength':256}}}}},oneOf=[
                {'properties':{'operation':{'enum':[op]},'arguments':argument_schema(op,bindings=True)}} for op in primitives])
    return dict(type='object',additionalProperties=False,required=['schema','id','steps'],properties={
        'schema':{'enum':[SCHEMA]},'id':{'type':'string','pattern':'^[a-z][a-z0-9_-]{0,31}$','not':{'enum':sorted(RESERVED)}},
        'steps':{'type':'array','minItems':1,'maxItems':MAX_STEPS,'items':step}})


def make_template(template, inputs):
    if not isinstance(template,str) or template not in TEMPLATES: raise ValueError('Unknown Studio workflow template')
    exact(inputs,TEMPLATES[template])
    def step(name,op,args):return dict(id=name,operation=op,arguments=args)
    def binding(name,file=''):return dict(from_step=name,file=file)
    if template=='camera_preview':
        steps=[step('prepare','camera_prepare',inputs),step('preview','camera_preview',dict(bundle=binding('prepare')))]
    elif template=='material_layers':
        steps=[step('prepare','layers_prepare',inputs),step('compose','layers_compose',dict(bundle=binding('prepare')))]
    elif template=='modular_preview':
        steps=[step('prepare','level_prepare',inputs),step('preview','level_preview',dict(bundle=binding('prepare')))]
    elif template=='image_preview':
        steps=[step('prepare','image_prepare',inputs),step('build','image_build',dict(bundle=binding('prepare')))]
    else:
        steps=[step('audit','rig_audit',{k:inputs[k] for k in ('source','specification')}),
               step('plan','rig_repair_plan',dict(bundle=binding('audit'),policy=inputs['policy'])),
               step('repair','rig_repair_copy',dict(plan=binding('plan','plan.json')))]
    return validate(dict(schema=SCHEMA,id=template.replace('_','-'),steps=steps))


def preflight(service, workflow):
    """Check configured runtimes and literal handles before accepting any work."""
    from .studio_service import OPERATIONS
    for step in workflow['steps']:
        service._require(step['operation'])
        for key,kind in OPERATIONS[step['operation']].items():
            values=[step['arguments'][key]] if kind=='path' else step['arguments'][key] if kind=='paths' else []
            for value in values:
                if isinstance(value,str):service._input(value)


def progress(value):
    return dict(id=value['workflow_id'],status=value['status'],current_step=value.get('current_step'),
                phase=value.get('phase','steps'),error=value.get('error'),
                total_steps=len(value['steps']),completed_steps=sum(s['status']=='succeeded' for s in value['steps']),
                steps=[{k:s[k] for k in ('id','operation','status','checks','error') if k in s} for s in value['steps']])


def interrupt(folder, record):
    """Mark journals uncertain; never resume or signal a stale PID after a crash."""
    path=safe_path(folder,'output/workflow-status.json')
    if path.is_file():
        value=read_json(path);value.update(status='interrupted',current_step=None)
        for step in value['steps']:
            if step['status'] in ('pending','running'):
                step['status']='interrupted' if step['status']=='running' else 'blocked'
                receipt=safe_path(folder,'output/steps/'+step['id']+'/step.json')
                if receipt.is_file():
                    current=read_json(receipt);current['status']=step['status'];write_json(receipt,current)
        write_json(path,value);record['workflow']=progress(value)
    elif 'workflow' in record:
        record['workflow']['status']='interrupted'
        for step in record['workflow']['steps']:step['status']='blocked'


def run(service, workflow, output):
    from .studio_service import OPERATIONS
    workflow=validate(workflow);output=Path(output);output.mkdir();(output/'steps').mkdir()
    write_json(output/'workflow.json',workflow)
    summary=dict(schema='cryptonyan.studio-workflow-result/1',workflow_id=workflow['id'],workflow_identity=identity(workflow),
                 status='running',phase='steps',current_step=None,engine_validated=False,visual_quality_validated=False,
                 steps=[dict(id=s['id'],operation=s['operation'],status='pending') for s in workflow['steps']])
    completed={};current=None;context=service._context_identity()
    def verify(folder, receipt):
        if identity(read_json(safe_path(folder,'step.json')))!=identity(receipt):raise ValueError('Workflow step receipt changed')
        service._verify_artifacts(folder,receipt['artifacts'],exclude=('step.json',))
    def publish():
        write_json(output/'workflow-status.json',summary)
        service._workflow_progress(output.parent,progress(summary))
    def resolve(value):
        if isinstance(value,str):return value
        folder,receipt=completed[value['from_step']]
        verify(folder,receipt)
        target=safe_path(folder,'output/'+value['file']) if value['file'] else safe_path(folder,'output')
        if not target.exists():raise ValueError('A workflow output binding is missing')
        if target.is_file() and not any(a['file']==target.relative_to(folder).as_posix() for a in receipt['artifacts']):
            raise ValueError('Workflow binding must select a completed artifact')
        if target.is_dir() and not any(a['file'].startswith(target.relative_to(folder).as_posix()+'/') for a in receipt['artifacts']):
            raise ValueError('Workflow directory binding must contain completed artifacts')
        return service._handle(target)
    try:
        publish()
        for specification,current in zip(workflow['steps'],summary['steps']):
            checkpoint();current.update(status='running');summary['current_step']=current['id'];publish()
            if service._context_identity()!=context:raise ValueError('Configuration changed during workflow')
            folder=safe_path(output/'steps',current['id']);folder.mkdir()
            args=copy.deepcopy(specification['arguments'])
            for key,kind in OPERATIONS[specification['operation']].items():
                if kind=='path':args[key]=resolve(args[key])
                elif kind=='paths':args[key]=[resolve(v) for v in args[key]]
            record=dict(schema='cryptonyan.studio-workflow-step/1',id=current['id'],operation=specification['operation'],status='running',artifacts=[])
            write_json(folder/'step.json',record);write_json(folder/'request.json',dict(operation=specification['operation'],arguments=args))
            service._require(specification['operation']);paths=service._inputs(specification['operation'],args)
            checkpoint();result=service._dispatch(specification['operation'],args,paths,folder/'output');checkpoint()
            write_json(folder/'result.json',result)
            checks=[]
            for check in specification['checks']:
                actual=result
                try:
                    for key in check['path']:
                        actual=actual[int(key)] if isinstance(actual,list) and key.isdigit() else actual[key]
                    matches=identity(actual)==identity(check['equals'])
                except (KeyError,IndexError,TypeError,ValueError):matches=False
                checks.append(dict(path=check['path'],matched=matches))
            current['checks']=checks
            if any(not c['matched'] for c in checks):raise WorkflowRejected('Explicit workflow result check failed')
            checkpoint();record.update(status='succeeded',artifacts=service._artifacts(folder,exclude=('step.json',)))
            all_artifacts=[a for _,previous in completed.values() for a in previous['artifacts']]+record['artifacts']
            if len(all_artifacts)>2048 or sum(a['bytes'] for a in all_artifacts)>2*1024**3:raise ValueError('Workflow artifact budget exceeded')
            write_json(folder/'step.json',record);completed[current['id']]=(folder,record)
            current.update(status='succeeded',output=service._handle(folder/'output'));publish()
        summary['phase']='verifying';publish()
        for folder,record in completed.values():verify(folder,record)
        checkpoint();summary.update(status='succeeded',phase='complete',current_step=None);publish();return summary
    except Exception as error:
        status='cancelled' if isinstance(error,Cancelled) else 'timed_out' if isinstance(error,BudgetExpired) else 'failed'
        summary.update(status=status,error=type(error).__name__)
        if current is not None and current['status']=='running':
            current.update(status='rejected' if isinstance(error,WorkflowRejected) else status,error=type(error).__name__)
            receipt=safe_path(output/'steps',current['id'])/'step.json'
            if receipt.is_file():
                record=read_json(receipt);record.update(status=current['status'],error=type(error).__name__);write_json(receipt,record)
        for step in summary['steps']:
            if step['status']=='pending':step['status']='blocked'
        publish();raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('templates')
    make=sub.add_parser('make');make.add_argument('template',choices=list(TEMPLATES));make.add_argument('inputs',type=Path)
    check=sub.add_parser('validate');check.add_argument('workflow',type=Path)
    args=parser.parse_args(argv)
    if args.command=='templates':value=templates()
    elif args.command=='make':value=make_template(args.template,read_json(args.inputs))
    else:value=dict(valid=True,workflow=validate(read_json(args.workflow)),execution_started=False,domain_recipes_validated=False)
    print(json.dumps(value,allow_nan=False,ensure_ascii=True));return 0


if __name__=='__main__':raise SystemExit(main())
