# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline plans for reversible material overrides on explicitly inspected components."""
import argparse
import copy
import html
import json
from pathlib import Path
import re

from .animation_doctor import exact, name, read_json
from .creative_director import integer, rows, snapshots, write_new
from .game_project import GameProject
from .storage import digest, safe_path
from .unreal_material_variants import _hash, _object_path


def map_file(project, world):
    path = safe_path(project.root, 'Content/'+_object_path(world).split('.')[0][6:]+'.umap')
    info = project._asset(path.relative_to(project.root).as_posix())
    if info['git_lfs_pointer'] or not 0 < info['bytes'] <= 512*1024*1024:
        raise ValueError('Require a saved downloaded map of at most 512 MiB')
    before = path.stat()
    sha = digest(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Map changed while reading')
    return dict(path=info['path'], bytes=after.st_size, sha256=sha)


def material_path(value):
    return None if value is None else _object_path(value)


def component_state(value, world):
    exact(value, ('actor', 'actor_class', 'actor_guid', 'component', 'component_class', 'creation_method',
                  'mesh', 'mesh_class', 'slot_names', 'defaults', 'overrides', 'effective'))
    for key in ('actor_class', 'component_class'):
        name(value[key])
    prefix = re.escape(world+':PersistentLevel.')
    if not isinstance(value['actor'], str) or not re.fullmatch(prefix+r'[A-Za-z0-9_]+', value['actor']):
        raise ValueError('Target must be in the persistent editor level')
    if not isinstance(value['component'], str) or not re.fullmatch(re.escape(value['actor'])+r'\.[A-Za-z0-9_]+', value['component']):
        raise ValueError('Component must belong directly to the captured actor')
    guid = value['actor_guid']
    if not isinstance(guid, str) or not re.fullmatch(r'[0-9a-f]{32}', guid) or guid == '0'*32:
        raise ValueError('Require a stable nonzero actor GUID')
    classes = {'StaticMeshComponent': 'StaticMesh', 'SkeletalMeshComponent': 'SkeletalMesh'}
    if classes.get(value['component_class']) != value['mesh_class'] or value['creation_method'] not in ('native', 'instance'):
        raise ValueError('Only native/instance static or skeletal mesh components are supported')
    if value['mesh'] != _object_path(value['mesh']):
        raise ValueError('Require canonical mesh path')
    slots = rows(value['slot_names'], 32)
    for slot in slots:
        name(slot)
    for field in ('defaults', 'overrides', 'effective'):
        values = value[field]
        if not isinstance(values, list) or len(values) > len(slots) or (field != 'overrides' and len(values) != len(slots)):
            raise ValueError('Invalid material array length')
        if any(material_path(v) != v for v in values):
            raise ValueError('Require canonical material paths')
    effective = [value['overrides'][i] if i < len(value['overrides']) and value['overrides'][i] is not None else base
                 for i, base in enumerate(value['defaults'])]
    if value['effective'] != effective:
        raise ValueError('Effective materials disagree with defaults and overrides')
    return value


def validate_capture(value, *, verify_map=True):
    exact(value, ('schema', 'project_root', 'project_identity', 'world', 'map_file', 'components', 'sources', 'source_classes', 'identity'))
    if value['schema'] != 'cryptonyan.level-material-capture/1' or value['identity'] != _hash({k:v for k,v in value.items() if k != 'identity'}):
        raise ValueError('Capture identity mismatch')
    project = GameProject(value['project_root'])
    if project._project_identity() != value['project_identity'] or _object_path(value['world']) != value['world']:
        raise ValueError('Capture project/world mismatch')
    seen, refs = set(), {}
    for state in rows(value['components'], 32):
        component_state(state, value['world'])
        if state['component'] in seen:
            raise ValueError('Duplicate captured component')
        seen.add(state['component']); refs[state['mesh']] = state['mesh_class']
        for field in ('defaults', 'overrides', 'effective'):
            for path in state[field]:
                if path is not None:
                    kind = value['source_classes'].get(path)
                    if kind not in ('Material', 'MaterialInstanceConstant') or (path in refs and refs[path] != kind):
                        raise ValueError('Invalid material source class')
                    refs[path] = kind
    if refs != value['source_classes'] or snapshots(project, refs) != value['sources']:
        raise ValueError('Captured source assets changed')
    if verify_map and map_file(project, value['world']) != value['map_file']:
        raise ValueError('Map file changed since capture')
    return project


def make_plan(capture, assignments, *, verify_map=True):
    capture, assignments = copy.deepcopy(capture), copy.deepcopy(assignments)
    project = validate_capture(capture, verify_map=verify_map)
    states = {s['component']: s for s in capture['components']}
    seen, grouped, refs = set(), {}, dict(capture['source_classes'])
    for item in rows(assignments, 128):
        exact(item, ('component', 'slot', 'material'))
        if not isinstance(item['component'], str) or item['component'] not in states:
            raise ValueError('Assignment requires an explicitly captured component')
        slot = integer(item['slot'], 0, len(states[item['component']]['slot_names'])-1)
        key = (item['component'], slot)
        if key in seen:
            raise ValueError('Duplicate component/slot assignment')
        seen.add(key); item['material'] = _object_path(item['material'])
        if item['material'] == states[item['component']]['effective'][slot]:
            raise ValueError('Assignment would not change the effective material')
        if item['material'] in refs and refs[item['material']] != 'MaterialInstanceConstant':
            raise ValueError('Variant must be a saved MaterialInstanceConstant')
        refs[item['material']] = 'MaterialInstanceConstant'
        grouped.setdefault(item['component'], []).append(item)
    assignments.sort(key=lambda i:(i['component'], i['slot']))
    operations = []
    for path, items in sorted(grouped.items()):
        before = states[path]; after = copy.deepcopy(before)
        for item in items:
            while len(after['overrides']) <= item['slot']:
                after['overrides'].append(None)
            after['overrides'][item['slot']] = item['material']
            after['effective'][item['slot']] = item['material']
        component_state(after, capture['world'])
        operations.append(dict(component=path, before=before, after=after))
    result = dict(schema='cryptonyan.level-material-plan/1', capture=capture, assignments=assignments,
                  project_root=str(project.root), project_identity=project._project_identity(), world=capture['world'],
                  operations=operations, source_classes=refs, sources=snapshots(project, refs),
                  dependency_scope='explicit_meshes_materials_and_package_sidecars', automatic_save=False)
    return {**result, 'identity': _hash(result)}


def load_plan(path, *, verify_map=True):
    value = read_json(path)
    if not isinstance(value, dict) or value.get('schema') != 'cryptonyan.level-material-plan/1':
        raise ValueError('Invalid level material plan')
    if value != make_plan(value['capture'], value['assignments'], verify_map=verify_map):
        raise ValueError('Plan or source assets changed')
    return value


def comparison_html(plan):
    cells = []
    for op in plan['operations']:
        for i, (before, after) in enumerate(zip(op['before']['effective'], op['after']['effective'])):
            if before != after:
                values = (op['component'], str(i), op['before']['slot_names'][i], before or '(aucun)', after or '(aucun)')
                cells.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+'</tr>')
    return '''<!doctype html><html lang="fr"><meta charset="utf-8"><title>Revue des matériaux</title>
<style>body{font:16px system-ui;margin:2rem;color:#17202a}table{border-collapse:collapse;width:100%}td,th{padding:.6rem;border:1px solid #ddd;text-align:left;overflow-wrap:anywhere}code{overflow-wrap:anywhere}</style>
<h1>Variantes de matériaux du niveau</h1><p>Comparaison des affectations. Aucun rendu ou jugement de qualité visuelle automatique.</p>
<p>Plan : <code>'''+html.escape(plan['identity'])+'''</code></p><table><thead><tr><th>Composant</th><th>Slot</th><th>Nom</th><th>Original</th><th>Variante</th></tr></thead><tbody>'''+''.join(cells)+'</tbody></table></html>\n'


def main(argv=None):
    p = argparse.ArgumentParser(description='Plan reversible level material overrides offline')
    p.add_argument('capture', type=Path); p.add_argument('assignments', type=Path)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--html', type=Path)
    args = p.parse_args(argv)
    plan = make_plan(read_json(args.capture), read_json(args.assignments))
    write_new(args.output, plan, plan['project_root'])
    if args.html:
        from .unreal_material_variants import _outside
        with _outside(args.html, GameProject(plan['project_root'])).open('x', encoding='utf-8') as stream:
            stream.write(comparison_html(plan))
    print(json.dumps(dict(identity=plan['identity'], components=len(plan['operations']), slots=len(plan['assignments']))))


if __name__ == '__main__':
    main()
