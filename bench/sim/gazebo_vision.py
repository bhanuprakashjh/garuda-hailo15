"""Bench-only pixels in/out. No actor poses, ground truth, or vehicle commands."""
import io
import json
import queue
import select
import subprocess
import threading
import time
import uuid
import os
import ctypes
from collections import OrderedDict

import numpy as np
from PIL import Image


class NativeNv12:
    def __init__(self, path, color='601_limited'):
        if color not in ('601_limited','sdk_full'):raise ValueError('unknown colour conversion')
        self.library = ctypes.CDLL(path)
        self.function = self.library.garuda_rgb_nv12 if color=='601_limited' else self.library.garuda_rgb_nv12_full
        self.function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.function.restype = ctypes.c_int

    def __call__(self, rgb):
        h, w, channels = rgb.shape
        if channels != 3 or rgb.dtype != np.uint8 or not rgb.flags.c_contiguous:
            raise ValueError('contiguous RGB8 required')
        output = np.empty(h*w*3//2, dtype=np.uint8)
        if self.function(rgb.ctypes.data, output.ctypes.data, w, h):
            raise ValueError('invalid native NV12 conversion shape')
        return output.tobytes()


def rgb_nv12(rgb):
    """RGB8 to BT.601 limited-range NV12, 2x2 averaged chroma; no resize/crop."""
    h, w, channels = rgb.shape
    if channels != 3 or h % 2 or w % 2 or rgb.dtype != np.uint8:
        raise ValueError("even RGB8 dimensions required")
    p = rgb.astype(np.int32)
    r, g, b = p[:, :, 0], p[:, :, 1], p[:, :, 2]
    y = ((66*r + 129*g + 25*b + 128) >> 8) + 16
    u = ((-38*r - 74*g + 112*b + 128) >> 8) + 128
    v = ((112*r - 94*g - 18*b + 128) >> 8) + 128
    uv = np.empty((h//2, w), dtype=np.uint8)
    uv[:, 0::2] = u.reshape(h//2, 2, w//2, 2).mean(axis=(1, 3)).round().clip(0, 255)
    uv[:, 1::2] = v.reshape(h//2, 2, w//2, 2).mean(axis=(1, 3)).round().clip(0, 255)
    return y.clip(0, 255).astype(np.uint8).tobytes() + uv.tobytes()


def jpeg(rgb):
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, "JPEG", quality=83)
    return output.getvalue()


def rgb_nv12_full(rgb):
    """Full-range inverse matching the deployed controlled HEF, not studio-range video."""
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.shape[0]%2 or rgb.shape[1]%2:
        raise ValueError('even RGB8 required')
    h,w,_=rgb.shape
    r,g,b=(rgb[:,:,i].astype(np.float64) for i in range(3))
    y=(g+(.343/1.765)*b+(.711/1.4)*r)/(1+.343/1.765+.711/1.4)
    u=(b-y)/1.765+128;v=(r-y)/1.4+128
    uv=np.empty((h//2,w),dtype=np.uint8)
    uv[:,::2]=u.reshape(h//2,2,w//2,2).mean(axis=(1,3)).round().clip(0,255)
    uv[:,1::2]=v.reshape(h//2,2,w//2,2).mean(axis=(1,3)).round().clip(0,255)
    return y.round().clip(0,255).astype(np.uint8).tobytes()+uv.tobytes()


def stamp(msg):
    return msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nsec


def rgb_message(msg):
    if msg.pixel_format_type != 3 or msg.step < msg.width*3 or len(msg.data) != msg.step*msg.height:
        raise ValueError("expected packed Gazebo RGB_INT8")
    return np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)[:, :msg.width*3].reshape(msg.height, msg.width, 3)


def depth_range(depth, box):
    """Central torso median. Aligned RGBD pixels only; invalid/dispersed = no range."""
    if depth is None or box is None:
        return None
    x, y, w, h = (box[k] for k in ("x", "y", "w", "h"))
    if not all(np.isfinite(v) for v in (x, y, w, h)) or w < 4 or h < 8:
        return None
    crop = depth[max(0, int(y+h*.25)):min(720, int(y+h*.6)),
                 max(0, int(x+w*.3)):min(1280, int(x+w*.7))]
    valid = crop[np.isfinite(crop) & (crop > .3) & (crop < 30)]
    if crop.size < 8 or valid.size < crop.size*.7:
        return None
    lo, med, hi = np.percentile(valid, (20, 50, 80))
    return float(med) if hi-lo < max(.4, .15*med) else None


def ingress_envelope(board, ingress_ns, completed_ns, stream_id):
    """Re-envelope on one PC clock; no board/PC clock offset estimate.

    The source time is explicitly PC pixel ingress, NOT simulated exposure.
    Full ingress->completion includes conversion, SSH, board work and return.
    Preserve older-observation age conservatively, and retain raw board timing.
    FreshFollow receives this local envelope with zero additional network RTT.
    """
    elapsed = (completed_ns-ingress_ns)/1e6
    processing = board['publish_monotonic_ms']-board['capture_monotonic_ms']
    if not 0 <= processing <= elapsed+2 or elapsed < 0:
        raise ValueError('inconsistent board/receiver durations')
    out = dict(board)
    out['lock'] = dict(board['lock'])
    out['lock']['obs_age_ms'] = max(elapsed, board['lock']['obs_age_ms']+max(0., elapsed-processing))
    out.update(source_id='gazebo.hailo15l', stream_id=stream_id,
        clock_domain='pc.gazebo_ingress.monotonic', capture_monotonic_ms=ingress_ns/1e6,
        publish_monotonic_ms=completed_ns/1e6, sample_monotonic_ms=completed_ns/1e6,
        age_ms=(completed_ns/1e6-ingress_ns/1e6), freshness_budget_ms=200.,
        valid_for_ms=max(0., 200-out['lock']['obs_age_ms']),
        board_timing=dict(capture_ms=board['capture_monotonic_ms'], publish_ms=board['publish_monotonic_ms']))
    return out


class GazeboPixels:
    def __init__(self):
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image as GzImage
        from gz.msgs10.clock_pb2 import Clock
        self.lock = threading.Lock()
        self.latest = self.overview = None
        self.depths = OrderedDict()
        self.sequence = self.invalid = 0
        self.clock = None
        self.previous_clock = None
        self.rtf = None
        self.node = Node()
        for typ, topic, cb in ((GzImage, "/garuda/drone/image", self.on_rgb),
                               (GzImage, "/garuda/drone/depth_image", self.on_depth),
                               (GzImage, "/garuda/overview", self.on_overview),
                               (Clock, "/world/garuda_follow/clock", self.on_clock)):
            if not self.node.subscribe(typ, topic, cb):
                raise RuntimeError("could not subscribe " + topic)

    def on_clock(self, msg):
        value = msg.sim.sec*1e9+msg.sim.nsec
        now = time.monotonic_ns()
        with self.lock:
            self.clock = (value, now)
            if self.previous_clock is None:
                self.previous_clock = self.clock
            elif now-self.previous_clock[1] > 1e9:
                self.rtf = (value-self.previous_clock[0])/(now-self.previous_clock[1])
                self.previous_clock = self.clock

    def on_rgb(self, msg):
        received = time.monotonic_ns()
        try:
            rgb = rgb_message(msg)
            if rgb.shape != (720, 1280, 3):
                raise ValueError("camera must be 1280x720")
            with self.lock:
                value = stamp(msg)
                if self.latest and value <= self.latest[1]:
                    self.invalid += 1
                    return
                self.sequence += 1
                self.latest = (self.sequence, value, received, rgb)
        except ValueError:
            self.invalid += 1

    def on_depth(self, msg):
        if (msg.width, msg.height, msg.pixel_format_type, msg.step) != (1280, 720, 13, 5120):
            return
        if len(msg.data) != 1280*720*4:
            return
        with self.lock:
            self.depths[stamp(msg)] = np.frombuffer(msg.data, dtype="<f4").reshape(720, 1280)
            while len(self.depths) > 4:
                self.depths.popitem(last=False)

    def on_overview(self, msg):
        try:
            value = (time.monotonic_ns(), jpeg(rgb_message(msg)))
            with self.lock:
                self.overview = value
        except ValueError:
            self.invalid += 1

    def snapshot(self):
        with self.lock:
            frame = self.latest
            return frame, self.depths.get(frame[1]) if frame else None, self.clock, self.rtf


def board_asset_path(value):
    from pathlib import PurePosixPath
    if (PurePosixPath(value).parent != PurePosixPath('/opt/garuda-sim') or
            any(c not in '/.-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in value)):
        raise ValueError('use an explicitly staged /opt/garuda-sim asset')
    return value


class BoardVision:
    """One SSH stream, one in-flight request, latest-frame source, finite timeouts.

    The board timestamps its *ingress*, not Gazebo exposure. Receiver ingress ->
    result interval is re-enveloped on the PC clock and charged exactly once.
    Simulator acquisition age remains a separately reported timing limitation.
    """
    def __init__(self, pixels, binary, error_log, events, profile='/opt/garuda-sim/profile.json'):
        binary=board_asset_path(binary);profile=board_asset_path(profile)
        self.pixels, self.events = pixels, events
        self.stream_id = uuid.uuid4().hex
        path = os.environ.get('GARUDA_RGB_NV12_LIB')
        self.color=os.environ.get('GARUDA_PIXEL_CONVERSION','sdk_full')
        if self.color not in ('sdk_full','601_limited'):raise ValueError('unknown pixel conversion')
        self.convert = NativeNv12(path,self.color) if path else rgb_nv12_full if self.color=='sdk_full' else rgb_nv12
        self.commands = queue.Queue(maxsize=1)
        self.results = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.pause_until = 0.
        self.proc = subprocess.Popen(["ssh", "-T", "-c", "aes128-gcm@openssh.com", "-oBatchMode=yes", "-oConnectTimeout=5",
            "-oServerAliveInterval=2", "-oServerAliveCountMax=2", "root@10.0.0.1",
            "exec env LD_LIBRARY_PATH=/opt/garuda-fresh/lib " + binary + " " + profile + " --stream"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log, bufsize=0)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def command(self, cmd):
        self.commands.put_nowait(cmd)

    def run(self):
        previous = 0
        try:
            while not self.stop.is_set():
                frame, depth, clock, rtf = self.pixels.snapshot()
                if not frame or frame[0] == previous or time.monotonic() < self.pause_until:
                    self.stop.wait(.005)
                    continue
                seq, sim_ns, received, rgb = frame
                previous = seq
                entered = time.monotonic_ns()
                raw = self.pixels.raw(seq) if hasattr(self.pixels,'raw') else self.convert(rgb)
                converted = time.monotonic_ns()
                header = dict(v=1, sequence=seq, bytes=len(raw))
                try:
                    header['command'] = self.commands.get_nowait()
                except queue.Empty:
                    pass
                # Nonblocking writes with a deadline avoid a dead board blocking teardown.
                payload = memoryview(json.dumps(header).encode()+b"\n"+raw)
                os.set_blocking(self.proc.stdin.fileno(), False)
                deadline = time.monotonic()+3
                while payload:
                    if self.stop.is_set() or time.monotonic() > deadline:
                        raise TimeoutError("board input timed out")
                    if select.select([], [self.proc.stdin], [], .1)[1]:
                        try:
                            n = os.write(self.proc.stdin.fileno(), payload[:65536])
                            payload = payload[n:]
                        except BlockingIOError:
                            pass
                sent = time.monotonic_ns()
                data = bytearray()
                while b"\n" not in data:
                    if self.stop.is_set() or time.monotonic() > deadline:
                        raise TimeoutError("board result timed out")
                    if select.select([self.proc.stdout], [], [], .1)[0]:
                        chunk = os.read(self.proc.stdout.fileno(), 65536)
                        if not chunk:
                            raise RuntimeError("board stream ended")
                        data.extend(chunk)
                        if len(data) > 512*1024:
                            raise ValueError("oversize board result")
                result = json.loads(data)
                completed = time.monotonic_ns()
                if result['sequence'] != seq or result['output']['sequence'] != seq:
                    raise ValueError("board source sequence mismatch")
                out = ingress_envelope(result['output'], received, completed, self.stream_id)
                if hasattr(self.pixels,'raw'):
                    out['source_id']='replay.hailo15l'
                    out['clock_domain']='pc.replay_release.monotonic'
                result['output'] = out
                out['raw_detections']=result.get('raw_detections',[])
                if depth is None:
                    with self.pixels.lock:
                        depth = self.pixels.depths.get(sim_ns)
                result.update(ingress_ns=received, received_ns=completed, sim_ns=sim_ns,
                    roundtrip_ms=(completed-received)/1e6, jpeg=jpeg(rgb),
                    host_stage_ms=dict(source_wait=(entered-received)/1e6, conversion=(converted-entered)/1e6,
                                  write=(sent-converted)/1e6, result_wait=(completed-sent)/1e6),
                    range_m=depth_range(depth, out['lock']['box']), depth_paired=depth is not None)
                if result.get('ack') is not None:
                    self.events("selection", result['ack'])
                try:
                    self.results.get_nowait()
                except queue.Empty:
                    pass
                self.results.put_nowait(result)
        except Exception as exc:
            if not self.stop.is_set():
                self.events("vision_error", str(exc))
            self.stop.set()

    def close(self):
        self.stop.set()
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.worker.join(timeout=4)
