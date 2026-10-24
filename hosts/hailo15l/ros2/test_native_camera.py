import json
from pathlib import Path
import socket
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(Path(__file__).parent), str(ROOT/'services/garuda-follow'),
               str(ROOT/'services/garuda-follow/tests')]
from test_fresh_follow import envelope
from native_camera import LocalCameraGate, read_packet, camera_request_bound, camera_response_heading
import math

MS = 1_000_000


class NativeCameraTests(unittest.TestCase):
    def row(self):
        return dict(envelope(), source_id='hailo15l.imx678', clock_domain='linux.monotonic:boot1')

    def test_request_bound_to_exact_selection_and_producer(self):
        row=self.row()
        self.assertTrue(camera_request_bound(row,row))
        for other in (dict(row,stream_id='other'),dict(row,source_id='other'),
                      dict(row,lock=dict(row['lock'],epoch=2)),dict(row,lock=dict(row['lock'],id=2)),{}):
            self.assertFalse(camera_request_bound(row,other))

    def test_absolute_camera_response_no_cumulative_turn(self):
        row=self.row();source=dict(heading_reference_ned=1.,camera_hfov=2.7)
        angles=[camera_response_heading(row,source) for _ in range(100)]
        self.assertEqual(len(set(angles)),1)
        self.assertLessEqual(abs(angles[0]-1.),math.pi/6)
        for key in ('heading_reference_ned','camera_hfov'):
            self.assertIsNone(camera_response_heading(row,dict(source,**{key:float('nan')})))

    def test_same_board_age_charged_once(self):
        gate = LocalCameraGate('linux.monotonic:boot1')
        self.assertTrue(gate.ingest(self.row(), 1030*MS))
        status = gate.status(1040*MS)
        self.assertEqual(status['observation_age_ms'], 40)
        self.assertEqual(status['expires_ns'], 1200*MS)
        self.assertFalse(status['vehicle_io'])

    def test_silent_feed_expires_without_new_packet(self):
        gate = LocalCameraGate('linux.monotonic:boot1')
        gate.ingest(self.row(), 1030*MS)
        self.assertTrue(gate.status(1199*MS)['would_be_fresh'])
        self.assertFalse(gate.status(1200*MS)['would_be_fresh'])

    def test_future_or_other_boot_cannot_rebase(self):
        for edit in (dict(clock_domain='linux.monotonic:other'), dict(sample_monotonic_ms=1040),
                     dict(source_id='other'), dict(capture_monotonic_ms=float('nan'))):
            gate = LocalCameraGate('linux.monotonic:boot1')
            gate.ingest(self.row(), 1030*MS)
            self.assertFalse(gate.ingest(dict(self.row(), **edit), 1031*MS))
            self.assertFalse(gate.status(1032*MS)['would_be_fresh'])

    def test_cached_packet_does_not_renew(self):
        gate = LocalCameraGate('linux.monotonic:boot1')
        gate.ingest(self.row(), 1030*MS)
        gate.ingest(self.row(), 1190*MS)
        self.assertEqual(gate.status(1191*MS)['expires_ns'], 1200*MS)
        self.assertFalse(gate.status(1201*MS)['would_be_fresh'])

    def test_framed_native_json_and_ignored_jpeg(self):
        a, b = socket.socketpair()
        try:
            data = json.dumps(self.row()).encode()
            a.sendall(struct.pack('!cI', b'J', 3)+b'jpg'+struct.pack('!cI', b'S', len(data))+data)
            self.assertIsNone(read_packet(b))
            self.assertEqual(read_packet(b), self.row())
        finally:
            a.close(); b.close()

    def test_oversize_rejected_before_allocation(self):
        a, b = socket.socketpair()
        try:
            a.sendall(struct.pack('!cI', b'S', 512*1024+1))
            with self.assertRaises(ValueError):
                read_packet(b)
        finally:
            a.close(); b.close()


if __name__ == '__main__':
    unittest.main()
