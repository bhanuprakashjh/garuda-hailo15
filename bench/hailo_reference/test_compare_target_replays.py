import copy
import unittest
from compare_target_replays import compare, evaluate


class PairedTargetTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(canvas=[100, 100], targets=[dict(index=i, box=[10, 20, 20, 30]) for i in range(3)])
        self.rows = [dict(source_index=i, age_ms=100,
            raw_detections=[dict(x=.1, y=.2, w=.2, h=.3, confidence=.9, label='car')],
            output=dict(lock=dict(control_valid=True, reason='observed', box=dict(x=10, y=20, w=20, h=30)))) for i in range(3)]

    def score(self, rows):
        return evaluate(rows, self.manifest, 0, 'car', .4)

    def test_unchanged_and_vacuous_are_not_improvements(self):
        scored = self.score(self.rows)
        self.assertTrue(compare(scored, scored)['quality_nonregression_screen_passed'])
        self.assertFalse(compare(scored, scored)['conservative_improvement_screen_passed'])
        for r in self.rows:
            r['output']['lock']['control_valid'] = False
        empty = self.score(self.rows)
        self.assertFalse(compare(empty, empty)['conservative_improvement_screen_passed'])

    def test_real_paired_gain(self):
        candidate = self.score(self.rows)
        self.rows[1]['output']['lock']['control_valid'] = False
        report = compare(self.score(self.rows), candidate)
        self.assertTrue(report['conservative_improvement_screen_passed'])
        self.assertEqual(report['gained_on_target_indices'], [1])
        self.assertFalse(report['deployment_qualified'])

    def test_wrong_class_and_weak_detection_not_usable(self):
        for r in self.rows:
            r['output']['lock']['control_valid'] = False
        self.rows[0]['raw_detections'][0]['label'] = 'person'
        self.rows[1]['raw_detections'][0]['confidence'] = .3
        rows = self.score(self.rows)
        self.assertEqual(rows[0]['category'], 'only_wrong_class_overlap')
        self.assertEqual(rows[1]['category'], 'same_class_detection_below_control_floor')
        self.assertEqual(rows[2]['category'], 'refused_despite_usable_detection')

    def test_new_bad_box_blocks_gain_even_with_nonzero_overlap(self):
        base = copy.deepcopy(self.rows)
        for r in base:
            r['output']['lock']['control_valid'] = False
        self.rows[1]['output']['lock']['box']['w'] = 5
        report = compare(self.score(base), self.score(self.rows))
        self.assertEqual(report['candidate']['zero_overlap'], 0)
        self.assertEqual(report['introduced_off_target_indices'], [1])
        self.assertFalse(report['conservative_improvement_screen_passed'])

    def test_latency_regression_blocks_gain(self):
        base = copy.deepcopy(self.rows)
        base[1]['output']['lock']['control_valid'] = False
        for r in self.rows:
            r['age_ms'] = 210
        self.assertFalse(compare(self.score(base), self.score(self.rows))['conservative_improvement_screen_passed'])

    def test_unequal_indices_rejected(self):
        with self.assertRaises(ValueError):
            compare(self.score(self.rows), self.score(self.rows[:2]))

    def test_malformed_and_reordered_evidence_rejected(self):
        for mutate in (lambda r: r[0].update(age_ms=float('nan')),
                       lambda r: r[0]['raw_detections'][0].update(confidence=float('nan')),
                       lambda r: r[0]['output']['lock'].update(control_valid='true'),
                       lambda r: r.reverse()):
            rows = copy.deepcopy(self.rows)
            mutate(rows)
            with self.assertRaises(ValueError):
                self.score(rows)

    def test_duplicate_truth_and_empty_interval_rejected(self):
        with self.assertRaises(ValueError):
            self.score([])
        self.manifest['targets'].append(self.manifest['targets'][0])
        with self.assertRaises(ValueError):
            self.score(self.rows)


if __name__ == '__main__':
    unittest.main()
