# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio.garment_fit import run, specification
from cryptonyan_asset_studio.storage import digest
from cryptonyan_asset_studio.materials import read_png
from cryptonyan_asset_studio.executors import WorkerFailure
BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
def spec():
    return dict(body='Body',garment='Garment',clearance_m=.02,max_distance_m=.2,max_influences=2,uv_size=32,
        capture=dict(armature='ExistingRig',action='Preview',start_frame=1,end_frame=3,step_frames=1,
          settings=dict(root='Origin',bones=['Tip'],loop=False,motion='in_place',contact_space='unknown',contacts=[])))
class ContractTests(unittest.TestCase):
    def test_invalid_budgets_names_and_sampling(self):
        for key,value in [('clearance_m',.3),('max_influences',True),('uv_size',513),('garment','Body')]:
            with self.subTest(key=key),self.assertRaises(ValueError): specification({**spec(),key:value})
        s=spec();s['capture']['end_frame']=122
        with self.assertRaises(ValueError): specification(s)
    def test_specification_does_not_mutate_input(self):
        value=spec();before=copy.deepcopy(value);specification(value);self.assertEqual(value,before)
@unittest.skipUnless(BLENDER,'Blender executable unavailable')
class BlenderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
    def fixture(self,*flags):
        source=self.root/'source.blend'
        result=subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
          '--python',str(ROOT/'loopcut/harness/cryptonyan_garment_fixture.py'),'--',str(source),*flags],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);return source
    def test_real_fit_weights_masks_poses_and_saved_copy(self):
        source=self.fixture();before=digest(source);out=self.root/'fit'
        receipt=run(source,spec(),out,BLENDER)
        self.assertEqual(receipt['status'],'candidate_created_review_required')
        report=receipt['report'];self.assertEqual(report['moved_vertices'],4)
        self.assertAlmostEqual(report['max_displacement_m'],.01,places=5)
        self.assertEqual(report['penetrating_samples'],0)
        self.assertEqual([s['frame'] for s in report['samples']],[1,2,3])
        self.assertEqual(report['weight_audit']['findings'],[])
        self.assertEqual(digest(source),before);self.assertNotEqual(digest(out/'candidate.blend'),before)
        for filename in ('body-uv-mask.png','garment-uv-mask.png'):
            self.assertEqual(read_png(out/filename)[1],dict(width=32,height=32))
        self.assertFalse(report['surface_collision_certified'])
        with self.assertRaises(FileExistsError):run(source,spec(),out,BLENDER)
    def test_pose_intersections_are_reported_instead_of_certifying_cloth(self):
        source=self.fixture('--penetrate');value=spec();value['max_influences']=1
        result=run(source,value,self.root/'fit',BLENDER)
        self.assertGreater(result['report']['penetrating_samples'],0)
        self.assertGreater(result['report']['samples'][-1]['max_depth_m'],.1)
        self.assertFalse(result['visual_quality_validated'])
    def test_far_garment_fails_without_touching_source(self):
        source=self.fixture('--far');before=digest(source)
        with self.assertRaises(WorkerFailure):run(source,spec(),self.root/'fit',BLENDER)
        self.assertEqual(digest(source),before);self.assertFalse((self.root/'fit/candidate.blend').exists())
    def test_open_body_fails_before_candidate_save(self):
        source=self.fixture('--open')
        with self.assertRaises(WorkerFailure):run(source,spec(),self.root/'fit',BLENDER)
        self.assertFalse((self.root/'fit/candidate.blend').exists())
if __name__=='__main__':unittest.main()
