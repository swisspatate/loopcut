# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/addons_core'))
from cryptonyan_asset_studio import wardrobe_review as wardrobe
from cryptonyan_asset_studio.executors import WorkerFailure
from cryptonyan_asset_studio.storage import digest
BLENDER = os.environ.get('LOOPCUT_BLENDER') or shutil.which('blender')


def spec():
    capture = dict(armature='ExistingRig', action='Bend', start_frame=1, end_frame=3, step_frames=1,
        settings=dict(root='Origin', bones=['Tip'], loop=False, motion='in_place', contact_space='unknown', contacts=[]))
    return dict(schema='cryptonyan.wardrobe-review/1', armature='ExistingRig', body='Body', garments=['Shirt', 'Cape'],
        captures=[capture, {**copy.deepcopy(capture), 'action': 'Safe'}], tolerance_m=.0001, max_influences=4)


class ContractTests(unittest.TestCase):
    def test_parse_is_independent_of_input(self):
        value = spec(); before = copy.deepcopy(value); parsed = wardrobe.specification(value)
        self.assertEqual(value, before)
        parsed['garments'].append('New'); parsed['captures'][0]['settings']['bones'].append('New')
        self.assertEqual(value, before)

    def test_unknown_schema_and_keys(self):
        for update in ({'schema': 'other'}, {'repair': True}):
            with self.subTest(update=update), self.assertRaises(ValueError): wardrobe.specification({**spec(), **update})

    def test_names_must_be_distinct(self):
        for garments in ([], ['Body'], ['ExistingRig'], ['Shirt', 'Shirt'], ['Bad\nName'], ['a']*9, 'Shirt'):
            with self.subTest(garments=garments), self.assertRaises(ValueError): wardrobe.specification({**spec(), 'garments': garments})

    def test_budgets_reject_bool_nan_and_out_of_range(self):
        for key, value in (('tolerance_m', True), ('tolerance_m', float('nan')), ('tolerance_m', 0),
                           ('tolerance_m', .1), ('max_influences', True), ('max_influences', 9)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): wardrobe.specification({**spec(), key: value})

    def test_action_mapping_and_duplicate_windows(self):
        for change in ('duplicate', 'rig', 'slots'):
            value = spec()
            if change == 'duplicate': value['captures'][1] = copy.deepcopy(value['captures'][0])
            elif change == 'rig': value['captures'][0]['armature'] = 'Other'
            else: value['captures'][0]['action_slot'] = ''
            with self.subTest(change=change), self.assertRaises(ValueError): wardrobe.specification(value)

    def test_combined_sample_budget_and_endpoints(self):
        value = spec()
        for capture in value['captures']: capture['end_frame'] = 121
        with self.assertRaises(ValueError): wardrobe.specification(value)
        for capture in value['captures']: capture['end_frame'] = 120
        self.assertEqual(len(wardrobe.specification(value)['captures']), 2)
        value['captures'][0]['step_frames'] = 2
        with self.assertRaises(ValueError): wardrobe.specification(value)

    def test_sampling_requires_at_least_one_and_at_most_eight_windows(self):
        for captures in ([], 'Bad', spec()['captures']*5):
            with self.subTest(captures=captures), self.assertRaises(ValueError): wardrobe.specification({**spec(), 'captures': captures})

    def test_failure_receipt_and_no_source_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.blend'; source.write_bytes(b'snapshot')
            binary = root / 'blender'; binary.write_bytes(b'not executed')
            with patch.object(wardrobe, 'run_process', side_effect=RuntimeError('stop')):
                with self.assertRaises(RuntimeError): wardrobe.run(source, spec(), root / 'out', binary)
            result = json.loads((root / 'out/result.json').read_text())
            self.assertEqual(result['status'], 'failed'); self.assertEqual(result['copies'], [])
            self.assertFalse(result['visual_quality_validated']); self.assertEqual(source.read_bytes(), b'snapshot')

    def test_existing_output_and_invalid_inputs_fail_before_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.blend'; source.write_bytes(b'abc')
            with self.assertRaises(FileExistsError): wardrobe.run(source, spec(), root, source)
            with self.assertRaises(ValueError): wardrobe.run(source, spec(), root / 'out', root / 'missing')
            with self.assertRaises(ValueError): wardrobe.run(source, spec(), root / 'out', source, timeout=True)
            self.assertEqual(list(root.iterdir()), [source])

    def test_offline_html_escapes_and_csv_does_not_execute_formulas(self):
        sample = dict(frame=1, time_s=0, negative_signed_distance_vertices=2, max_depth_m=.002, surface_crossing_edges=0)
        report = dict(clips=[dict(index=1, capture=dict(action='<script>x</script>'), review_file='review-01.blend',
            garments=[dict(name='=HYPERLINK("bad")', worst=sample, flagged_frames=1, samples=[sample])])])
        with tempfile.TemporaryDirectory() as temp:
            wardrobe.tables(report, temp); root = Path(temp); text = (root / 'review.html').read_text()
            self.assertNotIn('<script>', text); self.assertIn('&lt;script&gt;', text)
            with (root / 'samples.csv').open(newline='', encoding='utf-8') as stream: rows = list(csv.reader(stream))
            self.assertTrue(rows[1][2].startswith("'=")); self.assertNotIn('http', text)

    def test_cli_help_is_available_without_blender_import(self):
        result = subprocess.run([sys.executable, '-m', 'cryptonyan_asset_studio.wardrobe_review', '--help'],
            env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts/addons_core')}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertIn('--blender', result.stdout)


@unittest.skipUnless(BLENDER, 'Blender executable unavailable')
class BlenderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)

    def fixture(self, *flags):
        source = self.root / 'source.blend'
        self.blender('create', str(source), *flags); return source

    def blender(self, *args):
        result = subprocess.run([BLENDER, '--background', '--factory-startup', '--disable-autoexec', '--threads', '1',
            '--python-exit-code', '1', '--python', str(ROOT / 'loopcut/harness/cryptonyan_wardrobe_fixture.py'), '--', *args],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return result.stdout

    def test_multi_action_clothes_and_shape_keys_reopen_through_real_sidebar(self):
        source = self.fixture('--shape'); before = digest(source)
        (self.root / 'spec.json').write_text(json.dumps(spec()), encoding='utf-8')
        self.assertIn('CRYPTONYAN_WARDROBE_ASSERTIONS_PASSED', self.blender('ui', str(self.root)))
        receipt = json.loads((self.root / 'review/result.json').read_text())
        report = json.loads((self.root / 'review/wardrobe.json').read_text())
        self.assertEqual(digest(source), before); self.assertEqual(receipt['source_sha256'], before)
        self.assertEqual(report['weight_audit']['findings'], [])
        bend, safe = report['clips']
        self.assertEqual(bend['garments'][0]['worst']['frame'], 3)
        self.assertGreater(bend['garments'][0]['worst']['max_depth_m'], .2)
        self.assertEqual(bend['garments'][1]['flagged_frames'], 0)
        self.assertTrue(all(g['flagged_frames'] == 0 for g in safe['garments']))
        self.assertEqual([s['frame'] for s in bend['garments'][0]['samples']], [1, 2, 3])
        self.assertFalse(report['surface_collision_certified']); self.assertFalse(receipt['visual_quality_validated'])
        for candidate in receipt['copies']: self.assertEqual(digest(self.root / 'review' / candidate['file']), candidate['sha256'])
        self.assertTrue((self.root / 'review/review.html').is_file())

    def test_surface_crossing_with_no_garment_vertex_inside(self):
        source = self.fixture('--cross'); value = spec(); value['captures'] = [value['captures'][1]]
        wardrobe.run(source, value, self.root / 'review', BLENDER)
        report = json.loads((self.root / 'review/wardrobe.json').read_text())
        rows = report['clips'][0]['garments'][0]['samples']
        self.assertTrue(all(s['negative_signed_distance_vertices'] == 0 for s in rows))
        self.assertTrue(all(s['surface_crossing_edges'] > 0 and s['flagged'] for s in rows))
        self.assertTrue(any(e['source'] == 'body' for e in rows[0]['crossing_edges']))

    def test_open_body_fails_with_receipt_and_no_source_change(self):
        self.assert_failed('--open')

    def test_wrong_rig_fails_with_receipt_and_no_source_change(self):
        self.assert_failed('--wrong-rig')

    def assert_failed(self, flag):
        source = self.fixture(flag); before = digest(source)
        with self.assertRaises(WorkerFailure): wardrobe.run(source, spec(), self.root / 'review', BLENDER)
        result = json.loads((self.root / 'review/result.json').read_text())
        self.assertEqual(result['status'], 'failed'); self.assertEqual(digest(source), before)
        self.assertFalse((self.root / 'review/review.html').exists())

    def test_unknown_action_fails_before_review_copy(self):
        source = self.fixture(); value = spec(); value['captures'][0]['action'] = 'Missing'
        with self.assertRaises(WorkerFailure): wardrobe.run(source, value, self.root / 'review', BLENDER)
        self.assertFalse(list((self.root / 'review').glob('review-*.blend')))

    def test_cli_reports_issues_and_converts_scene_units_to_metres(self):
        source = self.fixture('--units'); before = digest(source)
        request = self.root / 'spec.json'; request.write_text(json.dumps(spec()), encoding='utf-8')
        output = self.root / 'review with spaces'
        result = subprocess.run([sys.executable, '-m', 'cryptonyan_asset_studio.wardrobe_review', str(source), str(request),
            '--output', str(output), '--blender', BLENDER],
            env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts/addons_core')}, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 1, result.stdout+result.stderr)
        receipt = json.loads(result.stdout); self.assertEqual(receipt['status'], 'review_required')
        report = json.loads((output / 'wardrobe.json').read_text())
        self.assertAlmostEqual(report['clips'][0]['garments'][0]['worst']['max_depth_m'], .075, places=5)
        self.assertEqual(digest(source), before)


if __name__ == '__main__':
    unittest.main()
