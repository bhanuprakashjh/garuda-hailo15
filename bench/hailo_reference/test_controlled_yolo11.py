import unittest
import numpy as np
from PIL import Image
from build_controlled_yolo11 import packed_full_nv12
from score_controlled_yolo11 import exact_rgb, nms

class ControlledInputTests(unittest.TestCase):
    def test_neutral_packing_and_conversion(self):
        packed=packed_full_nv12(Image.new('RGB',(640,640),(128,128,128)))
        self.assertEqual(packed.shape,(320,640,3))
        self.assertTrue((packed==128).all())
        self.assertTrue((exact_rgb(packed.tobytes())==128).all())

    def test_constant_color_roundtrip(self):
        for color in ((200,60,40),(30,170,220)):
            packed=packed_full_nv12(Image.new('RGB',(640,640),color))
            rgb=exact_rgb(packed.tobytes())
            self.assertLess(np.max(np.abs(rgb-np.array(color))),2)

    def test_no_hidden_clipping(self):
        raw=bytes([255])*(640*640)+bytes([255])*(640*320)
        self.assertGreater(exact_rgb(raw).max(),255)

    def test_nms_keeps_strongest(self):
        ds=[dict(x1=0,y1=0,x2=1,y2=1,score=s) for s in (.2,.8)]
        self.assertEqual([d['score'] for d in nms(ds)],[.8])

if __name__=='__main__':
    unittest.main()
