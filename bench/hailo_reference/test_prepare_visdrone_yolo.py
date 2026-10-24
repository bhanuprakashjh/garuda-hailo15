import unittest

from prepare_visdrone_yolo import COCO, VISDRONE_TO_COCO, convert_rows


class ConvertRowsTests(unittest.TestCase):
    def test_mapping_and_dropping(self):
        rows = [
            '10,20,30,40,1,1,0,0',      # pedestrian -> person
            '10,20,30,40,1,2,0,0',      # people -> person
            '0,0,50,50,1,4,0,0',        # car
            '0,0,50,50,1,5,0,0',        # van -> car
            '5,5,10,10,1,10,0,0',       # motor -> motorcycle
            '5,5,10,10,1,9,0,0',        # bus
            '5,5,10,10,1,6,0,0',        # truck
            '5,5,10,10,1,7,0,0',        # tricycle dropped
            '5,5,10,10,1,8,0,0',        # awning-tricycle dropped
            '5,5,10,10,0,1,0,0',        # score 0 (ignored region) dropped
            '5,5,10,10,1,0,0,0',        # category 0 dropped
            '5,5,10,10,1,11,0,0',       # others dropped
            '5,5,0,10,1,1,0,0',         # degenerate dropped
        ]
        boxes, dropped = convert_rows(rows, 100, 200)
        self.assertEqual(dropped, 6)
        self.assertEqual([b[0] for b in boxes], [0, 0, 2, 2, 3, 5, 7])
        self.assertEqual([COCO[b[0]] for b in boxes][:5], ['person', 'person', 'car', 'car', 'motorcycle'])
        c, cx, cy, w, h = boxes[0]
        self.assertAlmostEqual(cx, 25 / 100); self.assertAlmostEqual(cy, 40 / 200)
        self.assertAlmostEqual(w, 30 / 100); self.assertAlmostEqual(h, 40 / 200)

    def test_boxes_are_clipped_to_the_image(self):
        boxes, dropped = convert_rows(['90,190,30,40,1,4,0,0', '-10,-10,15,15,1,1,0,0', '99.5,0,10,10,1,1,0,0'], 100, 200)
        self.assertEqual(dropped, 1, 'a box with under 1 px inside the image is dropped')
        c, cx, cy, w, h = boxes[0]
        self.assertAlmostEqual(cx, 95 / 100); self.assertAlmostEqual(w, 10 / 100); self.assertAlmostEqual(h, 10 / 200)
        self.assertTrue(all(0 <= v <= 1 for b in boxes for v in b[1:]))
        self.assertEqual(sorted(set(VISDRONE_TO_COCO.values())), [0, 1, 2, 3, 5, 7])


if __name__ == '__main__':
    unittest.main()
