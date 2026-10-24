import importlib.util
import math
import json
import os
import pathlib
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hailo_adapter', ROOT / 'hailo_adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
if 'HAILO_DESCRIPTOR' not in os.environ:
    raise unittest.SkipTest('Stage the Hailo adapter and set HAILO_DESCRIPTOR/PYTHONPATH for these tests')
Frame = adapter.load_frame_type(pathlib.Path(os.environ['HAILO_DESCRIPTOR']))


def frame(timestamp=1000000000):
    f = Frame(isp_timestamp_ns=timestamp, frame_width=3840, frame_height=2160)
    d = f.detections.add(label='person', confidence=.8, tracking_id=0)
    d.bbox.xmin, d.bbox.ymin, d.bbox.xmax, d.bbox.ymax = 100, 200, 600, 2100
    return f


class HailoAdapterTests(unittest.TestCase):
    def test_rewind_clears_previous_session_detection(self):
        f=frame(); f.garuda_diagnostics_json=json.dumps(dict(v=1,detector_ran=True,
            source_timestamp_ns=str(f.isp_timestamp_ns),raw=[]))
        s=adapter.State(target_label='all'); s.ingest(f,100)
        self.assertIsNotNone(s.snapshot(101)['last_detection'])
        s.ingest(frame(999),110)
        self.assertIsNone(s.snapshot(111)['last_detection'])
        self.assertIsNone(s.snapshot(111)['last_detection_arrival_age_ms'])

    def test_empty_frames_keep_session_live(self):
        s=adapter.State(target_label='all'); s.ingest(frame(),100)
        session=s.session
        for i in range(1,40):
            f=Frame(isp_timestamp_ns=1000000000+i,frame_width=3840,frame_height=2160)
            s.ingest(f,100+i*30)
        self.assertEqual(s.session,session)
        self.assertTrue(s.snapshot(1271)['metadata_live'])
        self.assertEqual(s.snapshot(1271)['tracks'],[])

    def test_diagnostics_do_not_become_tracks(self):
        f=frame(); f.garuda_diagnostics_json=json.dumps(dict(v=1,detector_ran=True,
            source_timestamp_ns=str(f.isp_timestamp_ns),raw=[dict(label='cell phone',conf=.2,x=.1,y=.2,w=.3,h=.4)]))
        s=adapter.State(target_label='all');s.ingest(f,100)
        out=s.snapshot(101)
        self.assertEqual(out['tracks'][0]['label'],'person')
        self.assertEqual(out['diagnostics']['raw'][0]['x'],384)
        self.assertTrue(out['diagnostics']['aligned'])
        f.isp_timestamp_ns+=1;f.garuda_diagnostics_json='invalid';s.ingest(f,120)
        self.assertTrue(s.snapshot(121)['metadata_live'])
        self.assertIsNotNone(s.snapshot(121)['diagnostic_error'])

    def test_phone_filter_selection_and_latched_loss(self):
        f = frame()
        phone = f.detections.add()
        phone.CopyFrom(f.detections[0]); phone.label = 'cell phone'; phone.tracking_id = 8
        self.assertEqual([t['id'] for t in adapter.decode_tracks(f)[1]], [0])
        s = adapter.State(target_label='cell phone'); s.ingest(f, 100)
        snap = s.snapshot(101)
        self.assertEqual(snap['target_label'], 'cell phone')
        self.assertEqual([t['id'] for t in snap['tracks']], [8])
        s.select(8, s.session, s.sequence, 110)
        self.assertEqual(s.snapshot(111)['selection']['state'], 'selected')
        s.ingest(frame(1000000010), 120)
        self.assertEqual(s.snapshot(121)['selection']['state'], 'lost')
        f.isp_timestamp_ns += 20; s.ingest(f, 130)
        self.assertEqual(s.snapshot(131)['selection']['state'], 'lost')
        self.assertFalse(s.snapshot(131)['lock']['control_valid'])

    def test_exact_id_geometry_and_clock(self):
        f = Frame.FromString(frame().SerializeToString())
        s = adapter.State(); s.ingest(f, 100)
        out = s.snapshot(110)
        self.assertEqual(out['tracks'][0]['id'], 0)
        self.assertEqual(out['tracks'][0]['w'], 500)
        self.assertEqual(out['tracks'][0]['h'], 1900)
        self.assertEqual(out['source_capture_timestamp_ns'], '1000000000')
        self.assertEqual(out['arrival_age_ms'], 10)
        self.assertFalse(out['timestamp_valid'])
        self.assertFalse(out['lock']['control_valid'])
        self.assertFalse(out['image_target']['valid'])

    def test_repeated_source_does_not_refresh(self):
        s = adapter.State(); s.ingest(frame(), 100)
        self.assertFalse(s.ingest(frame(), 350))
        self.assertFalse(s.snapshot(401)['metadata_live'])
        self.assertEqual(s.snapshot(401)['tracks'], [])

    def test_disconnect_clears_immediately(self):
        s = adapter.State(); s.ingest(frame(), 100); s.disconnect('test')
        self.assertEqual(s.snapshot(101)['tracks'], [])
        self.assertEqual(s.snapshot(101)['connection'], 'disconnected')

    def test_reconnect_and_rewind_namespace_ids(self):
        s = adapter.State(); s.ingest(frame(), 100)
        first = s.session; s.reconnect()
        self.assertNotEqual(first, s.session)
        self.assertEqual(s.snapshot(101)['tracks'], [])
        s.ingest(frame(), 102); second = s.session
        s.ingest(frame(999), 103)
        self.assertNotEqual(second, s.session)

    def test_unknown_fields_and_untracked_detections(self):
        f = Frame.FromString(frame().SerializeToString() + b'\xa0\x06\x01')
        f.detections.add(label='face', tracking_id=5)
        f.detections.add(label='person')
        self.assertEqual(len(adapter.decode_tracks(f)[1]), 1)

    def test_bad_boxes_confidence_and_duplicate_ids(self):
        for field, value in [('xmin', math.nan), ('xmax', 4000), ('ymax', -1)]:
            f = frame(); setattr(f.detections[0].bbox, field, value)
            with self.assertRaises(ValueError): adapter.decode_tracks(f)
        f = frame(); f.detections[0].confidence = math.inf
        with self.assertRaises(ValueError): adapter.decode_tracks(f)
        f = frame(); f.detections.add().CopyFrom(f.detections[0])
        with self.assertRaises(ValueError): adapter.decode_tracks(f)

    def test_http_read_only(self):
        s = adapter.State()
        server = ThreadingHTTPServer(('127.0.0.1', 0), adapter.handler(s))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(url + '/api/snapshot') as response:
                self.assertIn(b'garuda.hailo.viewer.v1', response.read())
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url + '/api/control', method='POST'))
            self.assertEqual(error.exception.code, 405)
            self.assertEqual(s.sequence, 0)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_selection_is_not_a_control_lock(self):
        s=adapter.State();s.ingest(frame(),100)
        s.select(0,s.session,s.sequence,110)
        snap=s.snapshot(110)
        self.assertEqual(snap['selection']['state'],'selected')
        self.assertEqual(snap['selection']['id'],0)
        self.assertFalse(snap['lock']['control_valid'])
        self.assertEqual(snap['lock']['state'],'none')

    def test_lost_latches_without_switch_or_automatic_reacquisition(self):
        s=adapter.State();s.ingest(frame(),100);s.select(0,s.session,s.sequence,110)
        other=frame(1000000100);other.detections[0].tracking_id=7;s.ingest(other,120)
        self.assertEqual(s.snapshot(121)['selection']['state'],'lost')
        self.assertEqual(s.snapshot(121)['selection']['id'],0)
        s.ingest(frame(1000000200),130)
        self.assertEqual(s.snapshot(131)['selection']['state'],'lost')
        s.select(0,s.session,s.sequence,132)
        self.assertEqual(s.snapshot(133)['selection']['state'],'selected')
        s.clear_selection();self.assertIsNone(s.snapshot(134)['selection']['id'])

    def test_reconnect_same_id_stays_lost(self):
        s=adapter.State();s.ingest(frame(),100);s.select(0,s.session,s.sequence,110)
        old=s.session;s.reconnect();s.ingest(frame(),120)
        self.assertEqual(s.snapshot(121)['selection']['state'],'lost')
        with self.assertRaises(ValueError):s.select(0,old,s.sequence,122)

    def test_reject_stale_missing_and_invalid_clicks(self):
        s=adapter.State();s.ingest(frame(),100)
        for track,session,sequence,when in [(0,s.session,1,401),(1,s.session,1,110),(0,'old',1,110),(False,s.session,1,110),(0,s.session,999,110)]:
            with self.assertRaises(ValueError):s.select(track,session,sequence,when)
        self.assertIsNone(s.selected)

    def test_gap_latches_loss_even_without_snapshot_poll(self):
        s=adapter.State();s.ingest(frame(),100);s.select(0,s.session,s.sequence,110)
        s.ingest(frame(1000000200),450)
        self.assertEqual(s.snapshot(451)['selection']['state'],'lost')


if __name__ == '__main__':
    unittest.main()
