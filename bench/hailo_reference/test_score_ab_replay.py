"""Deterministic tests for the A/B sequence scorer's pure aggregation logic."""
import unittest

from score_ab_replay import gap_lengths, paired, summarize


def row(frame, phone, person=0.9, wait=100.0):
    return dict(frame=frame, phone=phone, person=person, wait_ms=wait, tiles=5)


class GapTests(unittest.TestCase):
    def test_gap_lengths(self):
        self.assertEqual(gap_lengths([True, False, False, True, False]), [2, 1])
        self.assertEqual(gap_lengths([False, False]), [2])
        self.assertEqual(gap_lengths([True, True]), [])
        self.assertEqual(gap_lengths([]), [])


class SummarizeTests(unittest.TestCase):
    def test_rates_gaps_and_waits(self):
        series = [row(1, 0.6, wait=90), row(3, 0.2, wait=110),
                  row(5, 0.0, wait=100), row(7, 0.1, wait=100)]
        s = summarize(series)
        self.assertEqual(s['frames'], 4)
        self.assertEqual(s['phone']['0.15']['detected'], 2)
        self.assertEqual(s['phone']['0.15']['max_gap'], 2)
        self.assertEqual(s['phone']['0.5']['detected'], 1)
        self.assertEqual(s['person']['0.5']['rate'], 1.0)
        self.assertEqual(s['phone']['conf_on_hits']['median'], 0.4)
        self.assertEqual(s['frame_wait_ms']['median'], 100.0)
        self.assertEqual(s['frame_wait_ms']['max'], 110.0)

    def test_no_hits_has_null_confidence(self):
        s = summarize([row(1, 0.0), row(3, 0.05)])
        self.assertIsNone(s['phone']['conf_on_hits']['mean'])
        self.assertEqual(s['phone']['0.15']['detected'], 0)
        self.assertEqual(s['phone']['0.15']['max_gap'], 2)


class PairedTests(unittest.TestCase):
    def test_disagreement_counts(self):
        a = [row(1, 0.6), row(3, 0.0), row(5, 0.3), row(7, 0.0)]
        b = [row(1, 0.6), row(3, 0.4), row(5, 0.0), row(7, 0.0)]
        p = paired(a, b)
        self.assertEqual(p['phone']['0.15'],
                         dict(a_only=1, b_only=1, both=1, neither=1))
        self.assertEqual(p['phone']['0.5'],
                         dict(a_only=0, b_only=0, both=1, neither=3))

    def test_frame_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            paired([row(1, 0.5)], [row(2, 0.5)])


if __name__ == '__main__':
    unittest.main()
