import unittest
import numpy as np
from float_input_check import rgb_from_nv12

class ConversionTests(unittest.TestCase):
    def test_neutral_chroma(self):
        data = bytes([128])*(640*640*3//2)
        for mode in ('601_limited', '709_limited', 'sdk_full'):
            rgb = rgb_from_nv12(data, mode)
            self.assertEqual(rgb.shape, (640, 640, 3))
            self.assertEqual(rgb.dtype, np.uint8)
            self.assertTrue(np.array_equal(rgb[:, :, 0], rgb[:, :, 1]))
            self.assertTrue(np.array_equal(rgb[:, :, 1], rgb[:, :, 2]))
        self.assertTrue((rgb_from_nv12(data, 'sdk_full') == 128).all())

    def test_limited_black(self):
        data = bytes([16])*(640*640)+bytes([128])*(640*320)
        self.assertTrue((rgb_from_nv12(data, '601_limited') == 0).all())
        self.assertTrue((rgb_from_nv12(data, '709_limited') == 0).all())

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            rgb_from_nv12(bytes(10), 'sdk_full')

if __name__ == '__main__':
    unittest.main()
