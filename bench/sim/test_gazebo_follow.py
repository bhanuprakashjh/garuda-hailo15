import json
import pathlib
import sys
import threading
import unittest
import urllib.request
import urllib.error
import shutil
import subprocess
import tempfile
import time
from dataclasses import replace
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gazebo_vision import rgb_nv12, rgb_nv12_full, depth_range, rgb_message, ingress_envelope, NativeNv12
from gazebo_follow import guarded_intent, Runtime
from follow_authority import CommandIntent
from gazebo_console import serve


class PixelTests(unittest.TestCase):
    def test_black_and_white_are_video_range(self):
        for rgb, y in ((0, 16), (255, 235)):
            raw = rgb_nv12(np.full((2, 2, 3), rgb, dtype=np.uint8))
            self.assertEqual(raw, bytes([y]*4+[128, 128]))

    def test_chroma_is_uv_not_vu(self):
        raw = rgb_nv12(np.tile(np.array([255, 0, 0], dtype=np.uint8), (2, 2, 1)))
        self.assertEqual(raw, bytes([82]*4+[90, 240]))

    def test_bad_shape_rejected(self):
        with self.assertRaises(ValueError):
            rgb_nv12(np.zeros((3, 2, 3), dtype=np.uint8))

    def test_depth_invalid_and_background_spread(self):
        box = dict(x=10, y=10, w=50, h=100)
        depth = np.full((720, 1280), 7., dtype=np.float32)
        self.assertEqual(depth_range(depth, box), 7.)
        depth[::2] = 20
        self.assertIsNone(depth_range(depth, box))
        depth[:] = np.nan
        self.assertIsNone(depth_range(depth, box))
        self.assertIsNone(depth_range(None, box))

    def test_reenvelope_counts_measured_duration_once(self):
        board = dict(capture_monotonic_ms=10000., publish_monotonic_ms=10065.,
                     lock=dict(obs_age_ms=65.))
        out = ingress_envelope(board, 1_000_000_000, 1_140_000_000, 'test')
        self.assertEqual(out['age_ms'], 140.)
        self.assertEqual(out['lock']['obs_age_ms'], 140.)
        self.assertEqual(out['valid_for_ms'], 60.)
        self.assertEqual(board['lock']['obs_age_ms'], 65.)

    def test_older_observation_is_not_refreshed_by_transport(self):
        board = dict(capture_monotonic_ms=10000., publish_monotonic_ms=10065.,
                     lock=dict(obs_age_ms=300.))
        out = ingress_envelope(board, 1_000_000_000, 1_140_000_000, 'test')
        self.assertEqual(out['lock']['obs_age_ms'], 375.)
        self.assertEqual(out['valid_for_ms'], 0.)
        with self.assertRaises(ValueError):
            ingress_envelope(board, 1_000_000_000, 1_001_000_000, 'test')


class GateTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000_000
        self.intent = CommandIntent(self.now, 100_000_000, 'ACTIVE', 'verified', 1, 1,
                                    0., 0., .1, True, 'live')
        self.result = dict(ingress_ns=self.now-20_000_000, sim_ns=500_000_000,
                           depth_paired=True, range_m=8.)
        self.clock = (550_000_000, self.now-10_000_000)

    def gate(self, **changes):
        return guarded_intent(changes.get('intent', self.intent), changes.get('result', self.result),
                              changes.get('clock', self.clock), self.now, changes.get('follow', True))

    def test_valid_exact_depth_drives_bounded_forward(self):
        self.assertEqual(self.gate().forward_vel, 1.)

    def test_missing_depth_is_yaw_only(self):
        self.assertEqual(self.gate(result=dict(self.result, depth_paired=False)).forward_vel, 0.)

    def test_stale_result_never_drives(self):
        self.assertIsNone(self.gate(result=dict(self.result, ingress_ns=self.now-200_000_000)))

    def test_physical_source_age_and_clock_both_required(self):
        live=dict(self.result,live_camera=True,age_ms=190,received_ns=self.now-10_000_000)
        self.assertIsNone(self.gate(result=live))
        for age in (-100,float('nan'),float('inf')):
            self.assertIsNone(self.gate(result=dict(live,age_ms=age)))
        live['age_ms']=100
        self.assertIsNone(self.gate(result=live,clock=(1,self.now-200_000_000)))
        # Camera and Gazebo clocks are independent, but both must be fresh.
        self.assertIsNotNone(self.gate(result=live,clock=(1,self.now)))

    def test_physical_camera_cannot_borrow_simulated_depth(self):
        live=dict(self.result,live_camera=True,age_ms=100,received_ns=self.now)
        self.assertEqual(self.gate(result=live).forward_vel,0)

    def test_stalled_or_reset_clock_never_drives(self):
        self.assertIsNone(self.gate(clock=(550_000_000, self.now-200_000_000)))
        self.assertIsNone(self.gate(clock=(1, self.now)))
        self.assertIsNone(self.gate(clock=(900_000_000, self.now)))

    def test_hold_ambiguous_and_expired_never_drive(self):
        self.assertIsNone(self.gate(follow=False))
        self.assertIsNone(self.gate(intent=replace(self.intent, command_eligible=False)))
        self.assertIsNone(self.gate(intent=replace(self.intent, ttl_ns=0)))

    def test_turning_has_no_forward_speed(self):
        self.assertEqual(self.gate(intent=replace(self.intent, yaw_rate=.3)).forward_vel, 0.)


@unittest.skipUnless(shutil.which('c++'), 'native pixel adapter requires the host C++ compiler')
class NativePixelTests(unittest.TestCase):
    def test_native_matches_reference_bytes(self):
        with tempfile.TemporaryDirectory(prefix='garuda-pixel-test-') as directory:
            output = pathlib.Path(directory)/'pixels.so'
            subprocess.run(['c++', '-O3', '-shared', '-fPIC', '-std=c++17',
                str(pathlib.Path(__file__).with_name('rgb_nv12.cpp')), '-o', str(output)], check=True)
            native = NativeNv12(str(output))
            rng = np.random.default_rng(42)
            for h, w in ((2, 2), (12, 34), (720, 1280)):
                pixels = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
                self.assertEqual(native(pixels), rgb_nv12(pixels))
                self.assertEqual(NativeNv12(str(output),'sdk_full')(pixels),rgb_nv12_full(pixels))
            with self.assertRaises(ValueError):
                native(np.zeros((3, 2, 3), dtype=np.uint8))

    def test_full_range_black_white(self):
        for value in (0,255):
            self.assertEqual(rgb_nv12_full(np.full((2,2,3),value,dtype=np.uint8)),bytes([value]*4+[128,128]))


class ConsoleTests(unittest.TestCase):
    def test_physical_preview_never_falls_back_to_gazebo(self):
        runtime=Runtime(None);runtime.pixel_source='Physical IMX678'
        self.assertIsNone(runtime.image('/frame.jpg',-1))
        runtime.result=dict(jpeg=b'physical')
        self.assertEqual(runtime.image('/frame.jpg',-1),b'physical')

    def test_expired_request_is_not_displayed_as_follow(self):
        class Pixels:
            overview=None
            def snapshot(self):return None,None,None,None
        runtime=Runtime(Pixels());runtime.command='FOLLOW';runtime.follow_enabled=True
        runtime.control_deadline_ns=time.monotonic_ns()-1
        self.assertEqual(runtime.state()['command'],'HOLD')
        self.assertTrue(runtime.state()['follow_enabled'])
        runtime.control_deadline_ns=time.monotonic_ns()+100_000_000
        self.assertTrue(runtime.state()['control_request_fresh'])
        self.assertGreater(runtime.state()['control_request_remaining_ms'],0)
        self.assertLessEqual(runtime.state()['control_request_remaining_ms'],100)

    def test_request_validation(self):
        runtime = Runtime(None)
        with self.assertRaises(ValueError):
            runtime.action(dict(action='select', sequence=1, x=0, y=0))
        with self.assertRaises(ValueError):
            runtime.action(dict(action='arm_physical_drone'))
        runtime.action(dict(action='hold'))
        self.assertEqual(runtime.requests.get_nowait(), dict(action='hold'))
        runtime.action(dict(action='takeoff'))
        runtime.action(dict(action='land'))
        self.assertEqual(runtime.requests.get_nowait(), dict(action='land'))
        self.assertTrue(runtime.requests.empty())

    def test_loopback_origin_gate_and_hold_route(self):
        runtime = Runtime(None)
        # Fixed high test port, matches the production Host guard.
        server = serve(runtime, 18109)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = 'http://127.0.0.1:18109/api/action'
            for route, mime in (('/', 'text/html'),('/follow_console.js', 'text/javascript')):
                with urllib.request.urlopen('http://127.0.0.1:18109'+route, timeout=2) as response:
                    self.assertEqual(response.status,200)
                    self.assertIn(mime,response.headers['Content-Type'])
                    self.assertGreater(len(response.read()),100)
            body = json.dumps(dict(action='hold')).encode()
            for origin in ('https://evil.invalid', None):
                headers = {'Origin': origin} if origin else {}
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=2)
                self.assertEqual(ctx.exception.code, 403)
            with urllib.request.urlopen(urllib.request.Request(url, body,
                    {'Origin': 'http://127.0.0.1:18109'}), timeout=2) as response:
                self.assertEqual(response.status, 202)
            self.assertEqual(runtime.requests.get_nowait()['action'], 'hold')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
