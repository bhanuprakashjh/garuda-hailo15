"""Prevent sparse appearance diagnostics from counting malformed or duplicate evidence."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location('object_embeddings', Path(__file__).resolve().parents[3] / 'bench/fresh_object_embeddings.py')
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class ObjectEmbeddingScoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.args = SimpleNamespace(manifest=root/'manifest.json', embeddings=root/'embeddings.jsonl', output=root/'score.json')
        self.manifest = {'anchor': 0, 'frames': [
            {'frame': 0, 'role': 'same_phone', 'nv12_sha256': 'a'*64},
            {'frame': 1, 'role': 'same_phone', 'nv12_sha256': 'b'*64},
            {'frame': 2, 'role': 'other_phone', 'nv12_sha256': 'c'*64},
            {'frame': 3, 'role': 'duplicate', 'duplicate_of': 0, 'nv12_sha256': 'a'*64}]}
        self.rows = [dict(frame=i, model='fixture', input_width=224, input_height=224,
                          embedding=[x, y]+[0.0]*510) for i, (x, y) in enumerate([(1, 0), (.8, .6), (0, 1), (1, 0)])]

    def run_score(self):
        self.args.manifest.write_text(json.dumps(self.manifest))
        self.args.embeddings.write_text('\n'.join(json.dumps(row) for row in self.rows))
        TOOL.score(self.args)
        return json.loads(self.args.output.read_text())

    def test_known_cosines_and_duplicate_excluded(self):
        result = self.run_score()
        self.assertEqual(result['anchor_same_phone_range'], [.8, .8])
        self.assertEqual(result['anchor_other_phone_range'], [0, 0])
        self.assertEqual(result['same_phone_views'], 2)
        self.assertEqual(result['duplicate_max_abs_difference'], {'3': 0})
        self.assertEqual(result['fixed_threshold_diagnostic'][2]['same_phone_accepted'], 1)

    def test_explicit_alternate_anchor(self):
        self.manifest['anchor'] = 1
        self.assertEqual(self.run_score()['anchor_other_phone_range'], [.6, .6])

    def test_invalid_observations_rejected(self):
        for field, value in [('model', 'other-model'), ('frame', 0), ('input_width', 128), ('embedding', [math.nan]*512), ('embedding', [1.0]*512)]:
            with self.subTest(field=field, value=str(value)[:20]):
                original = self.rows[1][field]
                self.rows[1][field] = value
                with self.assertRaises(ValueError):
                    self.run_score()
                self.rows[1][field] = original

    def test_incomplete_output_rejected(self):
        self.rows.pop()
        with self.assertRaises(ValueError):
            self.run_score()

    def test_duplicate_cannot_inflate_queries(self):
        self.manifest['frames'][3]['role'] = 'same_phone'
        with self.assertRaises(ValueError):
            self.run_score()

    def test_duplicate_requires_identical_input(self):
        self.manifest['frames'][3]['nv12_sha256'] = 'd'*64
        with self.assertRaises(ValueError):
            self.run_score()


if __name__ == '__main__':
    unittest.main()
