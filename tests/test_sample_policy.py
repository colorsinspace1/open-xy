"""Sample assignment policy: versioned defaults, explicit declarations and generated registration."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tooling.adapters import generate_sample_callbacks
from tooling.machines import machine_at
from machine_fixtures import FOLDER


class SamplePolicy(unittest.TestCase):
    def test_versioned_defaults_and_explicit_policy_reach_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'machine'
            shutil.copytree(FOLDER / 'probesample', root)
            metadata = json.loads((root / 'machine.json').read_text(encoding='utf-8'))
            definition = json.loads((root / 'definition.json').read_text(encoding='utf-8'))
            cases = [(f'1.{minor}', 2, None, False) for minor in range(5)]
            cases += [('1.5', 2, None, True), ('1.5', 2, 1, True), ('1.5', 2, 0, False),
                      ('1.5', 7, None, False), ('1.5', 7, 0, False)]
            for version, page, flag, expected in cases:
                with self.subTest(version=version, page=page, flag=flag):
                    metadata['sdk'], metadata['identity']['page'] = version, page
                    definition['resources'] = dict(voiceCapacity=256)
                    if flag is not None:
                        definition['resources']['singleSample'] = flag
                    (root / 'machine.json').write_text(json.dumps(metadata), encoding='utf-8')
                    (root / 'definition.json').write_text(json.dumps(definition), encoding='utf-8')
                    machine = machine_at(root)
                    self.assertEqual(machine.single_sample, expected)
                    generated = generate_sample_callbacks(temporary, [machine]).read_text(encoding='utf-8')
                    self.assertIn(f'probesample_engine_id, {page}, probesample_ready, {int(expected)},', generated)

    def test_invalid_flags_version_and_drum_assignment_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'machine'
            shutil.copytree(FOLDER / 'probesample', root)
            metadata = json.loads((root / 'machine.json').read_text(encoding='utf-8'))
            definition = json.loads((root / 'definition.json').read_text(encoding='utf-8'))
            cases = [('1.4', 2, 0), ('1.4', 2, 1), ('1.5', 7, 1)]
            cases += [('1.5', 2, flag) for flag in (-1, 2, True, '1', 1.0)]
            for version, page, flag in cases:
                with self.subTest(version=version, page=page, flag=flag):
                    metadata['sdk'], metadata['identity']['page'] = version, page
                    definition['resources'] = dict(voiceCapacity=256, singleSample=flag)
                    (root / 'machine.json').write_text(json.dumps(metadata), encoding='utf-8')
                    (root / 'definition.json').write_text(json.dumps(definition), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        machine_at(root)
