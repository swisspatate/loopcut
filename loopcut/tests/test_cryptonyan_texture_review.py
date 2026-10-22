# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline ComfyUI image review, source guards and actual Studio PBR composition."""
import base64
import copy
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

import test_cryptonyan_comfy_profiles as fixtures
from cryptonyan_asset_studio import artifact_io
from cryptonyan_asset_studio.animation_doctor import read_json
from cryptonyan_asset_studio.comfy_profiles import TextureService
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.png_pixels import decode
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.studio_service import StudioService
from cryptonyan_asset_studio.studio_workflows import make_template


class ReviewTests(unittest.TestCase):
    save=fixtures.ProfileTests.save

    def setUp(self):
        fixtures.ProfileTests.setUp(self)
        self.service.lock.close();self.work=self.root/'work'
        self.service=TextureService(self.root/'profiles.json',self.work/'textures',transport=self.peer,handle_root=self.work)
        self.addCleanup(self.service.lock.close)

    def open(self):return fixtures.ProfileTests.open(self)

    def collect(self, request_id='rock',color=(80,120,160)):
        self.peer.image=fixtures.png(color);self.peer.state='succeeded'
        self.service.submit('rock','rock texture',42,request_id)
        return self.service.collect(request_id)

    def result(self,request_id='rock'):return self.service._folder(request_id)/'result'

    def project(self):
        root=self.root/'game';root.mkdir();write_json(root/'Game.uproject',{'FileVersion':3,'EngineAssociation':'5.8'})
        target=root/'Content/Rock.uasset';target.parent.mkdir();target.write_bytes(b'opaque fixture package')
        project=GameProject(root,self.service)
        project.texture_submit('bound','Content/Rock.uasset','Rock / Stone','rock','rock texture',42)
        self.peer.state='succeeded';self.service.collect('bound')
        return project,target

    def test_inspection_is_offline_read_only_and_returns_exact_channel_provenance(self):
        self.collect();calls=len(self.peer.calls)
        # Windows byte locks forbid hashing an active owner lock. Inventory
        # those files, and verify every data file's bytes across the read.
        def snapshot():
            return {p.relative_to(self.work).as_posix():None if p.suffix=='.lock' else digest(p)
                    for p in self.work.rglob('*') if p.is_file()}
        before=snapshot()
        with patch.object(self.service,'transport',side_effect=AssertionError('No HTTP during review')):
            review=self.service.inspect('rock')
        self.assertEqual(review['profile'],'rock');self.assertEqual(review['seed'],42)
        self.assertEqual(review['template_sha256'],self.profile['workflow_sha256'])
        self.assertEqual(review['channels'][0]['output_binding'],['9',0])
        self.assertEqual(review['channels'][0]['color_space'],'sRGB')
        self.assertEqual((review['channels'][0]['width'],review['channels'][0]['height']),(2,2))
        self.assertTrue(review['collection_verified']);self.assertTrue(review['content_is_data'])
        for field in ('network_performed','gpu_execution_validated','target_freshness_validated',
                      'model_provenance_verified','distribution_approved','visual_quality_validated','applied_to_game'):
            self.assertFalse(review[field],field)
        self.assertEqual(calls,len(self.peer.calls))
        self.assertEqual(before,snapshot())

    def test_native_image_preserves_original_bytes_and_mcp_image_type(self):
        self.collect();calls=len(self.peer.calls)
        image=self.service.image('rock','base_color')
        self.assertEqual(base64.b64decode(image['data']),self.peer.image);self.assertEqual(image['mimeType'],'image/png')
        server=MCPServer(None,textures=self.service);server.handle({'jsonrpc':'2.0','id':0,'method':'initialize'})
        result=server.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
            'name':'texture_image','arguments':{'request_id':'rock','channel':'base_color'}}})
        self.assertFalse(result['result']['isError']);self.assertEqual(result['result']['content'][0]['type'],'image')
        self.assertEqual(len(self.peer.calls),calls)

    def test_missing_uncollected_and_uncertain_requests_do_not_trigger_generation(self):
        self.service.submit('rock','rock texture',42,'waiting');self.peer.fail_submit=True
        self.service.submit('rock','rock texture',42,'uncertain');calls=len(self.peer.calls)
        for request in ('missing','waiting','uncertain'):
            for method in (lambda:self.service.inspect(request),lambda:self.service.image(request,'base_color')):
                with self.subTest(request=request),self.assertRaises((ValueError,OSError)):method()
        self.assertEqual(len(self.peer.calls),calls)

    def test_absent_or_invalid_channels_never_synthesize_maps(self):
        self.collect();calls=len(self.peer.calls)
        for channel in ('normal','roughness','metallic','../images/image-00.png','occlusion',None,[],True):
            with self.subTest(channel=channel),self.assertRaises(ValueError):self.service.image('rock',channel)
        self.assertEqual(len(self.peer.calls),calls)

    def test_inspector_handles_are_usable_by_the_existing_studio_input_guard(self):
        self.collect();review=self.service.inspect('rock');handoff=review['studio']
        assets=self.root/'assets';assets.mkdir()
        with StudioService(self.work,assets) as studio:
            root=studio._input(handoff['source_root']);manifest=studio._input(handoff['material_manifest'])
            self.assertEqual(manifest,root/handoff['material_binding']['file'])
            self.assertEqual(digest(manifest),handoff['material_binding']['sha256'])
        self.assertEqual(handoff['source_root'],'work:textures')

    def test_two_collected_textures_feed_actual_pbr_layers_without_further_http(self):
        self.collect('black',(0,0,0));self.collect('white',(255,255,255))
        black=self.service.inspect('black')['studio'];white=self.service.inspect('white')['studio']
        mask=self.service.root/'authored/mask.png';mask.parent.mkdir();mask.write_bytes(fixtures.png((128,)*3))
        recipe=dict(schema='cryptonyan.material-layers/1',id='mixed',base=black['material_binding'],layers=[
            dict(id='white',material=white['material_binding'],mask={'file':'authored/mask.png','sha256':digest(mask)},
                 opacity=1,channels=['base_color'],blend='mix')])
        workflow=make_template('material_layers',dict(recipe=recipe,source_root=black['source_root']))
        assets=self.root/'assets';assets.mkdir();calls=len(self.peer.calls)
        with patch.object(self.service,'transport',side_effect=AssertionError('No more GPU requests')):
            with StudioService(self.work,assets) as studio:
                result=studio.execute('compose','workflow_run',{'workflow':workflow})
                self.assertEqual(result['status'],'succeeded',result)
                output=studio.operations/'compose/output/steps/compose/output/base_color.png'
                self.assertEqual(tuple(decode(output.read_bytes())[1][:3]),(188,)*3)
        self.assertEqual(calls,len(self.peer.calls))

    def test_standalone_service_does_not_invent_a_studio_workspace(self):
        self.service.lock.close()
        self.service=TextureService(self.root/'profiles.json',self.work/'textures',transport=self.peer)
        self.addCleanup(self.service.lock.close);self.collect()
        self.assertEqual(self.service.inspect('rock')['studio'],{'available':False})

    def test_handle_root_must_contain_a_separate_texture_subdirectory(self):
        for root in (self.root/'outside',self.work/'textures'):
            with self.subTest(root=root),self.assertRaises(ValueError):
                TextureService(self.root/'profiles.json',self.work/'textures',transport=self.peer,handle_root=root)

    def test_collected_snapshot_survives_profile_removal_without_network_or_recollection(self):
        self.collect();self.service.lock.close();self.catalog['profiles']=[];self.save()
        self.service=TextureService(self.root/'profiles.json',self.work/'textures',transport=self.peer,handle_root=self.work)
        self.addCleanup(self.service.lock.close);calls=len(self.peer.calls)
        self.assertEqual(self.service.inspect('rock')['profile'],'rock')
        self.assertEqual(base64.b64decode(self.service.image('rock','base_color')['data']),self.peer.image)
        self.assertEqual(calls,len(self.peer.calls))

    def test_receipt_identity_mapping_and_file_set_changes_are_rejected(self):
        self.collect();path=self.result()/'texture.json';original=read_json(path)
        for field,value in (('request_id','other'),('profile','other'),('template_sha256','b'*64),
                            ('outputs',{'base_color':['9',1]}),('files',{}),('references',[{'changed':True}])):
            altered=copy.deepcopy(original);altered[field]=value;write_json(path,altered)
            with self.subTest(field=field),self.assertRaises(ValueError):self.service.inspect('rock')
        write_json(path,original);extra=self.result()/'extra.txt';extra.write_text('extra',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'set changed'):self.service.image('rock','base_color')
        extra.unlink();self.assertTrue(self.service.inspect('rock')['collection_verified'])

    def test_corrupted_images_and_symlinks_block_both_collect_reuse_and_review(self):
        self.collect();image=self.result()/'material/base_color.png';original=image.read_bytes()
        image.write_bytes(fixtures.png((255,0,0)))
        for method in (lambda:self.service.collect('rock'),lambda:self.service.inspect('rock'),lambda:self.service.image('rock','base_color')):
            with self.assertRaisesRegex(ValueError,'integrity'):method()
        image.unlink();outside=self.root/'outside.png';outside.write_bytes(original)
        try:image.symlink_to(outside)
        except OSError:
            image.write_bytes(original);return  # Byte corruption above runs on all Windows accounts.
        with self.assertRaises(ValueError):self.service.inspect('rock')

    def test_generation_and_http_provenance_must_agree_after_manifest_rehash(self):
        self.collect();path=self.result()/'images/generation.json';original=path.read_bytes();receipt=self.result()/'texture.json';initial=read_json(receipt)
        for field,value in (('seed',99),('approved_workflow_sha256','b'*64),('models_declared',[]),('workflow_sha256','b'*64)):
            generation=json.loads(original);generation[field]=value;write_json(path,generation)
            changed=copy.deepcopy(initial);changed['files']['images/generation.json']=digest(path);write_json(receipt,changed)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'provenance'):self.service.inspect('rock')
        path.write_bytes(original);write_json(receipt,initial)
        summary=self.service._summary('rock');job=self.service._folder('rock')/'http'/(summary['prompt_id']+'.json')
        value=read_json(job);value['seed']=99;write_json(job,value)
        with self.assertRaisesRegex(ValueError,'provenance'):self.service.inspect('rock')

    def test_repacked_material_cannot_replace_a_selected_generation_output(self):
        self.collect();folder=self.result();image=folder/'material/base_color.png';image.write_bytes(fixtures.png((255,0,0)))
        material=read_json(folder/'material/material.json');material['channels']['base_color']['sha256']=digest(image)
        write_json(folder/'material/material.json',material);receipt=read_json(folder/'texture.json')
        for relative in ('material/base_color.png','material/material.json'):receipt['files'][relative]=digest(folder/relative)
        write_json(folder/'texture.json',receipt)
        with self.assertRaisesRegex(ValueError,'selected generation'):self.service.inspect('rock')

    def test_oversized_native_image_is_reported_and_refused_without_resampling(self):
        self.peer.state='succeeded';image=fixtures.png();payload=b'x'*(artifact_io.IMAGE_LIMIT+1);tag=b'tEXt'
        chunk=struct.pack('>I',len(payload))+tag+payload+struct.pack('>I',zlib.crc32(tag+payload))
        self.peer.image=image[:-12]+chunk+image[-12:]
        self.service.submit('rock','rock texture',42,'large');self.service.collect('large')
        review=self.service.inspect('large');self.assertFalse(review['channels'][0]['image_available'])
        self.assertGreater(review['channels'][0]['bytes'],artifact_io.IMAGE_LIMIT)
        with self.assertRaisesRegex(ValueError,'2 MiB'):self.service.image('large','base_color')

    def test_image_reader_detects_bytes_changed_after_verification(self):
        self.collect()
        with patch.object(artifact_io,'read_png',return_value=(fixtures.png((1,2,3)),{'width':2,'height':2})):
            with self.assertRaisesRegex(ValueError,'changed during display'):self.service.image('rock','base_color')

    def test_asset_bound_review_checks_sources_and_preserves_game_files(self):
        project,target=self.project();before=digest(target);calls=len(self.peer.calls)
        review=project.texture_inspect('bound');self.assertTrue(review['target_freshness_validated'])
        self.assertFalse(review['surface_verified']);self.assertFalse(review['editor_inspected'])
        self.assertEqual(project.texture_image('bound','base_color')['type'],'image')
        self.assertEqual(digest(target),before);self.assertEqual(len(self.peer.calls),calls)
        self.assertFalse((project.bindings/'bound.candidate.json').exists())
        target.write_bytes(b'changed game source')
        for method in (lambda:project.texture_inspect('bound'),lambda:project.texture_image('bound','base_color')):
            with self.assertRaisesRegex(ValueError,'Target changed'):method()
        self.assertFalse(self.service.inspect('bound')['target_freshness_validated'])
        self.assertEqual(self.service.image('bound','base_color')['type'],'image')

    def test_project_binding_mismatch_and_invalid_image_channels_are_rejected(self):
        project,_=self.project();receipt=project._receipt('bound');original=read_json(receipt)
        changed=copy.deepcopy(original);changed['request']['seed']=100;write_json(receipt,changed)
        with self.assertRaisesRegex(ValueError,'asset binding'):project.texture_inspect('bound')
        write_json(receipt,original)
        for channel in (None,[],True,'../base_color.png','unknown'):
            with self.subTest(channel=channel),self.assertRaises(ValueError):project.texture_image('bound',channel)

    def test_project_image_is_native_mcp_and_tools_require_configured_services(self):
        project,_=self.project();server=MCPServer(None,textures=self.service,project=project)
        server.handle({'jsonrpc':'2.0','id':0,'method':'initialize'})
        result=server.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
            'name':'project_texture_image','arguments':{'request_id':'bound','channel':'base_color'}}})
        self.assertFalse(result['result']['isError']);self.assertEqual(result['result']['content'][0]['type'],'image')
        self.assertEqual(len(tool_list()),8);self.assertEqual(len(tool_list(textures=True)),17)
        self.assertEqual(len(tool_list(True,True,True,True)),48)
        self.assertFalse(any(t['name'].startswith('texture_') for t in tool_list()))
        self.assertFalse(any(t['name']=='project_texture_image' for t in tool_list(project=True)))


if __name__=='__main__':unittest.main()
