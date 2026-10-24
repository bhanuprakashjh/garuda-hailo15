"""Deterministic tests for the MOT conversion and lock-scoring logic."""
import unittest

import mot_to_replay
from score_lock_replay import iou, judge, outages, score


def truth(seq, target=None, others=(), dropped=False):
    return dict(sequence=seq, capture_ms=seq*100.0, target=target,
                others=list(others), dropped=dropped)


def box(x=0.4, y=0.4, w=0.2, h=0.3, visibility=1.0):
    return dict(x=x, y=y, w=w, h=h, visibility=visibility)


def output(seq, state='tracking', valid=True, b=None):
    return {'v': 2, 'sequence': seq, 'frame': {'width': 1000, 'height': 1000},
            'lock': {'state': state, 'control_valid': valid,
                     'box': None if b is None else
                     {'x': b['x']*1000, 'y': b['y']*1000, 'w': b['w']*1000, 'h': b['h']*1000}}}


class ConversionTests(unittest.TestCase):
    def test_visibility_is_confidence_and_floor_drops(self):
        info = dict(width=1000, height=500, rate=10.0, length=3)
        pixel = dict(x=400.0, y=200.0, w=200.0, h=150.0, visibility=0.6, label='person')
        d = mot_to_replay.to_detection(pixel, info, 0.25)
        self.assertAlmostEqual(d['confidence'], 0.6)
        self.assertEqual(d['label'], 'person')
        self.assertAlmostEqual(d['box']['x'], 0.4)
        self.assertAlmostEqual(d['box']['y'], 0.4)
        self.assertAlmostEqual(d['box']['w'], 0.2)
        self.assertAlmostEqual(d['box']['h'], 0.3)
        self.assertIsNone(mot_to_replay.to_detection(dict(pixel, visibility=0.1), info, 0.25))

    def test_drop_window_half_open(self):
        self.assertTrue(mot_to_replay.in_window(2.0, [(2.0, 3.0)]))
        self.assertFalse(mot_to_replay.in_window(3.0, [(2.0, 3.0)]))

    def test_camera_motion_is_median_shift_excluding_target(self):
        info = dict(width=1000, height=500)
        def b(gid, x, y):
            return dict(gid=gid, x=x, y=y, w=10, h=10)
        prev = [b(1, 100, 100), b(2, 200, 100), b(3, 300, 100), b(9, 400, 100)]
        cur = [b(1, 110, 105), b(2, 210, 105), b(3, 312, 105), b(9, 600, 300)]   # gid 9 = target walks
        m = mot_to_replay.camera_motion(prev, cur, info, exclude_gid=9)
        self.assertAlmostEqual(m['dx'], 0.010)
        self.assertAlmostEqual(m['dy'], 0.010)
        self.assertTrue(m['valid'])
        self.assertIsNone(mot_to_replay.camera_motion(prev[:2], cur[:2], info))   # too few objects

    def test_visdrone_rows_map_category_and_occlusion(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'annotations').mkdir()
            (root/'sequences'/'seq').mkdir(parents=True)
            (root/'annotations'/'seq.txt').write_text(
                '1,7,10,20,30,40,1,1,0,0\n'    # pedestrian, unoccluded
                '1,8,50,60,30,40,1,2,0,1\n'    # people, partial occlusion
                '1,9,90,60,30,40,1,4,0,2\n'    # car, heavy occlusion
                '1,10,90,60,30,40,0,1,0,0\n'   # score 0: ignored
                '2,11,90,60,30,40,1,7,0,0\n')  # tricycle: unmapped
            gt = mot_to_replay.read_visdrone_gt(root/'sequences'/'seq')
            self.assertEqual([(b['gid'], b['label'], b['visibility']) for b in gt[1]],
                             [(7, 'person', 1.0), (8, 'person', 0.6), (9, 'car', 0.2)])
            self.assertNotIn(2, gt)


class JudgeTests(unittest.TestCase):
    def test_verdicts(self):
        t = truth(1, target=box(), others=[box(x=0.0, y=0.0)])
        self.assertEqual(judge(box(), t), 'correct')
        self.assertEqual(judge(box(x=0.0, y=0.0), t), 'wrong_identity')
        self.assertEqual(judge(box(x=0.8, y=0.8, w=0.1, h=0.1), t), 'unmatched')
        self.assertEqual(judge(None, t), 'no_box')

    def test_iou_disjoint_and_identical(self):
        self.assertAlmostEqual(iou(box(), box()), 1.0)
        self.assertEqual(iou(box(), box(x=0.9, y=0.9, w=0.05, h=0.05)), 0.0)


class OutageTests(unittest.TestCase):
    def test_spans_from_absence_visibility_and_drops(self):
        rows = [truth(1, box()), truth(2, None), truth(3, box(visibility=0.1)),
                truth(4, box()), truth(5, box(), dropped=True), truth(6, box())]
        self.assertEqual(outages(rows), [(1, 3), (4, 5)])


class ScoreTests(unittest.TestCase):
    def test_reacquire_latency_and_identity(self):
        rows = [truth(1, box()), truth(2, box()), truth(3, None),
                truth(4, None), truth(5, box()), truth(6, box())]
        outs = [output(1, b=box()), output(2, b=box()),
                output(3, 'coasting', False, box()), output(4, 'lost', False, None),
                output(5, 'lost', False, None), output(6, 'tracking', True, box())]
        s = score(outs, rows)
        self.assertEqual(s['wrong_identity_frames'], 0)
        self.assertEqual(len(s['outages']), 1)
        o = s['outages'][0]
        self.assertTrue(o['reacquired'])
        self.assertFalse(o['wrong_identity'])
        self.assertAlmostEqual(o['latency_ms'], 100.0)  # back at seq5, valid at seq6

    def test_wrong_identity_reacquire_is_flagged(self):
        rows = [truth(1, box(), others=[box(x=0.0, y=0.0)]), truth(2, None),
                truth(3, box(), others=[box(x=0.0, y=0.0)])]
        outs = [output(1, b=box()), output(2, 'lost', False, None),
                output(3, 'tracking', True, box(x=0.0, y=0.0))]
        s = score(outs, rows)
        self.assertEqual(s['wrong_identity_frames'], 1)
        self.assertTrue(s['outages'][0]['wrong_identity'])
        self.assertFalse(s['outages'][0]['reacquired'])


if __name__ == '__main__':
    unittest.main()
