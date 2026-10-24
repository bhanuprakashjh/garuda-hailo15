import unittest
from score_4k_tiles import iou, map_box, nms

class TileGeometryTests(unittest.TestCase):
    def test_full_view_inverse_padding(self):
        region = dict(x=0, y=0, w=3840, h=2160)
        d = dict(x1=0, y1=140/640, x2=1, y2=500/640)
        self.assertEqual(map_box(region, d), [0, 0, 3840, 2160])

    def test_native_crop_offset(self):
        region = dict(x=512, y=1024, w=640, h=640)
        d = dict(x1=0, y1=0, x2=1, y2=1)
        self.assertEqual(map_box(region, d), [512, 1024, 1152, 1664])

    def test_padding_only_rejected(self):
        region = dict(x=0, y=0, w=3840, h=2160)
        self.assertIsNone(map_box(region, dict(x1=0, y1=0, x2=1, y2=.1)))

    def test_class_aware_merge(self):
        ds = [dict(class_id=c, score=s, box=[0, 0, 10, 10])
              for c, s in ((0, .9), (0, .5), (1, .4))]
        self.assertEqual([d['score'] for d in nms(ds)], [.9, .4])
        self.assertEqual(iou(ds[0]['box'], ds[0]['box']), 1)

if __name__ == '__main__':
    unittest.main()
