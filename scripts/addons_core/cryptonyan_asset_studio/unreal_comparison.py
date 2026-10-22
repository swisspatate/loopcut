# SPDX-License-Identifier: GPL-3.0-or-later
"""Common in-editor comparison stage. No asset edits, map saves or renderer claims."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from .animation_doctor import exact, number, read_json
from .comparison_review import camera_pose, load_plan
from .game_project import GameProject
from .image_workshop import identity
from .materials import read_png
from .storage import write_json
from .unreal_director import clean_content, require
from .unreal_material_variants import _runtime, _outside, _path, _kind, _object_path, _bounded, inspect_native
from .unreal_review import ReviewError

PP = dict(override_auto_exposure_method=True, override_auto_exposure_bias=True,
    override_auto_exposure_apply_physical_camera_exposure=True, auto_exposure_apply_physical_camera_exposure=False)


def runtime(plan, u):
    version, project = _runtime(u)
    require(project._project_identity() == plan['project_identity'], 'wrong_active_project')
    world_editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    require(world_editor.get_game_world() is None, 'stop_play_in_editor_before_comparison')
    require(_path(world_editor.get_editor_world()) == _object_path(plan['specification']['target_level']), 'wrong_current_review_map')
    clean_content(u)
    return version, u.get_editor_subsystem(u.EditorActorSubsystem)


def inspections(plan, u):
    result = {}
    for path, kind in plan['source_classes'].items():
        obj = u.load_asset(path)
        permitted = ('Material', 'MaterialInstanceConstant') if kind == 'MaterialInterface' else (kind,)
        require(_path(obj) == path and _kind(obj) in permitted, 'missing_source_wrong_class_or_redirector')
        result[path] = inspect_native(path, u)
    require(len(json.dumps(result, allow_nan=False)) <= 8*1024*1024, 'comparison_inspection_budget_exceeded')
    for item in plan['specification']['variants']:
        slots = result[item['mesh']]['slots']
        require(1 <= len(slots) <= 32 and all(s['material'] is not None for s in slots), 'require_explicit_material_slots')
        require(all(m['slot'] < len(slots) for m in item['materials']), 'material_slot_out_of_range')
    pose = plan['specification']['pose']
    if pose:
        animation = u.load_asset(pose['animation'])
        skeleton = _path(animation.get_editor_property('skeleton'))
        require(skeleton is not None and all(result[v['mesh']]['skeleton']['path'] == skeleton
            for v in plan['specification']['variants']), 'animation_mesh_skeleton_mismatch')
        require(pose['time_s'] <= u.AnimationLibrary.get_sequence_length(animation), 'pose_time_out_of_range')
    return result


def xyz(value):
    return [number(getattr(value, axis), -1e8, 1e8) for axis in ('x', 'y', 'z')]


def rpy(value):
    return [number(getattr(value, axis), -360000, 360000) for axis in ('roll', 'pitch', 'yaw')]


def rot(u, value):
    return u.Rotator(roll=value[0], pitch=value[1], yaw=value[2])


def prop(obj, key, value):
    obj.set_editor_property(key, value)
    actual = obj.get_editor_property(key)
    require(same(actual, value), 'comparison_property_readback_failed_'+key)


def same(actual, value):
    return abs(actual-value) <= 1e-5*max(1, abs(value)) if type(value) is float else actual == value


def component(actor, row, u):
    symbol = dict(variant_static='StaticMeshComponent', variant_skeletal='SkeletalMeshComponent',
                  camera='CameraComponent', light='DirectionalLightComponent')[row['kind']]
    return require(actor.get_component_by_class(getattr(u, symbol)), 'missing_comparison_component')


def conditions(actor, row, u):
    c = component(actor, row, u)
    result = dict(path=_path(actor), kind=_kind(actor), location_cm=xyz(actor.get_actor_location()),
        rotation_rpy_deg=rpy(actor.get_actor_rotation()), scale=xyz(actor.get_actor_scale3d()),
        tags=[str(t) for t in actor.get_editor_property('tags')], hidden_editor=actor.is_hidden_ed(),
        hidden_actor=actor.get_editor_property('hidden'), relative_location_cm=xyz(c.get_editor_property('relative_location')),
        relative_rotation_rpy_deg=rpy(c.get_editor_property('relative_rotation')), relative_scale=xyz(c.get_editor_property('relative_scale3d')))
    if row['kind'].startswith('variant_'):
        field = 'static_mesh' if row['kind'] == 'variant_static' else 'skeletal_mesh_asset'
        result.update(mesh=_path(c.get_editor_property(field)), materials=[_path(c.get_material(i)) for i in range(c.get_num_materials())],
            collision=str(c.get_collision_enabled()), cast_hidden_shadow=c.get_editor_property('cast_hidden_shadow'),
            hidden_indirect=c.get_editor_property('affect_indirect_lighting_while_hidden'))
        if row['kind'] == 'variant_skeletal':
            data = c.get_editor_property('animation_data')
            result['pose'] = dict(animation=_path(data.get_editor_property('anim_to_play')),
                playing=data.get_editor_property('saved_playing'), position=data.get_editor_property('saved_position'),
                cloth=c.get_editor_property('disable_cloth_simulation'), suppress_notifies=c.get_editor_property('suppress_notify_event_dispatch'))
    elif row['kind'] == 'camera':
        settings = c.get_editor_property('post_process_settings')
        result.update(fov=c.get_editor_property('field_of_view'), aspect=c.get_editor_property('aspect_ratio'),
            constrain=c.get_editor_property('constrain_aspect_ratio'), blend=c.get_editor_property('post_process_blend_weight'),
            exposure={k: str(settings.get_editor_property(k)) for k in (*PP, 'auto_exposure_method', 'auto_exposure_bias')})
    else:
        color = c.get_editor_property('light_color')
        result.update(lux=c.get_editor_property('intensity'), color=[getattr(color, a) for a in ('r', 'g', 'b', 'a')],
                      temperature=c.get_editor_property('use_temperature'), mobility=str(c.get_editor_property('mobility')))
    return result


def create(plan_path, output, *, apply=False, unreal_module=None):
    if type(apply) is not bool: raise ValueError('apply must be boolean')
    plan = load_plan(plan_path); project = GameProject(plan['project_root'])
    output = _outside(output, project).resolve(); output.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema='cryptonyan.comparison-stage-result/1', plan_identity=plan['identity'], status='planned',
        owned_actors=[], removed_actors=[], level_saved=False, engine_validated=False, gpu_measured=False)
    spawned, u, editor = [], unreal_module, None
    try:
        if not apply: return receipt
        if u is None: import unreal as u
        version, editor = runtime(plan, u)
        require(all(_kind(a) == 'WorldSettings' for a in editor.get_all_level_actors()), 'review_map_not_empty')
        original_actor_paths = {_path(a) for a in editor.get_all_level_actors()}
        require(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'save_maps_before_comparison')
        native = inspections(plan, u)
        require(load_plan(plan_path) == plan, 'comparison_sources_changed_before_creation')
        spec = plan['specification']; session = dict(schema='cryptonyan.comparison-session/1', plan_identity=plan['identity'],
            stage_id='S'+uuid.uuid4().hex, engine_version=version, inspections=native, actors=[])

        def spawn(role, kind, cls, position, rotation):
            actor = require(editor.spawn_actor_from_class(getattr(u, cls), u.Vector(*[100*v for v in position]), rot(u, rotation)), 'comparison_spawn_failed')
            require(_path(actor) not in original_actor_paths, 'comparison_spawn_returned_existing_actor')
            spawned.append(actor); receipt['owned_actors'].append(_path(actor))
            require(_kind(actor) == cls, 'comparison_spawn_class_mismatch')
            actor.set_actor_label('CN_Compare_'+role)
            actor.set_editor_property('tags', [u.Name(session['stage_id']), u.Name(role)])
            require([str(t) for t in actor.get_editor_property('tags')] == [session['stage_id'], role], 'comparison_actor_tags_readback_failed')
            actor.set_actor_scale3d(u.Vector(1, 1, 1))
            require(all(abs(a-b*100) <= .01 for a,b in zip(xyz(actor.get_actor_location()), position))
                and all(abs((a-b+180)%360-180) <= .01 for a,b in zip(rpy(actor.get_actor_rotation()), rotation))
                and xyz(actor.get_actor_scale3d()) == [1, 1, 1], 'comparison_transform_readback_failed')
            row = dict(role=role, kind=kind, path=_path(actor)); session['actors'].append(row)
            return actor, component(actor, row, u)

        for item in spec['variants']:
            skeletal = item['mesh_class'] == 'SkeletalMesh'
            actor, c = spawn(item['id'], 'variant_skeletal' if skeletal else 'variant_static',
                'SkeletalMeshActor' if skeletal else 'StaticMeshActor', spec['anchor_m'], [0, 0, spec['yaw_deg']])
            mesh = u.load_asset(item['mesh'])
            if skeletal:
                c.set_skeletal_mesh_asset(mesh)
                prop(c, 'disable_cloth_simulation', True); prop(c, 'suppress_notify_event_dispatch', True)
                pose = spec['pose']; c.override_animation_data(u.load_asset(pose['animation']) if pose else None,
                    is_looping=False, is_playing=False, position=pose['time_s'] if pose else 0, play_rate=0)
                c.set_update_animation_in_editor(True)
                data = c.get_editor_property('animation_data')
                require(_path(data.get_editor_property('anim_to_play')) == (pose['animation'] if pose else None)
                    and data.get_editor_property('saved_playing') is False
                    and abs(data.get_editor_property('saved_position')-(pose['time_s'] if pose else 0)) <= .0001,
                    'comparison_pose_readback_failed')
            else: require(c.set_static_mesh(mesh), 'comparison_mesh_assignment_failed')
            expected = [s['material'] for s in native[item['mesh']]['slots']]
            for override in item['materials']:
                c.set_material(override['slot'], u.load_asset(override['material'])); expected[override['slot']] = override['material']
            require([_path(c.get_material(i)) for i in range(c.get_num_materials())] == expected, 'comparison_material_assignment_failed')
            require(_path(c.get_editor_property('skeletal_mesh_asset' if skeletal else 'static_mesh')) == item['mesh'], 'comparison_mesh_readback_failed')
            c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            require(c.get_collision_enabled() == u.CollisionEnabled.NO_COLLISION, 'comparison_collision_readback_failed')
            prop(c, 'cast_hidden_shadow', False); prop(c, 'affect_indirect_lighting_while_hidden', False)
            visible = item is spec['variants'][0]
            c.set_visibility(visible, True); c.set_hidden_in_game(not visible, True)
        camera = spec['camera']; pose = camera_pose(camera)
        actor, c = spawn('Camera', 'camera', 'CameraActor', pose['position_m'], pose['rotation_rpy_deg'])
        for key, value in dict(field_of_view=camera['fov_deg'], aspect_ratio=camera['aspect_ratio'],
                               constrain_aspect_ratio=True, post_process_blend_weight=1.0).items(): prop(c, key, value)
        settings = u.PostProcessSettings()
        for key, value in {**PP, 'auto_exposure_method': u.AutoExposureMethod.AEM_MANUAL, 'auto_exposure_bias': camera['exposure_bias_ev']}.items(): prop(settings, key, value)
        c.set_editor_property('post_process_settings', settings)
        readback = c.get_editor_property('post_process_settings')
        require(all(same(readback.get_editor_property(k), settings.get_editor_property(k))
            for k in (*PP, 'auto_exposure_method', 'auto_exposure_bias')), 'comparison_exposure_readback_failed')
        for index, light in enumerate(spec['lights']):
            actor, c = spawn('Light'+str(index), 'light', 'DirectionalLight', spec['anchor_m'], light['rotation_rpy_deg'])
            c.set_mobility(u.ComponentMobility.MOVABLE); c.set_intensity(light['lux'])
            require(c.get_editor_property('mobility') == u.ComponentMobility.MOVABLE, 'comparison_light_mobility_failed')
            require(abs(c.get_editor_property('intensity')-light['lux']) <= .01, 'comparison_light_readback_failed')
            c.set_light_color(u.LinearColor(1, 1, 1, 1)); prop(c, 'use_temperature', False)
        for actor, row in zip(spawned, session['actors']):
            row['conditions'] = conditions(actor, row, u)
            require(not row['conditions']['hidden_editor'] and not row['conditions']['hidden_actor'], 'comparison_actor_hidden')
        require(load_plan(plan_path) == plan and inspections(plan, u) == native, 'comparison_sources_changed_during_creation')
        session['identity'] = identity(session)
        write_json(output/'session.json', session)
        # Resolve and verify the entire stage through the same reader used for switching.
        require(checked(plan_path, output/'session.json', u, _creating=True)[3] == spec['variants'][0]['id'], 'comparison_baseline_not_visible')
        receipt.update(status='created_review_required', stage_id=session['stage_id'], session_identity=session['identity'])
        return receipt
    except Exception as error:
        receipt.update(status='failed', error=str(error) if isinstance(error, ReviewError) else type(error).__name__)
        if editor:
            for actor in reversed(spawned):
                try:
                    if editor.destroy_actor(actor): receipt['removed_actors'].append(_path(actor))
                except Exception: pass
        receipt['remaining_actors'] = [p for p in receipt['owned_actors'] if p not in receipt['removed_actors']]
        return receipt
    finally: write_json(output/'result.json', receipt)


def checked(plan_path, session_path, u, *, _creating=False):
    plan = load_plan(plan_path); session = read_json(session_path)
    exact(session, ('schema', 'plan_identity', 'stage_id', 'engine_version', 'inspections', 'actors', 'identity'))
    require(session['schema'] == 'cryptonyan.comparison-session/1' and session['plan_identity'] == plan['identity']
        and identity({k:v for k,v in session.items() if k != 'identity'}) == session['identity'], 'comparison_session_changed')
    if not _creating:
        receipt = read_json(Path(session_path).parent/'result.json')
        require(receipt.get('status') == 'created_review_required' and receipt.get('session_identity') == session['identity'], 'comparison_stage_incomplete')
    version, editor = runtime(plan, u)
    require(version == session['engine_version'] and inspections(plan, u) == session['inspections'], 'comparison_live_sources_changed')
    actors = {_path(a): a for a in editor.get_all_level_actors() if _kind(a) != 'WorldSettings'}
    require(set(actors) == {r['path'] for r in session['actors']}, 'comparison_actor_set_changed')
    variants, visible = {}, []
    for row in session['actors']:
        actor = actors[row['path']]
        require([str(t) for t in actor.get_editor_property('tags')] == [session['stage_id'], row['role']], 'comparison_actor_ownership_changed')
        require(conditions(actor, row, u) == row['conditions'], 'comparison_conditions_changed')
        if row['kind'].startswith('variant_'):
            c = component(actor, row, u); variants[row['role']] = c
            on = bool(c.get_editor_property('visible')); hidden = bool(c.get_editor_property('hidden_in_game'))
            require(on != hidden, 'comparison_visibility_inconsistent')
            if on: visible.append(row['role'])
    require(len(visible) == 1, 'comparison_requires_one_visible_variant')
    return plan, session, variants, visible[0]


def select(plan_path, session_path, variant, report_path, *, apply=False, unreal_module=None):
    if type(apply) is not bool: raise ValueError('apply must be boolean')
    plan = load_plan(plan_path); report = _outside(report_path, GameProject(plan['project_root']), Path(session_path).parent)
    receipt = dict(schema='cryptonyan.comparison-selection/1', plan_identity=plan['identity'], status='planned', variant=variant)
    with report.open('x', encoding='utf-8') as stream:
        previous, components = None, {}
        try:
            if unreal_module is None: import unreal as unreal_module
            _, session, components, previous = checked(plan_path, session_path, unreal_module)
            require(variant in components, 'unknown_comparison_variant')
            if not apply: return receipt
            for c in components.values(): c.set_visibility(False, True); c.set_hidden_in_game(True, True)
            components[variant].set_visibility(True, True); components[variant].set_hidden_in_game(False, True)
            _, _, _, active = checked(plan_path, session_path, unreal_module)
            require(active == variant, 'comparison_selection_readback_failed')
            receipt.update(status='selected_review_required', previous=previous, stage_id=session['stage_id'])
            return receipt
        except Exception as error:
            if apply and previous:
                try:
                    for key, c in components.items(): c.set_visibility(key == previous, True); c.set_hidden_in_game(key != previous, True)
                except Exception: pass
            receipt.update(status='failed', error=str(error) if isinstance(error, ReviewError) else type(error).__name__)
            return receipt
        finally: stream.write(json.dumps(receipt, indent=2, allow_nan=False)+'\n')


def collect(plan_path, session_path, image, output, *, unreal_module=None):
    if unreal_module is None: import unreal as unreal_module
    plan, session, _, active = checked(plan_path, session_path, unreal_module)
    output = _outside(output, GameProject(plan['project_root']), Path(session_path).parent).resolve()
    data, dimensions = read_png(image)
    require(abs(dimensions['width']-dimensions['height']*plan['specification']['camera']['aspect_ratio']) <= 1,
        'capture_aspect_ratio_differs_from_camera')
    # Pixels come from the supplied PNG, never from a claimed screenshot/GPU benchmark.
    output.mkdir(parents=True, exist_ok=False); (output/'image.png').write_bytes(data)
    receipt = dict(schema='cryptonyan.comparison-capture/1', plan_identity=plan['identity'], stage_id=session['stage_id'],
        conditions_identity=session['identity'], variant=active,
        image=dict(file='image.png', sha256=hashlib.sha256(data).hexdigest(), **dimensions),
        provenance='user_supplied_png_not_renderer_verified', gpu_measured=False)
    checked(plan_path, session_path, unreal_module)
    write_json(output/'capture.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--output', required=True, type=Path); stage.add_argument('--apply', action='store_true')
    activate = sub.add_parser('select'); activate.add_argument('session', type=Path); activate.add_argument('variant')
    activate.add_argument('--report', required=True, type=Path); activate.add_argument('--apply', action='store_true')
    capture = sub.add_parser('collect'); capture.add_argument('session', type=Path); capture.add_argument('image', type=Path)
    capture.add_argument('--output', required=True, type=Path)
    for command in (stage, activate, capture): command.add_argument('plan', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'stage': result = create(args.plan, args.output, apply=args.apply)
    elif args.command == 'select': result = select(args.plan, args.session, args.variant, args.report, apply=args.apply)
    else: result = collect(args.plan, args.session, args.image, args.output)
    print(json.dumps(result, indent=2)); return 1 if result.get('status') == 'failed' else 0


if __name__ == '__main__': raise SystemExit(main())
