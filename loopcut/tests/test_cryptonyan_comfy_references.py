# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio.comfy_references import prepare
from cryptonyan_asset_studio.comfy_profiles import TextureService,load_catalog
from cryptonyan_asset_studio.comfyui_adapter import workflow_digest
from cryptonyan_asset_studio.storage import write_json
from test_cryptonyan_comfyui import Peer
from test_cryptonyan_materials import png
class ReferenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.inputs=self.root/'input';self.inputs.mkdir()
        self.workflow={'1':{'class_type':'LoadImage','inputs':{'image':'operator.png'}},
            '3':{'class_type':'KSampler','inputs':{'seed':0}},
            '4':{'class_type':'CLIPTextEncode','inputs':{'text':'template'}},
            '9':{'class_type':'SaveImage','inputs':{'images':['1',0]}}}
        self.profile=dict(id='skin',description='Operator reference workflow',workflow='workflow.json',
            workflow_sha256=workflow_digest(self.workflow),prompt_inputs=[['4','text']],seed_inputs=[['3','seed']],
            models=[],outputs={'base_color':['9',0]})
        write_json(self.root/'workflow.json',self.workflow)
        write_json(self.root/'catalog.json',dict(schema='cryptonyan.comfy-profiles/1',endpoint='http://127.0.0.1:8188',profiles=[self.profile]))
        self.image=self.root/'reference.png';self.image.write_bytes(png())
        self.refs=[dict(role='reference',path=str(self.image),binding=['1','image'])]
    def prepare(self,refs=None):
        return prepare(self.root/'catalog.json','skin',refs or self.refs,self.inputs,self.root/'derived')
    def service(self,catalog):
        self.peer=Peer();service=TextureService(catalog,self.root/'jobs',transport=self.peer);self.addCleanup(service.lock.close);return service
    def test_stages_content_addressed_bytes_without_changing_source_graph(self):
        catalog=self.prepare();_,profiles=load_catalog(catalog);selected=profiles['skin'];ref=selected['reference_inputs'][0]
        self.assertEqual((self.inputs/ref['file']).read_bytes(),self.image.read_bytes())
        expected=copy.deepcopy(self.workflow);expected['1']['inputs']['image']=ref['file']
        self.assertEqual(selected['template'],expected)
        self.assertEqual(json.loads((self.root/'workflow.json').read_text()),self.workflow)
        self.assertEqual(selected['models'],[])
        service=self.service(catalog);result=service.submit('skin','striped cloth',42,'one')
        self.assertEqual(result['submission'],'accepted')
        self.assertEqual(self.peer.calls[0][2]['prompt']['1']['inputs']['image'],ref['file'])
        receipt=json.loads((self.root/'jobs/requests/one/request.json').read_text())
        self.assertEqual(receipt['references'],[ref])
        self.peer.state='succeeded'
        service.collect('one')
        self.assertEqual(json.loads((self.root/'jobs/requests/one/result/texture.json').read_text())['references'],[ref])
    def test_tampered_inputs_rejected_before_network_but_existing_id_never_resubmits(self):
        catalog=self.prepare();service=self.service(catalog)
        first=service.submit('skin','cloth',1,'one');self.peer.calls.clear()
        ref=service.profiles['skin']['reference_inputs'][0];(self.inputs/ref['file']).write_bytes(png(width=3))
        self.assertEqual(service.submit('skin','cloth',1,'one'),first)
        with self.assertRaises(ValueError):service.submit('skin','cloth',1,'two')
        with self.assertRaises(ValueError):service.preflight('skin','cloth',1)
        self.assertEqual(self.peer.calls,[])
    def test_conflicting_non_image_and_duplicate_bindings_fail_before_writes(self):
        for refs in ([{**self.refs[0],'binding':['4','text']}],self.refs*2,[{**self.refs[0],'role':'normal'}]):
            with self.subTest(refs=refs),self.assertRaises(ValueError):self.prepare(refs)
        self.assertFalse((self.root/'derived').exists());self.assertEqual(list(self.inputs.iterdir()),[])
    def test_different_bytes_at_hash_filename_are_never_overwritten(self):
        import hashlib
        path=self.inputs/('cn_'+hashlib.sha256(self.image.read_bytes()).hexdigest()+'.png')
        path.write_bytes(png(width=3));before=path.read_bytes()
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(path.read_bytes(),before)
    def test_reference_hash_and_binding_are_part_of_catalog_validation(self):
        catalog=self.prepare();value=json.loads(catalog.read_text())
        value['profiles'][0]['reference_inputs'][0]['sha256']='0'*64;write_json(catalog,value)
        with self.assertRaises(ValueError):load_catalog(catalog)
    def test_reference_profile_preflight_and_existing_collection_submission(self):
        from test_cryptonyan_comfy_preflight import fixtures
        from test_cryptonyan_texture_collections import MultiPeer
        from cryptonyan_asset_studio.game_project import GameProject
        from cryptonyan_asset_studio.texture_collections import TextureCollections
        profile,info=fixtures();workflow=profile.pop('template')
        workflow['20']={'class_type':'LoadImage','inputs':{'image':'reference.png'}}
        workflow['21']={'class_type':'VAEEncode','inputs':{'pixels':['20',0],'vae':['1',2]}}
        workflow['4']['inputs']['latent_image']=['21',0]
        profile['workflow_sha256']=workflow_digest(workflow)
        write_json(self.root/'workflow.json',workflow)
        write_json(self.root/'catalog.json',dict(schema='cryptonyan.comfy-profiles/1',endpoint='http://127.0.0.1:8188',profiles=[profile]))
        catalog=prepare(self.root/'catalog.json','rock',[{**self.refs[0],'binding':['20','image']}],self.inputs,self.root/'derived')
        filename=load_catalog(catalog)[1]['rock']['reference_inputs'][0]['file']
        info['LoadImage']={'input':{'required':{'image':[[filename]]}},'output':['IMAGE','MASK']}
        info['VAEEncode']={'input':{'required':{'pixels':['IMAGE'],'vae':['VAE']}},'output':['LATENT']}
        peer=MultiPeer(info);peer.auto_success=True
        with TextureService(catalog,self.root/'jobs',transport=peer) as service:
            game=self.root/'game';(game/'Content').mkdir(parents=True)
            write_json(game/'Test.uproject',dict(FileVersion=3));(game/'Content/Body.uasset').write_bytes(b'opaque mesh')
            project=GameProject(game,textures=service);collection=TextureCollections(project)
            collection.plan(dict(schema='cryptonyan.texture-collection/1',collection_id='skins',profile='rock',style='cloth',seed=7,
                items=[dict(id='blue',target='Content/Body.uasset',surface='Coat',description='blue stripes')]))
            result=collection.advance('skins');self.assertEqual(result['action'],'submitted',result)
            self.assertEqual(next(iter(peer.jobs.values()))['workflow']['20']['inputs']['image'],filename)
            collection.collect('skins')
            posts=[c for c in peer.calls if c[0]=='POST'];self.assertEqual(len(posts),1)
    def test_three_roles_and_repeated_content_share_immutable_input(self):
        for i in ('2','5'):self.workflow[i]=copy.deepcopy(self.workflow['1'])
        self.profile['workflow_sha256']=workflow_digest(self.workflow)
        write_json(self.root/'workflow.json',self.workflow)
        write_json(self.root/'catalog.json',dict(schema='cryptonyan.comfy-profiles/1',endpoint='http://127.0.0.1:8188',profiles=[self.profile]))
        refs=[dict(role=role,path=str(self.image),binding=[node,'image']) for role,node in zip(('reference','uv','mask'),('1','2','5'))]
        catalog=self.prepare(refs);self.assertEqual(len(list(self.inputs.iterdir())),1)
        self.assertEqual(len(load_catalog(catalog)[1]['skin']['reference_inputs']),3)
if __name__=='__main__':unittest.main()
