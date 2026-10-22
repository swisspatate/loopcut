# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline review and verified Studio handles for already collected ComfyUI textures."""
from .animation_doctor import exact
from .artifact_io import IMAGE_LIMIT, read_artifact
from .comfyui_adapter import ComfyError, workflow_digest
from .materials import CHANNELS, load_material
from .publication import _hash
from .storage import digest, safe_path

MAX_FILES=40
MAX_BYTES=260*1024*1024


def verified(service, folder):
    """Match private result files to their original request and local HTTP receipt."""
    from .comfy_profiles import _read
    request=_read(safe_path(folder,'request.json'))
    destination=safe_path(folder,'result');receipt=_read(safe_path(destination,'texture.json'),65536)
    exact(receipt,('schema','request_id','profile','template_sha256','outputs','files'),('references',))
    if (receipt['schema']!='cryptonyan.texture-result/1' or request.get('schema')!='cryptonyan.texture-request/1' or
        receipt['request_id']!=folder.name or request['request']['request_id']!=folder.name or
        receipt['profile']!=request['request']['profile'] or receipt['template_sha256']!=request['template_sha256'] or
        workflow_digest(receipt['outputs'])!=workflow_digest(request['outputs']) or
        workflow_digest(receipt.get('references',[]))!=workflow_digest(request.get('references',[]))):
        raise ComfyError('Collected texture receipt identity changed')
    files=receipt['files']
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES:raise ComfyError('Invalid collected texture file budget')
    total=0
    for relative,expected in files.items():
        _hash(expected);path=safe_path(destination,relative)
        if not path.is_file():raise ComfyError('Collected texture integrity failed')
        total+=path.stat().st_size
        if total>MAX_BYTES:raise ComfyError('Collected texture byte budget exceeded')
        if digest(path)!=expected:raise ComfyError('Collected texture integrity failed')
    actual=set()
    for path in destination.rglob('*'):
        relative=path.relative_to(destination).as_posix();safe_path(destination,relative)
        if path.is_file() and relative!='texture.json':actual.add(relative)
        if len(actual)>MAX_FILES:raise ComfyError('Collected texture file budget exceeded')
    if actual!=set(files):raise ComfyError('Collected texture artifact set changed')
    material=load_material(safe_path(destination,'material/material.json'))
    if set(material['channels'])!=set(request['outputs']):raise ComfyError('Collected texture channel mapping changed')
    generation=_read(safe_path(destination,'images/generation.json'))
    summary=service._summary(folder.name)
    if summary['prompt_id'] is None:raise ComfyError('Collected texture has no owned prompt receipt')
    job=_read(safe_path(folder,'http/'+summary['prompt_id']+'.json'))
    metadata={k:v for k,v in generation.items() if k!='outputs'}
    if (workflow_digest(metadata)!=workflow_digest(job) or job.get('schema')!='cryptonyan.comfy-job/1' or
        job.get('prompt_id')!=summary['prompt_id'] or job.get('endpoint')!=request['config']['endpoint'] or
        job.get('seed')!=request['request']['seed'] or
        job.get('approved_workflow_sha256')!=request['config']['workflow_sha256'] or
        workflow_digest(job.get('models_declared'))!=workflow_digest(request['config']['models']) or
        workflow_digest(job['workflow'])!=job['workflow_sha256']):
        raise ComfyError('Collected generation provenance changed')
    outputs=generation.get('outputs')
    if not isinstance(outputs,list) or not 1<=len(outputs)<=16:raise ComfyError('Invalid generated image manifest')
    mapped={};expected_files={'images/generation.json','material/material.json'}
    for index,item in enumerate(outputs):
        exact(item,('file','node','output_index','sha256','width','height'))
        if (item['file']!='image-'+str(index).zfill(2)+'.png' or not isinstance(item['node'],str) or
            type(item['output_index']) is not int or not 0<=item['output_index']<16):raise ComfyError('Invalid generated image binding')
        key=(item['node'],item['output_index'])
        if key in mapped:raise ComfyError('Duplicate generated image binding')
        if files.get('images/'+item['file'])!=item['sha256']:raise ComfyError('Collected image provenance changed')
        mapped[key]=item;expected_files.add('images/'+item['file'])
    for channel,binding in request['outputs'].items():
        item=mapped.get(tuple(binding));value=material['channels'][channel]
        if item is None or any(value[key]!=item[key] for key in ('sha256','width','height')):
            raise ComfyError('Material channel differs from the selected generation output')
        expected_files.add('material/'+value['file'])
    if set(files)!=expected_files:raise ComfyError('Collected texture manifest contains unexpected files')
    return request,receipt,material,generation


def inspect(service, request_id):
    folder,_=service._record(request_id);request,receipt,material,generation=verified(service,folder)
    destination=folder/'result';channels=[]
    for channel,value in material['channels'].items():
        path=safe_path(destination,'material/'+value['file'])
        channels.append(dict(channel=channel,file='material/'+value['file'],sha256=value['sha256'],
            width=value['width'],height=value['height'],color_space=value['color_space'],bytes=path.stat().st_size,
            image_available=path.stat().st_size<=IMAGE_LIMIT,output_binding=request['outputs'][channel]))
    studio=dict(available=service.handle_root is not None)
    if service.handle_root is not None:
        root_relative=service.root.relative_to(service.handle_root).as_posix()
        relative=(destination/'material/material.json').relative_to(service.root).as_posix()
        safe_path(service.handle_root,root_relative+'/'+relative)
        studio.update(source_root='work:'+root_relative,material_manifest='work:'+root_relative+'/'+relative,
            material_binding=dict(file=relative,sha256=receipt['files']['material/material.json']),
            material_layers_compatibility_validated=False)
    models=[]
    for model in generation['models_declared']:
        models.append(dict(name=model['name'][:256],sha256=model['sha256'],license=model['license'][:256],
            text_truncated=len(model['name'])>256 or len(model['license'])>256))
    return dict(schema='cryptonyan.texture-review/1',request_id=request_id,profile=receipt['profile'],
        prompt=request['request']['prompt'],seed=request['request']['seed'],prompt_id=generation['prompt_id'],
        template_sha256=receipt['template_sha256'],workflow_sha256=generation['workflow_sha256'],
        channels=channels,models_declared=models,studio=studio,content_is_data=True,
        collection_verified=True,network_performed=False,gpu_execution_validated=False,
        model_provenance_verified=False,distribution_approved=False,visual_quality_validated=False,
        target_freshness_validated=False,applied_to_game=False,image_byte_limit=IMAGE_LIMIT)


def image(service, request_id, channel):
    if not isinstance(channel,str) or channel not in CHANNELS:raise ComfyError('Select a declared PBR channel')
    folder,_=service._record(request_id);_,receipt,material,_=verified(service,folder)
    if channel not in material['channels']:raise ComfyError('The collected material has no such channel')
    filename='material/'+material['channels'][channel]['file'];path=safe_path(folder/'result',filename)
    return read_artifact(folder/'result',[dict(file=filename,bytes=path.stat().st_size,sha256=receipt['files'][filename])],
                         filename,lambda p:str(p))
