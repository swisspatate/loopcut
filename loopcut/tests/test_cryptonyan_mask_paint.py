# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import base64
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import mask_paint as masks,material_layers
from cryptonyan_asset_studio.materials import pack_material,load_material
from cryptonyan_asset_studio.png_pixels import decode
from cryptonyan_asset_studio.storage import digest,write_json
from test_cryptonyan_materials import png


def project(width=16,height=8):
    return {'schema':masks.SCHEMA,'reference':{'sha256':'a'*64,'width':width,'height':height},'intent':'Roof',
        'strokes':[{'mode':'paint','radius_px':2,'value':255,'points':[[.25,.5],[.75,.5]]}]}


class MaskTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='mask é ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.image=self.root/'reference.png';self.image.write_bytes(png(width=16,height=8))
        self.project=project();self.project['reference']['sha256']=digest(self.image)

    def test_round_brush_continuous_caps_and_top_left_coordinates(self):
        value=self.project;mask=masks.rasterize(value)
        self.assertEqual(mask[4*16+8],255);self.assertEqual(mask[0],0);self.assertEqual(mask[7*16+15],0)
        value['strokes'][0]['points']=[[0,0]]
        mask=masks.rasterize(value);self.assertEqual(mask[0],255);self.assertEqual(mask[-1],0)

    def test_erase_grayscale_and_reordered_strokes(self):
        eraser={'mode':'erase','radius_px':1,'value':255,'points':[[.5,.5]]}
        self.project['strokes'].append(eraser)
        mask=masks.rasterize(self.project);self.assertEqual(mask[4*16+8],0);self.assertEqual(mask[4*16+5],255)
        self.project['strokes'].reverse();self.project['strokes'][-1]['value']=80
        self.assertEqual(masks.rasterize(self.project)[4*16+8],80)

    def test_render_freezes_reference_and_exports_greyscale_material_mask(self):
        value=masks.render(self.project,self.image,self.root/'mask')
        self.image.unlink()
        self.assertEqual(masks.load_bundle(self.root/'mask'),value)
        size,rgba=decode((self.root/'mask/mask.png').read_bytes())
        self.assertEqual(size,{'width':16,'height':8})
        self.assertTrue(all(rgba[i]==rgba[i+1]==rgba[i+2] and rgba[i+3]==255 for i in range(0,len(rgba),4)))

    def test_wrong_reference_tampered_output_and_strokes_rejected(self):
        self.project['reference']['sha256']='f'*64
        with self.assertRaises(ValueError):masks.render(self.project,self.image,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
        self.project['reference']['sha256']=digest(self.image);masks.render(self.project,self.image,self.root/'mask')
        path=self.root/'mask/strokes.json';value=json.loads(path.read_text());value['intent']='changed';write_json(path,value)
        with self.assertRaises(ValueError):masks.load_bundle(self.root/'mask')
        write_json(path,self.project);(self.root/'mask/mask.png').write_bytes(png())
        with self.assertRaises(ValueError):masks.load_bundle(self.root/'mask')

    def test_brush_limits_paths_nonfinite_and_bad_fields(self):
        for mutate in (lambda p:p.update(extra=1),lambda p:p['strokes'][0].update(radius_px=True),lambda p:p['strokes'][0].update(radius_px=129),
                       lambda p:p['strokes'][0].update(mode='code'),lambda p:p['strokes'][0].update(value=256),
                       lambda p:p['strokes'][0].update(points=[[float('nan'),0]]),lambda p:p['strokes'][0].update(points=[[-.1,0]]),
                       lambda p:p['reference'].update(width=4096,height=4096),lambda p:p.update(strokes=p['strokes']*129)):
            value=copy.deepcopy(self.project);mutate(value)
            with self.assertRaises(ValueError):masks.specification(value)
        with patch.object(masks,'MAX_WORK',1),self.assertRaises(ValueError):masks.rasterize(self.project)

    def test_existing_output_and_write_failure_never_damage_source(self):
        before=digest(self.image);masks.render(self.project,self.image,self.root/'mask')
        with self.assertRaises(FileExistsError):masks.render(self.project,self.image,self.root/'mask')
        with patch.object(masks,'write_json',side_effect=OSError('disk full')),self.assertRaises(OSError):masks.render(self.project,self.image,self.root/'failed')
        self.assertFalse((self.root/'failed').exists());self.assertEqual(digest(self.image),before)

    def test_self_contained_editor_and_no_overwrite(self):
        path=self.root/'editor.html';masks.editor(self.image,path)
        content=path.read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64,',content);self.assertIn('pointerdown',content)
        self.assertNotIn('src="http',content);self.assertNotIn('fetch(',content)
        with self.assertRaises(FileExistsError):masks.editor(self.image,path)

    def test_painted_mask_composes_existing_material_layers(self):
        masks.render(self.project,self.image,self.root/'mask')
        inputs=self.root/'sources';inputs.mkdir()
        for name,color in (('base',(0,0,0)),('white',(255,255,255))):
            (inputs/(name+'.png')).write_bytes(png(color,width=16,height=8))
            pack_material(inputs,{'base_color':name+'.png'},inputs/name)
        shutil.copyfile(self.root/'mask/mask.png',inputs/'mask.png')
        binding=lambda name:{'file':name,'sha256':digest(inputs/name)}
        spec={'schema':material_layers.SCHEMA,'id':'snow','base':binding('base/material.json'),'layers':[
            {'id':'snow','material':binding('white/material.json'),'mask':binding('mask.png'),'opacity':1,'channels':['base_color'],'blend':'mix'}]}
        material_layers.prepare(spec,inputs,self.root/'prepared');material_layers.compose(self.root/'prepared',self.root/'composed')
        load_material(self.root/'composed/material.json')
        rgba=decode((self.root/'composed/base_color.png').read_bytes())[1]
        self.assertEqual(rgba[(4*16+8)*4],255);self.assertEqual(rgba[0],0)

    def test_mask_service_and_native_mcp_images_are_bound_to_reference(self):
        from cryptonyan_asset_studio.reference_board import ReferenceService
        from cryptonyan_asset_studio.mcp_stdio import MCPServer
        library=self.root/'library'
        masks.render(self.project,self.image,library/'masks/roof')
        service=ReferenceService(library)
        self.assertEqual(service.mask_list()['masks'][0]['mask_id'],'roof')
        self.assertEqual(service.mask_read('roof')['painting']['intent'],'Roof')
        server=MCPServer(object(),references=service);server.handle({'jsonrpc':'2.0','id':1,'method':'initialize'})
        for kind,filename in (('mask','mask.png'),('reference','reference.png')):
            result=server.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'reference_mask_image',
                'arguments':{'mask_id':'roof','kind':kind}}})['result']
            self.assertFalse(result['isError']);self.assertEqual(result['content'][0]['type'],'image')
            self.assertEqual(base64.b64decode(result['content'][0]['data']),(library/'masks/roof'/filename).read_bytes())
        with self.assertRaises(ValueError):service.mask_read('../escape')
        with self.assertRaises(ValueError):service.mask_image('roof','unknown')

    def test_mask_service_rejects_tampered_mask(self):
        library=self.root/'library';masks.render(self.project,self.image,library/'masks/roof')
        (library/'masks/roof/mask.png').write_bytes(png())
        with self.assertRaises(ValueError):masks.MaskService(library).read('roof')

    def test_cli_editor_render_check(self):
        path=self.root/'strokes.json';write_json(path,self.project)
        prefix=[sys.executable,'-m','cryptonyan_asset_studio.mask_paint'];env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        for args in (['editor',str(self.image),'--output',str(self.root/'editor.html')],['render',str(path),'--reference',str(self.image),'--output',str(self.root/'mask')],['check',str(self.root/'mask')]):
            r=subprocess.run(prefix+args,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIsInstance(json.loads(r.stdout),dict)


NODE=shutil.which('node')
class JavaScriptTests(unittest.TestCase):
    def setUp(self):
        if not NODE:
            if os.environ.get('CI'):self.fail('Node required for mask editor CI validation')
            self.skipTest('Node unavailable; browser event/raster tests required in CI')

    def run_js(self,request):
        r=subprocess.run([NODE,str(ROOT/'loopcut/harness/cryptonyan_mask_browser_fixture.js'),
            str(ROOT/'scripts/addons_core/cryptonyan_asset_studio/mask_editor.js')],input=json.dumps(request),capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);return json.loads(r.stdout)

    def test_javascript_and_python_rasters_match_for_seeded_brush_cases(self):
        rng=random.Random(93);projects=[]
        for i in range(16):
            value=project(32,16);value['strokes']=[]
            for j in range(4):
                value['strokes'].append({'mode':'erase' if j%3==2 else 'paint','radius_px':rng.randint(1,5),
                    'value':rng.randint(0,255),'points':[[rng.randint(0,32)/32,rng.randint(0,16)/16] for k in range(rng.randint(1,5))]})
            projects.append(value)
        results=self.run_js({'mode':'raster','projects':projects})
        for value,result in zip(projects,results):self.assertEqual(result['pixels'],list(masks.rasterize(value)))

    def test_actual_pointer_undo_redo_save_and_wrong_reference_import_handlers(self):
        result=self.run_js({'mode':'interact','project':{**project(),'strokes':[]}})
        self.assertEqual(result['afterUndo']['strokes'],[])
        self.assertEqual(len(result['afterRedo']['strokes']),1)
        self.assertEqual(result['afterRedo']['strokes'][0]['points'],[[.25,.5],[.75,.5]])
        self.assertEqual(result['painted']['intent'],'Neige sur le toit')
        self.assertEqual(result['painted'],result['afterWrongReference'])
        self.assertEqual(result['pixels'],list(masks.rasterize(result['painted'])))
        self.assertIn('download',result['clicks'])


if __name__=='__main__':unittest.main()
