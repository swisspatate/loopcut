# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict editor protocol doubles, not a real Unreal/GPU acceptance test."""
import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/addons_core'))
from cryptonyan_asset_studio import comparison_review as review
from cryptonyan_asset_studio import unreal_comparison as engine
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.unreal_review import ReviewError
from test_cryptonyan_unreal_materials import Editor as MaterialEditor, Object
from test_cryptonyan_materials import png

MESH = '/Game/Props/SM_Cat.SM_Cat'
MAT = '/Game/Materials/M_Base.M_Base'
SKIN = '/Game/Materials/MI_Neon.MI_Neon'
ANIM = '/Game/Animations/Run.Run'
SKELETON = '/Game/Rig/Skeleton.Skeleton'
MAP = '/Game/CryptoNyan/ReviewMaps/Compare'


def spec():
    return dict(schema='cryptonyan.comparison/1', id='CatSkins', target_level=MAP, anchor_m=[1, 2, 0], yaw_deg=30,
        camera=dict(position_m=[-4, 2, 2], target_m=[1, 2, 1], fov_deg=50, aspect_ratio=16/9, exposure_bias_ev=-1),
        lights=[dict(rotation_rpy_deg=[0, -40, -30], lux=1000), dict(rotation_rpy_deg=[0, -20, 140], lux=200)], pose=None,
        variants=[dict(id='Base', label='Original', mesh=MESH, mesh_class='StaticMesh', materials=[]),
                  dict(id='Neon', label='<Neon & cat>', mesh=MESH, mesh_class='StaticMesh', materials=[dict(slot=0, material=SKIN)])])


class Properties(Object):
    def __init__(self, **properties): super().__init__('', 'Properties', **properties)


class Component(Properties):
    def __init__(self, kind, editor):
        super().__init__(visible=True, hidden_in_game=False, cast_hidden_shadow=True, affect_indirect_lighting_while_hidden=True,
            relative_location=editor.Vector(0, 0, 0), relative_rotation=editor.Rotator(roll=0, pitch=0, yaw=0), relative_scale3d=editor.Vector(1, 1, 1))
        self.kind, self.editor, self.overrides, self.mesh = kind, editor, {}, None

    def set_editor_property(self, key, value):
        # Unreal properties use single precision for several camera fields.
        if key in ('aspect_ratio', 'field_of_view') and type(value) in (float, int): value = struct.unpack('f', struct.pack('f', value))[0]
        super().set_editor_property(key, value)

    def set_static_mesh(self, mesh): self.mesh = mesh; self.properties['static_mesh'] = mesh; return True
    def set_skeletal_mesh_asset(self, mesh): self.mesh = mesh; self.properties['skeletal_mesh_asset'] = mesh
    def get_num_materials(self): return len(self.mesh.properties['static_materials' if self.mesh.kind == 'StaticMesh' else 'materials'])
    def get_material(self, index):
        slots = self.mesh.properties['static_materials' if self.mesh.kind == 'StaticMesh' else 'materials']
        return self.overrides.get(index, slots[index].properties['material_interface'])
    def set_material(self, index, material): self.overrides[index] = material
    def set_collision_enabled(self, value): self.collision = value
    def get_collision_enabled(self): return self.collision
    def set_visibility(self, value, propagate):
        assert propagate is True
        self.properties['visible'] = value
        if self.editor.fail_visibility:
            self.editor.fail_visibility = False
            raise RuntimeError('interrupted selection')
    def set_hidden_in_game(self, value, propagate):
        assert propagate is True
        self.properties['hidden_in_game'] = value
    def set_mobility(self, value): self.properties['mobility'] = value
    def set_intensity(self, value): self.properties['intensity'] = value
    def set_light_color(self, value): self.properties['light_color'] = value
    def override_animation_data(self, animation, *, is_looping, is_playing, position, play_rate):
        assert is_looping is False and is_playing is False and play_rate == 0
        self.properties['animation_data'] = Properties(anim_to_play=animation, saved_playing=is_playing,
            saved_position=0 if self.editor.bad_pose else position)
    def set_update_animation_in_editor(self, value): assert value is True


class Actor(Object):
    def __init__(self, path, kind, location, rotation, editor):
        super().__init__(path, kind, tags=[], hidden=False)
        self.location, self.rotation, self.scale = location, rotation, editor.Vector(1, 1, 1)
        symbol = dict(StaticMeshActor='StaticMeshComponent', SkeletalMeshActor='SkeletalMeshComponent',
                      CameraActor='CameraComponent', DirectionalLight='DirectionalLightComponent')[kind]
        self.component = Component(symbol, editor)
    def set_actor_label(self, label): self.label = label
    def set_editor_property(self, key, value):
        class NameArray(list):
            def __eq__(self, other): return isinstance(other, NameArray) and super().__eq__(other)
        super().set_editor_property(key, NameArray(value) if key == 'tags' else value)
    def set_actor_scale3d(self, scale): self.scale = scale
    def get_actor_scale3d(self): return self.scale
    def get_actor_location(self): return self.location
    def get_actor_rotation(self): return self.rotation
    def is_hidden_ed(self): return False
    def get_component_by_class(self, kind):
        assert kind == self.component.kind
        return self.component


class Editor(MaterialEditor):
    UnrealEditorSubsystem = 'WorldEditor'
    EditorActorSubsystem = 'Actors'
    StaticMeshActor = 'StaticMeshActor'
    SkeletalMeshActor = 'SkeletalMeshActor'
    CameraActor = 'CameraActor'
    DirectionalLight = 'DirectionalLight'
    StaticMeshComponent = 'StaticMeshComponent'
    SkeletalMeshComponent = 'SkeletalMeshComponent'
    CameraComponent = 'CameraComponent'
    DirectionalLightComponent = 'DirectionalLightComponent'
    CollisionEnabled = NS(NO_COLLISION='None')
    ComponentMobility = NS(MOVABLE='Movable')
    AutoExposureMethod = NS(AEM_MANUAL='Manual')
    Name = str
    PostProcessSettings = Properties
    Rotator = NS
    Vector = staticmethod(lambda x, y, z: NS(x=x, y=y, z=z))
    LinearColor = staticmethod(lambda r, g, b, a: NS(r=r, g=g, b=b, a=a))

    def __init__(self, root):
        super().__init__(root)
        self.actors, self.removed, self.maps_dirty = [], [], []
        self.game_world, self.fail_spawn_at, self.on_spawn, self.fail_visibility, self.bad_pose = None, None, None, False, False
        self.world = Object(MAP+'.Compare', 'World')
        self.EditorLoadingAndSavingUtils.get_dirty_map_packages = lambda: self.maps_dirty
        self.AnimationLibrary = NS(get_sequence_length=lambda a: a.properties['duration'])
    def get_editor_subsystem(self, kind):
        if kind == self.UnrealEditorSubsystem:
            return NS(get_editor_world=lambda: self.world, get_game_world=lambda: self.game_world)
        assert kind == self.EditorActorSubsystem
        return NS(get_all_level_actors=lambda: [Object('WorldSettings', 'WorldSettings'), *self.actors],
                  spawn_actor_from_class=self.spawn, destroy_actor=self.destroy)
    def spawn(self, kind, location, rotation):
        if len(self.actors) == self.fail_spawn_at: return None
        actor = Actor(MAP+'.Compare:PersistentLevel.Actor_'+str(len(self.actors)), kind, location, rotation, self)
        self.actors.append(actor)
        if self.on_spawn: self.on_spawn(actor)
        return actor
    def destroy(self, actor): self.actors.remove(actor); self.removed.append(actor.path); return True


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        self.game = self.root/'game'; self.game.mkdir(); (self.game/'Cat.uproject').write_text('{"FileVersion":3}')
        self.work = self.root/'work'; self.work.mkdir(); self.u = Editor(self.game)
        mat = self.u.add(MAT, 'Material', tangent_space_normal=True, use_material_attributes=False, texture={}, scalar={}, vector={})
        self.u.add(SKIN, 'MaterialInstanceConstant', parent=mat, texture={}, scalar={'Glow': 2}, vector={})
        self.mesh = self.u.add(MESH, 'StaticMesh', static_materials=[Object('', 'Slot', material_slot_name='Body', material_interface=mat)])
        level = self.game/('Content/'+MAP[6:]+'.umap'); level.parent.mkdir(parents=True); level.write_bytes(b'opaque map package')
        self.plan_path = self.work/'plan.json'; self.save_plan()
    def save_plan(self, value=None):
        self.plan = review.make_plan(value or spec(), self.game); write_json(self.plan_path, self.plan)
    def stage(self):
        result = engine.create(self.plan_path, self.work/'stage', apply=True, unreal_module=self.u)
        self.assertEqual(result['status'], 'created_review_required', result)
        return self.work/'stage/session.json'
    def select(self, session, variant, name='selection.json', apply=True):
        return engine.select(self.plan_path, session, variant, self.work/name, apply=apply, unreal_module=self.u)
    def test_deterministic_plan_and_independent_specification(self):
        value = spec(); before = copy.deepcopy(value); parsed = review.specification(value)
        parsed['variants'][0]['label'] = 'Other'; self.assertEqual(value, before)
        self.assertEqual(self.plan, review.make_plan(spec(), self.game))
        self.assertEqual(self.plan['sources'][MESH][0]['sha256'], digest(self.game/'Content/Props/SM_Cat.uasset'))
    def test_invalid_contracts_fail_before_project_access(self):
        for change in ({'schema': 'bad'}, {'automatic_adoption': True}, {'anchor_m': [True, 0, 0]}, {'variants': []},
                       {'lights': []}, {'target_level': '/Game/Production/Main'}, {'yaw_deg': float('nan')}):
            with self.subTest(change=change), self.assertRaises(ValueError): review.make_plan({**spec(), **change}, self.root/'missing')
    def test_reserved_duplicate_ids_slots_and_invalid_camera(self):
        for issue in ('id', 'reserved', 'slot', 'camera', 'mixed', 'static_pose'):
            value = spec()
            if issue == 'id': value['variants'][1]['id'] = 'base'
            elif issue == 'reserved': value['variants'][1]['id'] = 'Camera'
            elif issue == 'slot': value['variants'][1]['materials'] *= 2
            elif issue == 'camera': value['camera']['position_m'] = value['camera']['target_m']
            elif issue == 'mixed': value['variants'][1]['mesh_class'] = 'SkeletalMesh'
            else: value['pose'] = dict(animation=ANIM, time_s=0)
            with self.subTest(issue=issue), self.assertRaises(ValueError): review.specification(value)
    def test_saved_map_source_sidecar_and_plan_drift_rejected(self):
        for relative in ('Content/Props/SM_Cat.uasset', 'Content/Props/SM_Cat.ubulk', 'Content/CryptoNyan/ReviewMaps/Compare.umap'):
            file = self.game/relative; before = file.read_bytes() if file.exists() else None
            file.write_bytes(b'changed')
            with self.subTest(relative=relative), self.assertRaises(ValueError): review.load_plan(self.plan_path)
            if before is None: file.unlink()
            else: file.write_bytes(before)
        plan = read_json_copy(self.plan_path); plan['specification']['camera']['fov_deg'] += 5; write_json(self.plan_path, plan)
        with self.assertRaises(ValueError): review.load_plan(self.plan_path)
    def test_dry_run_does_not_require_unreal_or_mutate_anything(self):
        result = engine.create(self.plan_path, self.work/'dry')
        self.assertEqual(result['status'], 'planned'); self.assertFalse(self.u.actors)
        self.assertFalse((self.work/'dry/session.json').exists())
        with self.assertRaises(FileExistsError): engine.create(self.plan_path, self.work/'dry')
    def test_real_protocol_switches_shared_stage_without_changing_assets(self):
        originals = {p: digest(p) for p in self.game.rglob('*') if p.is_file()}
        session = self.stage(); a, b, camera, key, fill = self.u.actors
        self.assertEqual((a.location.x, a.location.y, a.location.z), (100, 200, 0))
        self.assertEqual(vars(a.location), vars(b.location))
        self.assertEqual(camera.location.x, -400); self.assertEqual(key.component.properties['intensity'], 1000)
        self.assertEqual(fill.component.properties['intensity'], 200)
        self.assertIs(a.component.get_material(0), self.u.objects[MAT]); self.assertIs(b.component.get_material(0), self.u.objects[SKIN])
        self.assertIs(self.mesh.properties['static_materials'][0].properties['material_interface'], self.u.objects[MAT])
        self.assertEqual(self.select(session, 'Neon')['status'], 'selected_review_required')
        self.assertFalse(a.component.properties['visible']); self.assertTrue(b.component.properties['visible'])
        self.assertEqual(self.select(session, 'Base', 'dry.json', apply=False)['status'], 'planned')
        self.assertTrue(b.component.properties['visible'])
        self.assertEqual({p: digest(p) for p in originals}, originals)
        self.assertEqual(self.u.saved, []); self.assertEqual(self.u.imports, []); self.assertEqual(self.u.created, [])
    def test_invalid_runtime_map_content_or_play_blocks_all_spawns(self):
        for issue in ('version', 'map', 'dirty', 'dirty_map', 'occupied', 'PIE'):
            with self.subTest(issue=issue):
                u = Editor(self.game); u.objects = self.u.objects
                if issue == 'version': u.version = '5.7.0'
                elif issue == 'map': u.world.path = '/Game/Production.Main'
                elif issue == 'dirty': u.dirty = [MESH.split('.')[0]]
                elif issue == 'dirty_map': u.maps_dirty = [Object(MAP, 'Package')]
                elif issue == 'occupied': u.actors.append(Object('Existing', 'StaticMeshActor'))
                else: u.game_world = Object('PIE', 'World')
                count = len(u.actors)
                result = engine.create(self.plan_path, self.work/issue, apply=True, unreal_module=u)
                self.assertEqual(result['status'], 'failed'); self.assertEqual(len(u.actors), count)
    def test_bad_slot_or_redirector_rejected_before_spawning(self):
        value = spec(); value['variants'][1]['materials'][0]['slot'] = 4; self.save_plan(value)
        result = engine.create(self.plan_path, self.work/'badslot', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'material_slot_out_of_range'); self.assertEqual(self.u.actors, [])
        self.save_plan(); self.mesh.kind = 'ObjectRedirector'
        result = engine.create(self.plan_path, self.work/'redirect', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'missing_source_wrong_class_or_redirector'); self.assertEqual(self.u.actors, [])
    def test_partial_spawn_rolls_back_only_owned_actors(self):
        self.u.fail_spawn_at = 3
        result = engine.create(self.plan_path, self.work/'partial', apply=True, unreal_module=self.u)
        self.assertEqual(result['status'], 'failed'); self.assertEqual(self.u.actors, [])
        self.assertEqual(len(result['removed_actors']), 3); self.assertEqual(result['remaining_actors'], [])
    def test_camera_transform_readback_failure_rolls_back(self):
        self.u.on_spawn = lambda a: setattr(a.location, 'x', a.location.x+10) if a.kind == 'CameraActor' else None
        result = engine.create(self.plan_path, self.work/'badcamera', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'comparison_transform_readback_failed'); self.assertEqual(self.u.actors, [])
    def test_changed_live_material_blocks_selection_without_visibility_change(self):
        session = self.stage(); self.u.objects[SKIN].properties['scalar']['Glow'] = 3
        result = self.select(session, 'Neon'); self.assertEqual(result['error'], 'comparison_live_sources_changed')
        self.assertTrue(self.u.actors[0].component.properties['visible'])
    def test_camera_light_transform_and_material_drift_are_detected(self):
        session = self.stage()
        for actor, field, changed in ((self.u.actors[2].component, 'field_of_view', 80),
                                      (self.u.actors[3].component, 'intensity', 2000)):
            old = actor.properties[field]; actor.properties[field] = changed
            with self.assertRaises(ReviewError): engine.checked(self.plan_path, session, self.u)
            actor.properties[field] = old
        self.u.actors[1].component.overrides[0] = self.u.objects[MAT]
        with self.assertRaises(ReviewError): engine.checked(self.plan_path, session, self.u)
        self.u.actors[1].component.overrides[0] = self.u.objects[SKIN]
        self.u.actors[2].component.properties['relative_location'].x = 10
        with self.assertRaises(ReviewError): engine.checked(self.plan_path, session, self.u)
    def test_extra_actor_and_visibility_tampering_refuse_selection(self):
        session = self.stage(); self.u.actors.append(Object('Unexpected', 'Actor'))
        result = self.select(session, 'Neon'); self.assertEqual(result['error'], 'comparison_actor_set_changed')
        self.u.actors.pop(); self.u.actors[1].component.properties.update(visible=True, hidden_in_game=False)
        result = self.select(session, 'Neon', 'again.json'); self.assertEqual(result['error'], 'comparison_requires_one_visible_variant')
    def test_interrupted_switch_restores_previous_variant(self):
        session = self.stage(); self.u.fail_visibility = True
        result = self.select(session, 'Neon')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(engine.checked(self.plan_path, session, self.u)[3], 'Base')
    def test_unknown_variant_and_repeated_receipt_do_not_overwrite(self):
        session = self.stage(); self.assertEqual(self.select(session, 'Unknown')['status'], 'failed')
        with self.assertRaises(FileExistsError): self.select(session, 'Base')
        with self.assertRaises(ReviewError): engine.create(self.plan_path, self.game/'forbidden')
    def test_manual_captures_and_offline_comparison_preserve_provenance(self):
        session = self.stage(); image = self.root/'screen.png'; image.write_bytes(png(width=16, height=9))
        base = self.work/'capture-base'; neon = self.work/'capture-neon'
        first = engine.collect(self.plan_path, session, image, base, unreal_module=self.u)
        self.assertEqual(first['provenance'], 'user_supplied_png_not_renderer_verified'); self.assertFalse(first['gpu_measured'])
        self.select(session, 'Neon'); engine.collect(self.plan_path, session, image, neon, unreal_module=self.u)
        gallery = self.work/'gallery'; result = review.compare(self.plan_path, [base, neon], gallery)
        self.assertEqual([c['variant'] for c in result['captures']], ['Base', 'Neon'])
        page = (gallery/'comparison.html').read_text(); self.assertIn('&lt;Neon &amp; cat&gt;', page)
        self.assertNotIn('<script', page); self.assertFalse(result['visual_quality_validated'])
        self.assertEqual(digest(gallery/'Base.png'), digest(image))
        image.unlink(); self.assertEqual(review.load_capture(base, self.plan), first)
    def test_capture_hash_or_session_drift_is_rejected(self):
        session = self.stage(); image = self.root/'screen.png'; image.write_bytes(png(width=16, height=9))
        base = self.work/'base'; neon = self.work/'neon'
        engine.collect(self.plan_path, session, image, base, unreal_module=self.u)
        self.select(session, 'Neon'); engine.collect(self.plan_path, session, image, neon, unreal_module=self.u)
        value = read_json_copy(neon/'capture.json'); value['conditions_identity'] = '0'*64; write_json(neon/'capture.json', value)
        with self.assertRaises(ValueError): review.compare(self.plan_path, [base, neon], self.work/'gallery')
        (base/'image.png').write_bytes(b'bad')
        with self.assertRaises(ValueError): review.load_capture(base, self.plan)
    def test_failed_stage_cannot_be_used_as_a_session(self):
        session = self.stage(); value = read_json_copy(session.parent/'result.json'); value['status'] = 'failed'; write_json(session.parent/'result.json', value)
        self.assertEqual(self.select(session, 'Neon')['error'], 'comparison_stage_incomplete')
    def skeletal(self, pose=True):
        skeleton = self.u.add(SKELETON, 'Skeleton')
        self.mesh.kind = 'SkeletalMesh'
        if 'static_materials' in self.mesh.properties: self.mesh.properties['materials'] = self.mesh.properties.pop('static_materials')
        self.mesh.properties['skeleton'] = skeleton
        self.u.add(ANIM, 'AnimSequence', skeleton=skeleton, duration=1)
        value = spec()
        for item in value['variants']: item['mesh_class'] = 'SkeletalMesh'
        value['pose'] = dict(animation=ANIM, time_s=.25) if pose else None
        self.save_plan(value)
    def test_skeletal_meshes_share_a_paused_pose_without_cloth_or_notifies(self):
        self.skeletal(); session = self.stage()
        for actor in self.u.actors[:2]:
            self.assertEqual(actor.component.properties['animation_data'].properties['saved_position'], .25)
            self.assertTrue(actor.component.properties['disable_cloth_simulation'])
            self.assertTrue(actor.component.properties['suppress_notify_event_dispatch'])
        self.assertEqual(self.select(session, 'Neon')['status'], 'selected_review_required')
    def test_reference_pose_and_bad_animation_position(self):
        self.skeletal(pose=False); self.stage()
        self.assertIsNone(self.u.actors[0].component.properties['animation_data'].properties['anim_to_play'])
        self.u.actors.clear(); self.skeletal(); self.u.bad_pose = True
        result = engine.create(self.plan_path, self.work/'wrong-pose', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'comparison_pose_readback_failed'); self.assertEqual(self.u.actors, [])
    def test_wrong_skeleton_or_time_blocks_before_spawning(self):
        self.skeletal(); self.u.objects[ANIM].properties['skeleton'] = self.u.add('/Game/Other.Other', 'Skeleton')
        result = engine.create(self.plan_path, self.work/'wrong-skeleton', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'animation_mesh_skeleton_mismatch'); self.assertEqual(self.u.actors, [])
        self.u.objects[ANIM].properties['skeleton'] = self.u.objects[SKELETON]
        self.u.objects[ANIM].properties['duration'] = .1
        result = engine.create(self.plan_path, self.work/'wrong-time', apply=True, unreal_module=self.u)
        self.assertEqual(result['error'], 'pose_time_out_of_range'); self.assertEqual(self.u.actors, [])
    def test_cli_prepares_a_real_plan_without_editor(self):
        request = self.work/'recipe.json'; write_json(request, spec())
        command = [sys.executable, '-m', 'cryptonyan_asset_studio.comparison_review', 'plan', str(request),
            '--project', str(self.game), '--output', str(self.work/'cli-plan.json')]
        result = subprocess.run(command, env={**os.environ, 'PYTHONPATH': str(ROOT/'scripts/addons_core')}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(review.load_plan(self.work/'cli-plan.json'), self.plan)


def read_json_copy(path): return json.loads(Path(path).read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
