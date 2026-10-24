"""Baseline tamper and exact-source qualification gates; no board required."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'bench'), str(ROOT/'hosts/hailo15l')]
from freeze_baseline import verify, allowed
from qualify_capture import qualify


class QualificationTests(unittest.TestCase):
    def capture(self, root):
        def save(name, value):
            (root/name).write_text(json.dumps(value))
        producer = ['camera','stream','boot']
        save('request.json', dict(recording_id='test', frames=1))
        save('summary.json', dict(complete=True, frames=1, paired_frames=1, producer=producer))
        save('end.json', dict(complete=True, recording_id='test', sent=1))
        data = b'abcdef'
        sha = hashlib.sha256(data).hexdigest()
        meta = dict(recording_id='test', sample_index=0, input_w=2, input_h=2,
                    pixel_format='NV12', packed_stride=2, nv12_sha256=sha,
                    source_id='camera', stream_id='stream', clock_domain='boot',
                    isp_timestamp_ns=1000000000, frame=dict(sequence=1,capture_ms=1000),
                    output=dict(sequence=1,capture_monotonic_ms=1000,frame=dict(width=2,height=2)),
                    source_image=dict(width=2,height=2,pixel_format='NV12',packed_stride=2,
                                      byte_offset=6,byte_length=6,isp_timestamp_ns=1000000000,sha256=sha))
        save('000000.json', meta)
        (root/'000000.nv12').write_bytes(data)
        (root/'000000.source.nv12').write_bytes(data)
        return meta

    def test_complete_capture_is_not_accuracy_qualification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.capture(root)
            result=qualify(root)
            self.assertTrue(result['integrity_pass'])
            self.assertFalse(result['tracking_accuracy_qualified'])
            self.assertEqual(result['source_elapsed_ms'],0)
            self.assertIsNone(result['capture_interval_ms_max'])
            self.assertEqual(result['pixel_bytes'],12)

    def test_sample_interval_and_gaps_are_reported_not_sensor_drops(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta=self.capture(root)
            for name,key in [('request.json','frames'),('summary.json','frames'),('end.json','sent')]:
                path=root/name;data=json.loads(path.read_text());data[key]=2
                if name=='summary.json':data['paired_frames']=2
                path.write_text(json.dumps(data))
            meta['sample_index']=1;meta['frame'].update(sequence=4,capture_ms=1100)
            meta['output'].update(sequence=4,capture_monotonic_ms=1100)
            meta['isp_timestamp_ns']=1_100_000_000
            meta['source_image']['isp_timestamp_ns']=1_100_000_000
            (root/'000001.json').write_text(json.dumps(meta))
            for suffix in ['.nv12','.source.nv12']:
                (root/('000001'+suffix)).write_bytes(b'abcdef')
            result=qualify(root)
            self.assertEqual(result['source_elapsed_ms'],100)
            self.assertEqual(result['capture_interval_ms_max'],100)
            self.assertEqual(result['unrecorded_tracker_sequence_ids'],2)
            self.assertIn('NOT a measured sensor-drop',result['sampling_scope'])

    def test_corrupt_pixels_and_incomplete_recordings_fail(self):
        for name in ('000000.nv12','000000.source.nv12','end.json','summary.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root=Path(d);self.capture(root)
                (root/name).write_bytes(b'bad')
                with self.assertRaises((ValueError,KeyError)):
                    qualify(root)

    def test_wrong_exposure_and_output_sequence_fail(self):
        for wrong_source in (True,False):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);meta=self.capture(root)
                if wrong_source:meta['source_image']['isp_timestamp_ns']+=1
                else:meta['output']['sequence']+=1
                (root/'000000.json').write_text(json.dumps(meta))
                with self.assertRaises(ValueError):qualify(root)

    def test_baseline_tamper_and_path_escape_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'binary').write_bytes(b'good')
            entry=dict(local='binary',bytes=4,sha256=hashlib.sha256(b'good').hexdigest())
            manifest=dict(schema='garuda.deployed-baseline.v1',files=[entry])
            (root/'manifest.json').write_text(json.dumps(manifest));verify(root)
            (root/'binary').write_bytes(b'evil')
            with self.assertRaises(ValueError):verify(root)
            entry['local']='../binary'
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):verify(root)
        for path in ('/etc/passwd','/opt/garuda-fresh/../secret'):
            with self.assertRaises(ValueError):allowed(path)


if __name__ == '__main__':unittest.main()
