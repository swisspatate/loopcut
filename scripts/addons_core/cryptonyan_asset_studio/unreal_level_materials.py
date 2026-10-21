# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit editor material A/B with durable intent journal and conditional restoration.

Only component override arrays are changed. No actor spawning, asset writes, saves,
selection changes, render claims, remote control or automatic recovery after a crash.
"""
import argparse
import json
from pathlib import Path
import re

from .animation_doctor import read_json
from .creative_director import snapshots, write_new
from .game_project import GameProject
from .level_materials import component_state, load_plan, map_file, validate_capture
from .storage import safe_path, write_json
from .unreal_director import clean_content, require, validate_sources
from .unreal_material_variants import _bounded, _hash, _kind, _object_path, _outside, _path, _runtime
from .unreal_review import ReviewError


def runtime(u, expected=None):
    _, project = _runtime(u)
    require(not u.get_editor_subsystem(u.LevelEditorSubsystem).is_in_play_in_editor(), 'stop_PIE_before_material_review')
    clean_content(u)
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    path = _path(world)
    require(path is not None and _object_path(path) == path, 'require_saved_Game_editor_world')
    map_file(project, path)
    if expected is not None:
        require(project._project_identity() == expected['project_identity'] and path == expected['world'], 'wrong_editor_project_or_map')
    return project, path


def read_component(component, world, u):
    kind = _kind(component)
    require(kind in ('StaticMeshComponent', 'SkeletalMeshComponent'), 'unsupported_mesh_component')
    actor = component.get_owner()
    require(not actor.is_package_external(), 'external_actor_package_requires_separate_adapter')
    require(_path(actor.get_level()) == world+':PersistentLevel', 'only_loaded_persistent_level_components')
    creation = component.get_editor_property('creation_method')
    creation = next((name for name, member in (('native', u.ComponentCreationMethod.NATIVE),
                    ('instance', u.ComponentCreationMethod.INSTANCE)) if creation == member), 'unsupported')
    guid = actor.get_editor_property('actor_guid').to_string().replace('-', '').lower()
    require(bool(re.fullmatch('[0-9a-f]{32}', guid)), 'invalid_actor_guid')
    mesh = component.get_editor_property('static_mesh') if kind == 'StaticMeshComponent' else component.get_skinned_asset()
    require(_kind(mesh) == ('StaticMesh' if kind == 'StaticMeshComponent' else 'SkeletalMesh'), 'missing_or_unsupported_mesh')
    slots = _bounded(mesh.get_editor_property('static_materials' if kind == 'StaticMeshComponent' else 'materials'), 32, 'too_many_material_slots')
    require(1 <= len(slots) <= 32 and component.get_num_materials() == len(slots), 'component_slot_layout_mismatch')
    defaults = [s.get_editor_property('material_interface') for s in slots]
    overrides = _bounded(component.get_editor_property('override_materials'), 32, 'too_many_material_overrides')
    effective = [component.get_material(i) for i in range(len(slots))]
    assets = { _path(mesh): _kind(mesh) }
    for material in defaults+overrides+effective:
        if material is not None:
            require(_kind(material) in ('Material', 'MaterialInstanceConstant'), 'dynamic_or_unsupported_material')
            path = _object_path(_path(material))
            require(path == _path(material), 'require_canonical_Game_material')
            assets[path] = _kind(material)
    state = dict(actor=_path(actor), actor_class=_kind(actor), actor_guid=guid, component=_path(component),
                 component_class=kind, creation_method=creation, mesh=_path(mesh), mesh_class=_kind(mesh),
                 slot_names=[str(s.get_editor_property('material_slot_name')) for s in slots],
                 defaults=[_path(m) for m in defaults], overrides=[_path(m) for m in overrides], effective=[_path(m) for m in effective])
    return component_state(state, world), assets


def inspect_selection(output, *, unreal_module=None):
    if unreal_module is None:
        import unreal as unreal_module
    u = unreal_module
    project, world = runtime(u)
    require(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'save_map_before_capture')
    actors = _bounded(u.get_editor_subsystem(u.EditorActorSubsystem).get_selected_level_actors(), 32, 'select_at_most_32_actors')
    require(actors, 'select_existing_mesh_actors_first')
    states, refs = [], {}
    for actor in actors:
        components = _bounded(actor.get_components_by_class(u.MeshComponent), 32, 'too_many_actor_components')
        require(components, 'selected_actor_has_no_mesh_components')
        for component in components:
            state, assets = read_component(component, world, u)
            states.append(state); refs.update(assets)
    require(len(states) <= 32, 'capture_exceeds_32_components')
    states.sort(key=lambda s:s['component'])
    result = dict(schema='cryptonyan.level-material-capture/1', project_root=str(project.root),
                  project_identity=project._project_identity(), world=world, map_file=map_file(project, world),
                  components=states, source_classes=refs, sources=snapshots(project, refs))
    result['identity'] = _hash(result)
    validate_capture(result)
    write_new(output, result, project.root)
    return result


def live_components(u, plan):
    actors = _bounded(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors(), 10000, 'too_many_loaded_actors')
    wanted = {op['before']['actor'] for op in plan['operations']}
    found = {}
    for actor in actors:
        if _path(actor) not in wanted:
            continue
        for component in _bounded(actor.get_components_by_class(u.MeshComponent), 64, 'too_many_actor_components'):
            path = _path(component)
            require(path not in found, 'ambiguous_component_path')
            found[path] = component
    return found


def current(u, plan, op):
    component = live_components(u, plan).get(op['component'])
    require(component is not None, 'target_component_missing_or_unloaded')
    return component, read_component(component, plan['world'], u)[0]


def set_state(component, state, sources):
    require(component.modify(), 'component_transaction_modify_failed')
    component.set_editor_property('override_materials', [sources[p] if p else None for p in state['overrides']])


def journal(folder, receipt):
    write_json(folder / 'operation.json', receipt)


def new_folder(path, plan):
    folder = _outside(path, GameProject(plan['project_root']))
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_json(folder / 'plan.json', plan)
    return folder


def execute(plan_path, output, *, apply=False, unreal_module=None):
    if type(apply) is not bool:
        raise ValueError('apply must be boolean')
    plan = load_plan(plan_path)
    folder = new_folder(output, plan)
    receipt = dict(schema='cryptonyan.level-material-operation/1', kind='apply', plan_identity=plan['identity'],
                   status='planned', attempted=[], changed=[], restored=[], conflicts=[], map_saved=False, assets_saved=False,
                   visual_quality_validated=False)
    journal(folder, receipt)
    if not apply:
        return receipt
    u = unreal_module
    try:
        if u is None:
            import unreal as u
        runtime(u, plan)
        require(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(), 'save_map_before_apply')
        sources = validate_sources(plan, u)
        for op in plan['operations']:
            require(current(u, plan, op)[1] == op['before'], 'component_changed_since_capture')
        require(load_plan(plan_path) == plan, 'plan_changed_before_apply')
        receipt['status'] = 'applying'; journal(folder, receipt)
        with u.ScopedEditorTransaction('CryptoNyan material variant review'):
            for op in plan['operations']:
                component, state = current(u, plan, op)
                require(state == op['before'], 'component_changed_during_apply')
                receipt['attempted'].append(op['component']); journal(folder, receipt)  # Intent BEFORE mutation.
                set_state(component, op['after'], sources)
                require(current(u, plan, op)[1] == op['after'], 'override_readback_failed')
                receipt['changed'].append(op['component']); journal(folder, receipt)
            require(load_plan(plan_path) == plan, 'sources_changed_during_apply')
            clean_content(u)
        receipt['status'] = 'applied_review_required'
    except Exception as error:
        receipt.update(status='failed', error=str(error) if isinstance(error, (ReviewError, ValueError)) else type(error).__name__)
        # Conditional rollback: never overwrite an unexpected intermediate or foreign state.
        if receipt['attempted']:
            with u.ScopedEditorTransaction('Rollback CryptoNyan material review'):
                for op in reversed(plan['operations']):
                    if op['component'] not in receipt['attempted']:
                        continue
                    try:
                        runtime(u, plan)
                        component, state = current(u, plan, op)
                        if state != op['before']:
                            require(state == op['after'], 'rollback_conflict')
                            set_state(component, op['before'], sources)
                            require(current(u, plan, op)[1] == op['before'], 'rollback_readback_failed')
                        receipt['restored'].append(op['component'])
                    except Exception:
                        receipt['conflicts'].append(op['component'])
        receipt['recovery_required'] = bool(receipt['conflicts'])
    finally:
        journal(folder, receipt)
    return receipt


def operation(folder):
    folder = Path(folder)
    plan = load_plan(safe_path(folder, 'plan.json'), verify_map=False)
    receipt = read_json(safe_path(folder, 'operation.json'))
    require(receipt.get('schema') == 'cryptonyan.level-material-operation/1' and receipt.get('kind') == 'apply'
            and receipt.get('plan_identity') == plan['identity'], 'operation_plan_identity_mismatch')
    attempted = receipt.get('attempted')
    paths = [op['component'] for op in plan['operations']]
    require(isinstance(attempted, list) and attempted == paths[:len(attempted)], 'invalid_attempted_component_journal')
    require(receipt.get('status') in ('planned', 'applying', 'applied_review_required', 'failed'), 'invalid_operation_status')
    require(receipt['status'] != 'planned' or not attempted, 'dry_run_cannot_own_changes')
    if receipt['status'] == 'applied_review_required':
        require(attempted == paths and receipt.get('changed') == paths, 'incomplete_success_journal')
    return plan, receipt


def restore(operation_folder, output, *, apply=False, unreal_module=None):
    if type(apply) is not bool:
        raise ValueError('apply must be boolean')
    plan, owned = operation(operation_folder)
    folder = new_folder(output, plan)
    result = dict(schema='cryptonyan.level-material-restoration/1', plan_identity=plan['identity'],
                  source_operation=str(Path(operation_folder).resolve()), status='planned', restored=[],
                  already_original=[], conflicts=[], attempted=[], map_saved=False, assets_saved=False, visual_quality_validated=False)
    journal(folder, result)
    if not apply:
        return result
    u = unreal_module
    ops = [op for op in plan['operations'] if op['component'] in owned['attempted']]
    try:
        if u is None:
            import unreal as u
        runtime(u, plan); sources = validate_sources(plan, u)
        # Dirty maps are allowed here: an unsaved review is precisely what must be reversible.
        # Check EVERY owned component before making the first restoration.
        for op in ops:
            state = current(u, plan, op)[1]
            if state not in (op['before'], op['after']):
                result['conflicts'].append(op['component'])
        require(not result['conflicts'], 'restoration_conflicts_require_manual_review')
        require(operation(operation_folder) == (plan, owned), 'operation_changed_before_restore')
        result['status'] = 'restoring'; journal(folder, result)
        with u.ScopedEditorTransaction('Restore CryptoNyan material overrides'):
            for op in reversed(ops):
                component, state = current(u, plan, op)
                if state == op['before']:
                    result['already_original'].append(op['component'])
                    continue
                require(state == op['after'], 'component_changed_during_restore')
                result['attempted'].append(op['component']); journal(folder, result)
                set_state(component, op['before'], sources)
                require(current(u, plan, op)[1] == op['before'], 'restore_readback_failed')
                result['restored'].append(op['component']); journal(folder, result)
        require(operation(operation_folder) == (plan, owned), 'sources_changed_during_restore')
        clean_content(u); result['status'] = 'restored_review_required'
    except Exception as error:
        result.update(status='failed', error=str(error) if isinstance(error, (ReviewError, ValueError)) else type(error).__name__,
                      recovery_required=True)
        # Already restored components stay original; rerun from the apply journal with a new receipt.
    finally:
        journal(folder, result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description='Inspect selected level meshes, apply a material review or restore it')
    sub = p.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('inspect'); capture.add_argument('--output', type=Path, required=True)
    for name in ('apply', 'restore'):
        cmd = sub.add_parser(name); cmd.add_argument('input', type=Path)
        cmd.add_argument('--output', type=Path, required=True); cmd.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    if args.command == 'inspect':
        result = inspect_selection(args.output)
    else:
        result = (execute if args.command == 'apply' else restore)(args.input, args.output, apply=args.apply)
    print(json.dumps(result)); return 1 if result.get('status') == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
