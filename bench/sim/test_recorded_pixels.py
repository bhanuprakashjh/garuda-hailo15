import math
import pathlib
import sys
import unittest
from types import SimpleNamespace
from dataclasses import dataclass
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from recorded_pixels import HeadingResponse,full_nv12_rgb
from gazebo_vision import rgb_nv12_full
import numpy as np

@dataclass
class Intent:
    command_eligible:bool=True
    forward_vel:float=1.
    yaw_rate:float=0.

class ResponseTests(unittest.TestCase):
    def test_fixed_image_is_absolute_not_cumulative_turn(self):
        response=HeadingResponse(1.2)
        box=dict(x=1100,y=10,w=100,h=100)
        first=response.apply(Intent(),box,0.)
        desired=response.desired
        self.assertGreater(first.yaw_rate,0.)
        settled=response.apply(Intent(),box,desired)
        self.assertEqual(settled.forward_vel,0.)
        self.assertAlmostEqual(settled.yaw_rate,0.)
        self.assertAlmostEqual(response.desired,desired)

    def test_thirty_degree_limit_and_wrap(self):
        response=HeadingResponse(2.)
        response.apply(Intent(),dict(x=1200,y=0,w=80,h=100),3.1)
        self.assertLessEqual(response.desired-3.1,math.pi/6+1e-9)
        result=response.apply(Intent(),dict(x=1200,y=0,w=80,h=100),response.desired-2*math.pi)
        self.assertAlmostEqual(result.yaw_rate,0.)

    def test_invalid_intent_cannot_create_turn(self):
        response=HeadingResponse(1.2)
        self.assertIsNone(response.apply(None,None,0.))
        self.assertIsNone(response.desired)

    def test_display_decode_preserves_neutral_full_range(self):
        for value in (0,114,255):
            pixels=np.full((720,1280,3),value,dtype=np.uint8)
            np.testing.assert_array_equal(full_nv12_rgb(rgb_nv12_full(pixels)),pixels)

    def test_loop_restarts_pixels_while_the_declared_clock_keeps_running(self):
        """A two-frame clip at 1 fps: played once it holds its last frame (vision expires at EOF);
        looped, frame 0 returns at the third period with a new sequence, a later declared time
        and loop count 1, so a loop boundary is a visible cut, never a frozen picture."""
        import hashlib,json,tempfile,time
        from unittest import mock
        from recorded_pixels import ReplayPixels
        with tempfile.TemporaryDirectory() as d:
            size=1280*720*3//2
            frames=b''.join(bytes([v])*size for v in (16,200))
            pathlib.Path(d,'source.nv12').write_bytes(frames)
            pathlib.Path(d,'manifest.json').write_text(json.dumps(dict(canvas=[1280,720],frames=2,source_sha256=hashlib.sha256(frames).hexdigest())))
            world=SimpleNamespace(overview=None)
            for loop in (False,True):
                pixels=ReplayPixels(d,world,1,loop=loop)
                with mock.patch('recorded_pixels.time.monotonic',return_value=100.),mock.patch('recorded_pixels.time.monotonic_ns',return_value=100_000_000_000):
                    pixels.start();first=pixels.snapshot()[0]
                with mock.patch('recorded_pixels.time.monotonic_ns',return_value=102_500_000_000):
                    third=pixels.snapshot()[0]
                self.assertEqual(pixels.raw(first[0])[0],16)          # luma of the exact NV12 bytes the board gets
                if loop:
                    self.assertEqual(pixels.raw(third[0])[0],16,'frame 0 again after the clip wrapped')
                    self.assertEqual((third[0],third[1],pixels.loops),(first[0]+1,2_000_000_000,1))
                else:
                    self.assertEqual(pixels.raw(third[0])[0],200,'last frame held at EOF')
                    self.assertEqual((third[1],pixels.loops),(1_000_000_000,0))

    def test_pause_holds_the_pixels_while_fresh_frames_keep_coming_then_resumes_in_place(self):
        """A looping three-frame clip at 1 fps paused on frame 1: every period still releases a new
        sequence (fresh capture time, the declared clock running) carrying frame 1, so the board keeps
        detecting on a still picture; resume continues with frame 2, not with wherever the clock
        got to. A clip that does not loop cannot be paused (the frozen evidence protocol)."""
        import hashlib,json,tempfile
        from unittest import mock
        from recorded_pixels import ReplayPixels
        with tempfile.TemporaryDirectory() as d:
            size=1280*720*3//2
            frames=b''.join(bytes([v])*size for v in (16,100,200))
            pathlib.Path(d,'source.nv12').write_bytes(frames)
            pathlib.Path(d,'manifest.json').write_text(json.dumps(dict(canvas=[1280,720],frames=3,source_sha256=hashlib.sha256(frames).hexdigest())))
            world=SimpleNamespace(overview=None)
            pixels=ReplayPixels(d,world,1,loop=True)
            def at(seconds):
                return mock.patch.multiple('recorded_pixels.time',monotonic=lambda:100.+seconds,monotonic_ns=lambda:100_000_000_000+int(seconds*1e9))
            with at(0):pixels.start();pixels.snapshot()
            with at(1.2):frame1=pixels.snapshot()[0];pixels.pause()
            self.assertTrue(pixels.paused);self.assertEqual(pixels.raw(frame1[0])[0],100)
            with at(2.2):held=pixels.snapshot()[0]
            with at(3.2):held2=pixels.snapshot()[0]
            self.assertEqual((pixels.raw(held[0])[0],pixels.raw(held2[0])[0]),(100,100),'the pixels hold on frame 1')
            self.assertEqual((held[0],held2[0]),(frame1[0]+1,frame1[0]+2),'a new sequence every period while paused')
            self.assertEqual((held[1],held2[1]),(2_000_000_000,3_000_000_000),'the declared clock keeps running')
            self.assertGreater(held2[2],held[2],'fresh capture times, so the board does not see a stale frame')
            with at(3.7):pixels.resume()
            with at(4.2):after=pixels.snapshot()[0]
            self.assertFalse(pixels.paused);self.assertEqual(pixels.raw(after[0])[0],200,'resume continues with frame 2')
            with at(5.2):self.assertEqual(pixels.raw(pixels.snapshot()[0][0])[0],16,'then wraps as before');self.assertEqual(pixels.loops,1)
            once=ReplayPixels(d,world,1,loop=False)
            with at(0):once.start();once.snapshot();once.pause()
            self.assertFalse(once.paused,'a clip played once for evidence cannot be paused')

if __name__=='__main__':unittest.main()
