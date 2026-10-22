# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import scene_selection as selection, agent_connect
from cryptonyan_asset_studio.reference_board import ReferenceService,create
from cryptonyan_asset_studio.mcp_stdio import MCPServer,tool_list
from cryptonyan_asset_studio.storage import write_json,digest
from test_cryptonyan_materials import png
from test_cryptonyan_agent_connect import LocalPeer


def facts():
    return {'schema':selection.SCHEMA,'blender':'4.3.2','source':{'file_name':'game.blend','saved':True,'dirty':True},
        'scene':{'name':'Game','frame':12,'subframe':.25,'fps':30,'unit_scale_m':1,'coordinate_policy':'Blender units'},
        'active':'Temple','objects':[{'summary':{'name':'Temple','type':'MESH','mesh':{'verts':8,'faces':6}},
        'world_matrix':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],'uv_maps':['UVMap'],'materials':[],
        'rig':None,'animation':{'action':None,'channel_count':0,'channels':[],'channels_truncated':False}}]}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='selection é ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.library=self.root/'library';self.folder=self.library/'scene-contexts/temple'
        self.image=self.root/'view.png';self.image.write_bytes(png())

    def publish(self):return selection.publish(self.library,'temple',facts(),self.image)

    def test_snapshot_roundtrip_without_mutating_facts_or_image(self):
        before=facts();original=copy.deepcopy(before);value=selection.publish(self.library,'temple',before,self.image)
        self.assertEqual(before,original);self.assertEqual(selection.load(self.folder),value)
        self.assertFalse(value['live_scene_control']);self.assertEqual(value['image']['kind'],'provided_png')
        self.image.unlink()
        self.assertEqual(selection.SelectionService(self.library).list()['snapshots'][0]['selected'],['Temple'])
        self.assertEqual(base64.b64decode(selection.SelectionService(self.library).image('temple')['data']),png())

    def test_metadata_only_export_and_missing_image(self):
        value=selection.publish(self.library,'temple',facts())
        self.assertIsNone(value['image'])
        with self.assertRaises(ValueError):selection.SelectionService(self.library).image('temple')

    def test_stale_metadata_and_image_tampering_are_rejected(self):
        value=self.publish();value['facts']['scene']['frame']=99;write_json(self.folder/'context.json',value)
        with self.assertRaisesRegex(ValueError,'identity'):selection.load(self.folder)
        value['facts']['scene']['frame']=12;write_json(self.folder/'context.json',value)
        (self.folder/'view.png').write_bytes(png((20,30,40)))
        with self.assertRaises(ValueError):selection.load(self.folder)

    def test_invalid_selection_nonfinite_numbers_limits_and_fields(self):
        for mutate in (lambda v:v.update(objects=[]),lambda v:v.update(active='Missing'),lambda v:v.update(objects=v['objects']*33),
                       lambda v:v['objects'][0].update(world_matrix=[[1]]),lambda v:v['scene'].update(fps=float('nan')),
                       lambda v:v['scene'].update(frame=True),lambda v:v.update(extra=True),lambda v:v['source'].update(saved=1)):
            value=facts();mutate(value)
            with self.assertRaises(ValueError):selection.publish(self.library,'bad',value)
        self.assertFalse((self.library/'scene-contexts/bad').exists())

    def test_existing_snapshot_traversal_and_reserved_board_namespace(self):
        self.publish();before=digest(self.folder/'context.json')
        with self.assertRaises(FileExistsError):self.publish()
        with self.assertRaises(ValueError):selection.SelectionService(self.library).read('../secret')
        self.assertEqual(digest(self.folder/'context.json'),before)
        other=self.root/'other';create(other/'scene-contexts','scene-contexts','Reserved name')
        with self.assertRaises(ValueError):selection.publish(other,'temple',facts())

    def test_failed_write_removes_only_owned_new_directory(self):
        with patch.object(selection,'write_json',side_effect=OSError('disk full')),self.assertRaises(OSError):self.publish()
        self.assertFalse(self.folder.exists());self.assertTrue(self.image.exists())
        self.publish()

    def test_namespace_symlink_and_image_symlink_rejected(self):
        self.library.mkdir();outside=self.root/'outside';outside.mkdir()
        try:(self.library/'scene-contexts').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('OS symlink privilege unavailable')
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(list(outside.iterdir()),[])

    def test_reuse_native_viewport_capture_without_scene_execution(self):
        value=facts()
        tool=NS(capture_viewport=lambda **kwargs:NS(text='native viewport',image_path=self.image,ok=True),ToolError=RuntimeError)
        with patch.object(selection,'blender_facts',return_value=value),patch.dict(sys.modules,{'bpy':NS(app=NS(background=False)),'loopcut.tools':tool}):
            result=selection.capture(self.library,'temple',viewport=True)
        self.assertEqual(result['image']['kind'],'loopcut_viewport')
        self.assertEqual(result['image']['note'],'native viewport')

    def test_background_viewport_is_rejected_before_publication(self):
        with patch.object(selection,'blender_facts',return_value=facts()),patch.dict(sys.modules,{'bpy':NS(app=NS(background=True)),
                  'loopcut.tools':NS(capture_viewport=lambda **kwargs:None,ToolError=RuntimeError)}),self.assertRaises(ValueError):
            selection.capture(self.library,'temple',viewport=True)
        self.assertFalse(self.folder.exists())

    def test_board_and_selection_libraries_coexist_and_mcp_image_is_native(self):
        self.publish();create(self.library/'board','board','Board')
        service=ReferenceService(self.library)
        self.assertEqual([b['board_id'] for b in service.boards()['boards']],['board'])
        server=MCPServer(object(),references=service);server.handle({'jsonrpc':'2.0','id':1,'method':'initialize'})
        response=server.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'reference_scene_image','arguments':{'snapshot_id':'temple'}}})
        self.assertEqual(response['result']['content'][0]['type'],'image')
        self.assertNotIn('reference_scene_read',[t['name'] for t in tool_list()])

    def test_real_exported_stdio_connection_reads_snapshots(self):
        self.publish();assets=self.root/'assets';assets.mkdir()
        profile=self.root/'connection.json'
        agent_connect.save_config(profile,{'schema':agent_connect.SCHEMA,'executor':'mock','python':sys.executable,
            'workspace':str(self.root/'jobs'),'asset_root':str(assets),'blender':'','game_project':'','comfy_profiles':'','reference_root':str(self.library)})
        peer=LocalPeer(profile,'claude');self.addCleanup(peer.close);peer.call('initialize')
        result=peer.tool('reference_scene_read',{'snapshot_id':'temple'})
        self.assertEqual(result['facts']['active'],'Temple')
        response=peer.call('tools/call',{'name':'reference_scene_image','arguments':{'snapshot_id':'temple'}})
        self.assertEqual(base64.b64decode(response['content'][0]['data']),png())
        from cryptonyan_asset_studio import mask_paint
        _,ref=mask_paint._reference(self.image)
        mask_paint.render({'schema':mask_paint.SCHEMA,'reference':ref,'intent':'Roof','strokes':[]},self.image,self.library/'masks/roof')
        self.assertEqual(peer.tool('reference_mask_read',{'mask_id':'roof'})['painting']['intent'],'Roof')
        response=peer.call('tools/call',{'name':'reference_mask_image','arguments':{'mask_id':'roof','kind':'mask'}})
        self.assertEqual(response['content'][0]['type'],'image')

    def test_snapshot_cli(self):
        self.publish();env={**os.environ,'PYTHONPATH':str(ROOT/'scripts/addons_core')}
        for command,path in (('check',self.folder),('list',self.library)):
            r=subprocess.run([sys.executable,'-m','cryptonyan_asset_studio.scene_selection',command,str(path)],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIsInstance(json.loads(r.stdout),dict)


BLENDER=os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')
@unittest.skipUnless(BLENDER,'Real Blender unavailable')
class BlenderTests(unittest.TestCase):
    def test_actual_selection_rig_material_and_sidebar_without_scene_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            r=subprocess.run([BLENDER,'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
                '--python',str(ROOT/'loopcut/harness/cryptonyan_context_fixture.py'),'--',temp],capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('CRYPTONYAN_CONTEXT_ASSERTIONS_PASSED',r.stdout)


if __name__=='__main__':unittest.main()
