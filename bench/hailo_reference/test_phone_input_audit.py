"""Offline regression checks for the bounded phone input diagnostic."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from audit_phone_input import BOXES, prepare
from score_phone_input_audit import border_rejected, gray_padding


class PhoneInputAuditTests(unittest.TestCase):
    def test_padding_changes_only_neutral_letterbox_luma(self):
        data = np.full(640*640*3//2, 128, dtype=np.uint8)
        y = data[:640*640].reshape(640, 640)
        y[:140] = 0
        y[500:] = 0
        result = np.frombuffer(gray_padding(data.tobytes(), dict(w=1280, h=720)), dtype=np.uint8)
        out = result[:640*640].reshape(640, 640)
        self.assertTrue(np.all(out[:140] == 114))
        self.assertTrue(np.all(out[500:] == 114))
        np.testing.assert_array_equal(out[140:500], y[140:500])
        np.testing.assert_array_equal(result[640*640:], data[640*640:])

    def test_square_crop_unchanged(self):
        raw = bytes([37])*(640*640*3//2)
        self.assertEqual(gray_padding(raw, dict(w=320, h=320)), raw)

    def test_wrong_padding_or_size_refused(self):
        for raw in (b'', bytes([37])*(640*640*3//2)):
            with self.assertRaises(ValueError):
                gray_padding(raw, dict(w=1280, h=720))

    def test_interior_boundary_reproduces_frame12(self):
        r = dict(x=0, y=288, w=768, h=432, source_w=1280, source_h=720, full_frame=False)
        box = [630.6883392333984, 305.6876220703125, 677.6748504638672, 399.8839416503906]
        d = dict(x1=box[0]/768, x2=box[2]/768,
                 y1=((box[1]-288)*640/768+140)/640,
                 y2=((box[3]-288)*640/768+140)/640)
        self.assertTrue(border_rejected(r, d, .08))
        self.assertFalse(border_rejected(r, d, .015))
        r['full_frame'] = True
        self.assertFalse(border_rejected(r, d, .08))

    def fixture(self, directory, corrupt=False):
        source, metadata = directory/'source', directory/'metadata'
        source.mkdir()
        metadata.mkdir()
        for i in BOXES:
            raw = bytes([i])*(1280*720*3//2)
            (source/f'{i:06d}.source.nv12').write_bytes(raw)
            m = dict(source_image=dict(sha256='bad' if corrupt else hashlib.sha256(raw).hexdigest()),
                     target_roi=dict(region=None if i == 7 else dict(x=0, y=0, w=640, h=640)),
                     isp_timestamp_ns=i+1, isp_ae_integration_time=33006)
            (metadata/f'{i:06d}.json').write_text(json.dumps(m))
        return source, metadata

    def test_prepare_bounded_order_and_alignment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, metadata = self.fixture(root)
            rows = prepare(source, metadata, root/'output')
            self.assertEqual(len(rows), 31)
            self.assertEqual([r['source_frame'] for r in rows if r['method'] == 'full'], list(BOXES))
            self.assertTrue(all(all(r[k] % 2 == 0 for k in ('x', 'y', 'w', 'h')) for r in rows))
            self.assertEqual((root/'output'/'source.nv12').stat().st_size, 31*1280*720*3//2)
            with self.assertRaises(FileExistsError):
                prepare(source, metadata, root/'output')

    def test_prepare_refuses_pixel_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, metadata = self.fixture(root, corrupt=True)
            with self.assertRaisesRegex(ValueError, 'provenance'):
                prepare(source, metadata, root/'output')

    def test_rectangular_network_and_invalid_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source,metadata=self.fixture(root)
            rows=prepare(source,metadata,root/'rect',(1024,576))
            self.assertTrue(all((r['network_w'],r['network_h'])==(1024,576) for r in rows))
            for dims in ((1024,577),(0,640),(2048,640)):
                with self.assertRaisesRegex(ValueError,'network size'):
                    prepare(source,metadata,root/'invalid',dims)


if __name__ == '__main__':
    unittest.main()
