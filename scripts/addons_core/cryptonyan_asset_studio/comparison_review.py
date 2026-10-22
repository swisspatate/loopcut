# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned comparison recipes and offline evidence bundles for the existing game."""
import argparse
import copy
import html
import json
from pathlib import Path
import re

from .animation_doctor import exact, name, number, read_json
from .camera_moves import _pose
from .creative_director import identifier, integer, rows, snapshots, vector, write_new
from .game_project import GameProject, MAX_TARGET_BYTES
from .image_workshop import identity
from .materials import read_png
from .publication import _hash as hash_value
from .storage import digest, safe_path, write_json
from .unreal_material_variants import _object_path, _outside


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ('schema', 'id', 'target_level', 'anchor_m', 'yaw_deg', 'camera', 'lights', 'variants', 'pose'))
    if value['schema'] != 'cryptonyan.comparison/1':
        raise ValueError('Unsupported comparison schema')
    identifier(value['id'])
    if not isinstance(value['target_level'], str) or not re.fullmatch(r'/Game/CryptoNyan/ReviewMaps/[A-Za-z][A-Za-z0-9_]{0,47}', value['target_level']):
        raise ValueError('Choose an explicit empty review map')
    value['anchor_m'] = vector(value['anchor_m'], -1000, 1000)
    number(value['yaw_deg'], -360, 360)
    camera = value['camera']
    exact(camera, ('position_m', 'target_m', 'fov_deg', 'aspect_ratio', 'exposure_bias_ev'))
    for key in ('position_m', 'target_m'): camera[key] = vector(camera[key], -1000, 1000)
    camera_pose(camera)  # Shared look-at helper rejects a vertical/zero direction.
    number(camera['fov_deg'], 5, 150); number(camera['aspect_ratio'], .5, 4)
    number(camera['exposure_bias_ev'], -16, 16)
    if len(rows(value['lights'], 2)) != 2:
        raise ValueError('Choose exactly two common white directional lights')
    for light in value['lights']:
        exact(light, ('rotation_rpy_deg', 'lux'))
        light['rotation_rpy_deg'] = vector(light['rotation_rpy_deg'], -360, 360)
        number(light['lux'], 0, 150000)
    if not any(light['lux'] > 0 for light in value['lights']):
        raise ValueError('At least one light must be enabled')
    variants = rows(value['variants'], 8)
    if len(variants) < 2:
        raise ValueError('Choose a baseline and at least one candidate')
    ids, classes = set(), set()
    for item in variants:
        exact(item, ('id', 'label', 'mesh', 'mesh_class', 'materials'))
        key = identifier(item['id']).casefold()
        if key in ids or key in ('camera', 'light0', 'light1'): raise ValueError('Duplicate or reserved variant ID')
        ids.add(key); name(item['label'])
        item['mesh'] = _object_path(item['mesh'])
        if item['mesh_class'] not in ('StaticMesh', 'SkeletalMesh'):
            raise ValueError('Choose a StaticMesh or SkeletalMesh')
        classes.add(item['mesh_class'])
        if not isinstance(item['materials'], list) or len(item['materials']) > 32:
            raise ValueError('At most 32 explicit material slot overrides')
        slots = set()
        for override in item['materials']:
            exact(override, ('slot', 'material'))
            integer(override['slot'], 0, 31)
            if override['slot'] in slots: raise ValueError('Duplicate slot override')
            slots.add(override['slot']); override['material'] = _object_path(override['material'])
        item['materials'].sort(key=lambda m: m['slot'])
    if len(classes) != 1:
        raise ValueError('Compare meshes of the same class')
    if value['pose'] is not None:
        exact(value['pose'], ('animation', 'time_s'))
        if classes != {'SkeletalMesh'}: raise ValueError('Animation requires skeletal variants')
        value['pose']['animation'] = _object_path(value['pose']['animation'])
        number(value['pose']['time_s'], 0, 600)
    references(value)  # Reject conflicting source roles before any filesystem work.
    return value


def camera_pose(camera):
    return _pose(dict(move='line', easing='linear', start_m=camera['position_m'], end_m=camera['position_m'], target_m=camera['target_m']), 0)


def references(spec):
    result = {}
    def add(path, kind):
        if path in result and result[path] != kind: raise ValueError('Conflicting source asset roles')
        result[path] = kind
    for item in spec['variants']:
        add(item['mesh'], item['mesh_class'])
        for override in item['materials']: add(override['material'], 'MaterialInterface')
    if spec['pose']: add(spec['pose']['animation'], 'AnimSequence')
    return dict(sorted(result.items()))


def make_plan(spec, project_root):
    spec = specification(spec); project = GameProject(project_root); refs = references(spec)
    relative = 'Content/'+spec['target_level'][6:]+'.umap'
    plan = dict(schema='cryptonyan.comparison-plan/1', specification=spec, project_root=str(project.root),
        project_identity=project._project_identity(), source_classes=refs, sources=snapshots(project, refs),
        map_snapshot=map_snapshot(project, relative), engine_validated=False,
        dependency_scope='explicit_packages_and_sidecars_offline_plus_live_material_inspection_in_editor')
    plan['identity'] = identity(plan)
    return plan


def map_snapshot(project, relative):
    asset = project._asset(relative); path = safe_path(project.root, relative)
    if asset['git_lfs_pointer'] or not 0 < asset['bytes'] <= MAX_TARGET_BYTES:
        raise ValueError('Require a downloaded saved map of at most 512 MiB')
    before = path.stat(); sha = digest(path); after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Map changed during fingerprinting')
    return dict(path=relative, sha256=sha, bytes=after.st_size)


def load_plan(path):
    plan = read_json(path)
    exact(plan, ('schema', 'specification', 'project_root', 'project_identity', 'source_classes', 'sources',
                 'map_snapshot', 'engine_validated', 'dependency_scope', 'identity'))
    if make_plan(plan['specification'], plan['project_root']) != plan:
        raise ValueError('Comparison plan, map, project or source packages changed')
    return plan


def load_capture(folder, plan):
    folder = Path(folder); value = read_json(folder/'capture.json')
    exact(value, ('schema', 'plan_identity', 'stage_id', 'conditions_identity', 'variant', 'image', 'provenance', 'gpu_measured'))
    if (value['schema'] != 'cryptonyan.comparison-capture/1' or value['plan_identity'] != plan['identity']
            or value['provenance'] != 'user_supplied_png_not_renderer_verified' or value['gpu_measured'] is not False):
        raise ValueError('Unbound or unsupported comparison capture')
    hash_value(value['conditions_identity']); identifier(value['stage_id'])
    if value['variant'] not in {v['id'] for v in plan['specification']['variants']}:
        raise ValueError('Unknown captured variant')
    exact(value['image'], ('file', 'sha256', 'width', 'height'))
    if value['image']['file'] != 'image.png': raise ValueError('Unexpected image path')
    image = safe_path(folder, 'image.png'); _, dimensions = read_png(image)
    if dimensions != {k: value['image'][k] for k in ('width', 'height')} or digest(image) != value['image']['sha256']:
        raise ValueError('Capture image changed')
    return value


def compare(plan_path, capture_folders, output):
    plan = load_plan(plan_path)
    if not isinstance(capture_folders, list) or not 2 <= len(capture_folders) <= 8:
        raise ValueError('Compare 2 to 8 captured variants')
    captures = [load_capture(p, plan) for p in capture_folders]
    if len({c['variant'] for c in captures}) != len(captures): raise ValueError('Duplicate capture variant')
    for keys in (('stage_id',), ('conditions_identity',)):
        if len({tuple(c[k] for k in keys) for c in captures}) != 1: raise ValueError('Different comparison sessions or conditions')
    if len({(c['image']['width'], c['image']['height']) for c in captures}) != 1:
        raise ValueError('Captured dimensions differ')
    if plan['specification']['variants'][0]['id'] not in {c['variant'] for c in captures}:
        raise ValueError('Include the baseline capture')
    output = _outside(output, GameProject(plan['project_root']), *capture_folders).resolve()
    output.mkdir(parents=True, exist_ok=False)
    labels = {v['id']: v['label'] for v in plan['specification']['variants']}
    cards = []
    for folder, capture in zip(capture_folders, captures):
        data, _ = read_png(safe_path(folder, 'image.png'))
        if identity(read_json(Path(folder)/'capture.json')) != identity(capture) or digest(safe_path(folder, 'image.png')) != capture['image']['sha256']:
            raise ValueError('Capture changed during comparison')
        filename = capture['variant']+'.png'; (output/filename).write_bytes(data)
        if digest(output/filename) != capture['image']['sha256']: raise ValueError('Image changed during copy')
        cards.append('<figure><figcaption>'+html.escape(labels[capture['variant']])+'</figcaption><img alt="Variante" src="'+filename+'"></figure>')
    page = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Comparaison Unreal</title>'
        '<style>body{font:16px system-ui;margin:2em}main{display:flex;flex-wrap:wrap;gap:1em}figure{margin:0;flex:1;min-width:280px}img{width:100%}</style>'
        '<h1>Comparaison des variantes</h1><p>PNG fournis manuellement ; leur origine dans le renderer et leur synchronisation '
        'ne sont pas vérifiées. Même session et réglages de scène contrôlés au moment de la collecte. Aucune mesure GPU.</p>'
        '<main>'+''.join(cards)+'</main></html>')
    (output/'comparison.html').write_text(page, encoding='utf-8')
    if load_plan(plan_path) != plan: raise ValueError('Comparison sources changed')
    result = dict(schema='cryptonyan.comparison-gallery/1', plan_identity=plan['identity'], captures=captures,
                  engine_validated=False, visual_quality_validated=False, gpu_measured=False)
    write_json(output/'comparison.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('plan'); prepare.add_argument('specification', type=Path)
    prepare.add_argument('--project', required=True, type=Path); prepare.add_argument('--output', required=True, type=Path)
    gallery = sub.add_parser('compare'); gallery.add_argument('plan', type=Path); gallery.add_argument('captures', nargs='+', type=Path)
    gallery.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'plan':
        result = make_plan(read_json(args.specification), args.project); write_new(args.output, result, args.project)
    else: result = compare(args.plan, args.captures, args.output)
    print(json.dumps(result, indent=2)); return 0


if __name__ == '__main__': raise SystemExit(main())
