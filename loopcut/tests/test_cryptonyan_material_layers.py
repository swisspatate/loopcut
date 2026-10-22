# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio import material_layers as layers
from cryptonyan_asset_studio.materials import load_material, pack_material
from cryptonyan_asset_studio.png_pixels import decode, encode
from cryptonyan_asset_studio.storage import digest, write_json
from test_cryptonyan_materials import png


def filtered_png(mode, channels=3):
    """Independent PNG encoder fixture with varying left/up/diagonal predictors."""
    width, height = 3, 3
    raster = [bytes((13*x+31*y+41*c)%256 for x in range(width) for c in range(channels)) for y in range(height)]
    raw = bytearray()
    for y,row in enumerate(raster):
        raw.append(mode)
        for i,value in enumerate(row):
            a = row[i-channels] if i >= channels else 0
            b = raster[y-1][i] if y else 0
            c = raster[y-1][i-channels] if y and i >= channels else 0
            if mode == 0: predictor = 0
            elif mode == 1: predictor = a
            elif mode == 2: predictor = b
            elif mode == 3: predictor = (a+b)//2
            else:
                p=a+b-c
                candidates = [(abs(p-a),a),(abs(p-b),b),(abs(p-c),c)]
                predictor = min(enumerate(candidates), key=lambda pair: (pair[1][0],pair[0]))[1][1]
            raw.append((value-predictor)%256)
    def chunk(tag,data): return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    payload = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2 if channels==3 else 6,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    expected = bytearray()
    for row in raster:
        for x in range(width): expected.extend(row[x*channels:x*channels+3]+(row[x*channels+3:x*channels+4] if channels==4 else b'\xff'))
    return payload, expected


class RasterTests(unittest.TestCase):
    def test_all_png_row_filters_rgb_and_rgba(self):
        for mode in range(5):
            for channels in (3,4):
                with self.subTest(mode=mode,channels=channels):
                    data,expected=filtered_png(mode,channels)
                    self.assertEqual(decode(data), ({"width":3,"height":3},expected))

    def test_nonsquare_encode_roundtrip(self):
        rgb=bytes(range(18))
        size,rgba=decode(encode(3,2,rgb))
        self.assertEqual(size,{"width":3,"height":2})
        self.assertEqual(bytes(v for i,v in enumerate(rgba) if i%4!=3),rgb)

    def test_bad_crc_and_raster_budget(self):
        with self.assertRaises(ValueError): decode(png()+b'extra')
        with patch('cryptonyan_asset_studio.png_pixels.MAX_PIXELS',1),self.assertRaises(ValueError): decode(png())


class Fixture:
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='layers é ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.sources=self.root/'sources';self.sources.mkdir()
        for key,color,rough,normal in (('base',(0,0,0),0,(128,128,255)),('snow',(255,255,255),255,(180,128,244))):
            folder=self.sources/key;folder.mkdir()
            for role,rgb in {'base_color':color,'roughness':(rough,)*3,'normal':normal}.items():
                (folder/(role+'.png')).write_bytes(png(rgb))
            pack_material(folder,{role:role+'.png' for role in ('base_color','roughness','normal')},self.sources/(key+'-pbr'))
        (self.sources/'mask.png').write_bytes(png((128,)*3))
        self.spec={"schema":layers.SCHEMA,"id":"snow","base":self.binding('base-pbr/material.json'),"layers":[
            {"id":"snow","material":self.binding('snow-pbr/material.json'),"mask":self.binding('mask.png'),"opacity":1,
             "channels":["base_color","roughness","normal"],"blend":"mix"}]}
        self.bundle=self.root/'bundle';self.output=self.root/'result'

    def binding(self,relative):return {"file":relative,"sha256":digest(self.sources/relative)}

    def prepare(self):return layers.prepare(self.spec,self.sources,self.bundle)

    def pixels(self,role):return decode((self.output/(role+'.png')).read_bytes())[1]


class CompositionTests(Fixture,unittest.TestCase):
    def test_linear_color_scalar_and_normal_math(self):
        self.prepare();receipt=layers.compose(self.bundle,self.output)
        self.assertEqual(tuple(self.pixels('base_color')[:3]),(188,)*3)
        self.assertEqual(tuple(self.pixels('roughness')[:3]),(128,)*3)
        n=[v/127.5-1 for v in self.pixels('normal')[:3]]
        self.assertAlmostEqual(math.sqrt(sum(v*v for v in n)),1,delta=.01)
        self.assertTrue(n[0]>0 and n[2]>.9)
        self.assertFalse(receipt['engine_validated'])
        self.assertEqual(load_material(self.output/'material.json'),receipt['material'])

    def test_black_white_and_zero_opacity_exact_endpoints(self):
        for index,(mask,opacity,key) in enumerate(((0,1,'base'),(255,1,'snow'),(255,0,'base'))):
            (self.sources/'mask.png').write_bytes(png((mask,)*3));self.spec['layers'][0]['mask']=self.binding('mask.png')
            self.spec['layers'][0]['opacity']=opacity
            bundle=self.root/('b'+str(index));output=self.root/('o'+str(index))
            layers.prepare(self.spec,self.sources,bundle);layers.compose(bundle,output)
            for role in ('base_color','roughness','normal'):
                self.assertEqual(decode((output/(role+'.png')).read_bytes())[1],decode((self.sources/(key+'-pbr')/(role+'.png')).read_bytes())[1])

    def test_multiply_and_layer_order_are_explicit(self):
        self.spec['layers'][0]['blend']='multiply';self.spec['layers'][0]['channels']=['roughness']
        self.prepare();layers.compose(self.bundle,self.output)
        self.assertEqual(self.pixels('roughness')[0],0)
        self.assertEqual(self.pixels('base_color')[0],0)

    def test_ordered_layers_change_the_actual_pixels(self):
        self.spec['layers'][0]['channels']=['base_color']
        second=copy.deepcopy(self.spec['layers'][0]);second['id']='darken';second['material']=self.binding('base-pbr/material.json')
        self.spec['layers'].append(second)
        self.prepare();layers.compose(self.bundle,self.output)
        self.assertEqual(self.pixels('base_color')[0],137)
        self.spec['layers'].reverse()
        layers.prepare(self.spec,self.sources,self.root/'reverse-bundle')
        layers.compose(self.root/'reverse-bundle',self.root/'reverse-result')
        self.assertEqual(decode((self.root/'reverse-result/base_color.png').read_bytes())[1][0],188)

    def test_invalid_colored_mask_stops_public_composition_before_output(self):
        (self.sources/'mask.png').write_bytes(png((10,20,30)))
        self.spec['layers'][0]['mask']=self.binding('mask.png')
        self.prepare()
        with self.assertRaisesRegex(ValueError,'greyscale'):layers.compose(self.bundle,self.output)
        self.assertFalse(self.output.exists())

    def test_unselected_channels_preserved_and_rebuild_deterministic_without_originals(self):
        self.spec['layers'][0]['channels']=['base_color'];self.prepare()
        before=digest(self.sources/'base-pbr/normal.png')
        shutil.rmtree(self.sources)
        layers.compose(self.bundle,self.output);layers.compose(self.bundle,self.root/'second')
        self.assertEqual(digest(self.output/'normal.png'),before)
        for role in ('base_color','roughness','normal'):
            self.assertEqual(digest(self.output/(role+'.png')),digest(self.root/'second'/(role+'.png')))

    def test_source_and_snapshot_tampering_rejected(self):
        (self.sources/'mask.png').write_bytes(png((1,)*3))
        with self.assertRaises(ValueError):self.prepare()
        self.spec['layers'][0]['mask']=self.binding('mask.png');self.prepare()
        (self.bundle/'inputs/base/base_color.png').write_bytes(png((20,)*3))
        with self.assertRaises(ValueError):layers.compose(self.bundle,self.output)
        self.assertFalse(self.output.exists())

    def test_recipe_and_plan_identity_changes_rejected(self):
        plan=self.prepare();plan['recipe']['layers'][0]['opacity']=.25;write_json(self.bundle/'plan.json',plan)
        with self.assertRaises(ValueError):layers.load_bundle(self.bundle)

    def test_bad_scalar_mask_normal_and_alpha_rejected(self):
        for role in ('roughness','mask','normal'):
            value=png((30,100,20)) if role!='normal' else png((128,128,0))
            with self.subTest(role=role),self.assertRaises(ValueError):layers._pixels(value,role)
        payload,_=filtered_png(0,4)
        with self.assertRaisesRegex(ValueError,'opaque'):layers._pixels(payload,'base_color')

    def test_dimension_mismatch_missing_channel_and_limits_leave_no_output(self):
        (self.sources/'mask.png').write_bytes(png(width=1));self.spec['layers'][0]['mask']=self.binding('mask.png')
        with self.assertRaises(ValueError):self.prepare()
        (self.sources/'mask.png').write_bytes(png());self.spec['layers'][0]['mask']=self.binding('mask.png')
        self.spec['layers'][0]['channels']=['metallic']
        with self.assertRaises(ValueError):self.prepare()
        self.spec['layers'][0]['channels']=['base_color']
        for constant in ('MAX_BYTES','MAX_WORK'):
            with patch.object(layers,constant,1),self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_strict_recipes_and_paths(self):
        for change in (lambda s:s.update(extra=1),lambda s:s['base'].update(file='../escape'),lambda s:s['base'].update(sha256='bad'),
                       lambda s:s['layers'][0].update(opacity=float('nan')),lambda s:s['layers'][0].update(blend='multiply'),
                       lambda s:s['layers'][0].update(channels=['base_color']*2),lambda s:s.update(layers=s['layers']*9)):
            value=copy.deepcopy(self.spec);change(value)
            with self.assertRaises(ValueError):layers.specification(value)

    def test_outputs_never_overwrite_or_nest_in_sources(self):
        with self.assertRaises(ValueError):layers.prepare(self.spec,self.sources,self.sources/'prepared')
        self.prepare();layers.compose(self.bundle,self.output)
        before=digest(self.output/'material.json')
        with self.assertRaises(FileExistsError):layers.compose(self.bundle,self.output)
        self.assertEqual(digest(self.output/'material.json'),before)
        with self.assertRaises(ValueError):layers.compose(self.bundle,self.bundle/'output')

    def test_failed_preparation_cleans_new_folder(self):
        with patch.object(layers,'write_json',side_effect=OSError('disk full')),self.assertRaises(OSError):self.prepare()
        self.assertFalse(self.bundle.exists());self.assertTrue(self.sources.exists())

    def test_cli_prepare_check_compose(self):
        path=self.root/'recipe.json';write_json(path,self.spec)
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        prefix=[sys.executable,'-m','cryptonyan_asset_studio.material_layers']
        for args in (['prepare',str(path),'--source-root',str(self.sources),'--output',str(self.bundle)],['check',str(self.bundle)],['compose',str(self.bundle),'--output',str(self.output)]):
            result=subprocess.run(prefix+args,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIsInstance(json.loads(result.stdout),dict)


BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
@unittest.skipUnless(BLENDER,'Real Blender unavailable')
class BlenderTests(Fixture,unittest.TestCase):
    def test_real_sidebar_composition_packed_shader_and_glb(self):
        write_json(self.root/'recipe.json',self.spec)
        result=subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
            '--python',str(ROOT/'loopcut/harness/cryptonyan_layers_fixture.py'),'--',str(self.root)],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('CRYPTONYAN_LAYERS_ASSERTIONS_PASSED',result.stdout)


if __name__=='__main__':unittest.main()
