# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import camera_moves as cameras
from cryptonyan_asset_studio.creative_director import operations,make_plan
from cryptonyan_asset_studio.storage import digest,write_json
from cryptonyan_asset_studio.unreal_director import execute
from test_cryptonyan_director import Editor


def recipe():
    return {'schema':cameras.SCHEMA,'id':'TempleReveal','fps':30,'destination':'/Game/CryptoNyan/DirectedReviews/TempleCamera',
            'shots':[{'id':'Approach','move':'line','frames':90,'samples':10,'easing':'smoothstep',
                      'start_m':[-10,2,3],'end_m':[-4,2,2],'target_m':[0,0,1]},
                     {'id':'Orbit','move':'orbit','frames':120,'samples':30,'easing':'linear','center_m':[0,0,1],
                      'radius_m':5,'azimuth_deg':[0,270],'height_m':[2,3]}]}


class CameraTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='camera é ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.bundle=self.root/'bundle'

    def test_reproducible_program_no_mutation_and_director_compatibility(self):
        spec=recipe();before=copy.deepcopy(spec);data=cameras.program(spec)
        self.assertEqual(data,cameras.program(copy.deepcopy(spec)));self.assertEqual(spec,before)
        ops=operations(data['cinematic'])
        self.assertEqual([(s['start'],s['end']) for s in ops],[(0,90),(90,210)])
        self.assertEqual(ops[0]['keys'][0]['position_cm'],[-1000,200,300])
        self.assertEqual(ops[-1]['keys'][-1]['frame'],209)

    def test_line_endpoints_easing_and_look_at_angles(self):
        data=cameras.program(recipe());shot=data['cinematic']['shots'][0]
        self.assertEqual(shot['keys'][0]['position_m'],[-10,2,3])
        self.assertEqual(shot['keys'][-1]['position_m'],[-4,2,2])
        for key in shot['keys']:
            p,y=map(math.radians,key['rotation_rpy_deg'][1:])
            forward=[math.cos(p)*math.cos(y),math.cos(p)*math.sin(y),math.sin(p)]
            delta=[b-a for a,b in zip(key['position_m'],[0,0,1])];length=math.sqrt(sum(v*v for v in delta))
            self.assertLess(math.dist(forward,[v/length for v in delta]),1e-12)
        self.assertLess(shot['keys'][1]['position_m'][0],-10+6*shot['keys'][1]['frame']/89)

    def test_orbit_radius_height_and_unwrapped_rotation(self):
        spec=recipe();spec['shots']=spec['shots'][1:];spec['shots'][0]['azimuth_deg']=[0,720];spec['shots'][0]['samples']=100
        data=cameras.program(spec)
        keys=data['cinematic']['shots'][0]['keys']
        for key in keys:self.assertAlmostEqual(math.hypot(*key['position_m'][:2]),5)
        generated=operations(data['cinematic'])[0]['keys']
        self.assertAlmostEqual(abs(generated[-1]['rotation_rpy_deg'][2]-generated[0]['rotation_rpy_deg'][2]),720)
        self.assertAlmostEqual(keys[-1]['position_m'][2],4)

    def test_crane_and_truck_use_same_line_contract(self):
        for end in ([-10,2,8],[-10,8,3]):
            spec=recipe();spec['shots']=spec['shots'][:1];spec['shots'][0]['end_m']=end
            self.assertEqual(cameras.program(spec)['cinematic']['shots'][0]['keys'][-1]['position_m'],end)

    def test_invalid_paths_bounds_sampling_and_singularities(self):
        changes=[lambda s:s.update(destination='/Game/Existing'),lambda s:s.update(fps=True),lambda s:s.update(extra=1),
                 lambda s:s['shots'][0].update(end_m=[10,-2,0]),lambda s:s['shots'][0].update(start_m=[0,0,10]),
                 lambda s:s['shots'][0].update(end_m=s['shots'][0]['start_m']),lambda s:s['shots'][0].update(samples=200),
                 lambda s:s['shots'][0].update(easing='expression'),lambda s:s['shots'][1].update(samples=2),
                 lambda s:s['shots'][1].update(radius_m=float('nan')),lambda s:s['shots'][1].update(azimuth_deg=[-720,720]),
                 lambda s:s['shots'][1].update(id='approach')]
        for change in changes:
            spec=recipe();change(spec)
            with self.subTest(spec=spec),self.assertRaises(ValueError):cameras.program(spec)

    def test_bundle_check_tamper_and_no_overwrite(self):
        data=cameras.prepare(recipe(),self.bundle);self.assertEqual(cameras.load_program(self.bundle),data)
        with self.assertRaises(FileExistsError):cameras.prepare(recipe(),self.bundle)
        path=self.bundle/'cinematic.json';value=json.loads(path.read_text());value['fps']=60;write_json(path,value)
        with self.assertRaisesRegex(ValueError,'changed'):cameras.load_program(self.bundle)

    def test_camera_program_identity_tamper(self):
        data=cameras.prepare(recipe(),self.bundle);data['recipe']['fps']=24;write_json(self.bundle/'camera-program.json',data)
        with self.assertRaises(ValueError):cameras.load_program(self.bundle)

    def test_generated_recipe_runs_existing_unreal_protocol_adapter(self):
        game=self.root/'game';game.mkdir();write_json(game/'Test.uproject',{'FileVersion':3})
        editor=Editor(game)
        plan=make_plan(cameras.program(recipe())['cinematic'],game)
        path=self.root/'plan.json';write_json(path,plan)
        receipt=execute(path,self.root/'unreal.json',apply=True,unreal_module=editor)
        self.assertFalse(receipt['engine_validated'])
        self.assertEqual(receipt['camera_count'],2)

    def test_preview_failure_has_receipt_and_no_blend_claim(self):
        cameras.prepare(recipe(),self.bundle)
        with patch.object(cameras,'run_process',side_effect=RuntimeError('worker failed')),self.assertRaises(RuntimeError):
            cameras.preview(self.bundle,self.root/'failed',sys.executable)
        receipt=json.loads((self.root/'failed/operation.json').read_text())
        self.assertEqual(receipt['status'],'failed');self.assertNotIn('artifacts',receipt)
        with self.assertRaises(ValueError):cameras.preview(self.bundle,self.bundle/'nested',sys.executable)

    def test_cli_prepare_check(self):
        path=self.root/'recipe.json';write_json(path,recipe())
        prefix=[sys.executable,'-m','cryptonyan_asset_studio.camera_moves']
        env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        for args in (['prepare',str(path),'--output',str(self.bundle)],['check',str(self.bundle)]):
            r=subprocess.run(prefix+args,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIsInstance(json.loads(r.stdout),dict)


BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
@unittest.skipUnless(BLENDER,'Real Blender unavailable')
class BlenderTests(unittest.TestCase):
    def test_actual_camera_program_preview_and_sidebar(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);write_json(root/'recipe.json',recipe())
            result=subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
                '--python',str(ROOT/'loopcut/harness/cryptonyan_camera_fixture.py'),'--',str(root)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('CRYPTONYAN_CAMERA_ASSERTIONS_PASSED',result.stdout)


if __name__=='__main__':unittest.main()
