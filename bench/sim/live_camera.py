"""Fixed desk-camera UI/supervisor connection; never stops or replaces inference.

JPEG and snapshots are independent on the current native protocol. Label this
preview approximate; do not claim exact-frame overlays or native-4K zoom.
"""
import json
import queue
import threading
import time
import urllib.parse
import urllib.request


class LiveCameraVision:
    def __init__(self, pixels, log, event):
        self.pixels, self.log, self.event = pixels, log, event
        self.stop = threading.Event()
        self.results = queue.Queue(maxsize=1)
        self.commands = queue.Queue(maxsize=8)
        self.pause_until = 0
        self.latest_jpeg = None
        self.jpeg_at = 0
        self.workers = [threading.Thread(target=f, daemon=True) for f in (self.images, self.states, self.send_commands)]
        for worker in self.workers:
            worker.start()

    def images(self):
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen('http://10.0.0.1:8099/stream', timeout=1) as stream:
                    while not self.stop.is_set():
                        line = stream.readline(1024)
                        if not line:
                            raise EOFError('camera JPEG stream closed')
                        if line.lower().startswith(b'content-length:'):
                            size = int(line.split(b':', 1)[1])
                            if not 0 < size <= 4*1024*1024:
                                raise ValueError('oversize JPEG')
                            if stream.readline(1024) != b'\r\n':
                                raise ValueError('bad JPEG header')
                            image = stream.read(size)
                            if len(image) != size:
                                raise EOFError('truncated JPEG')
                            self.latest_jpeg, self.jpeg_at = image, time.monotonic_ns()
            except (OSError, EOFError, ValueError):
                self.stop.wait(.2)

    def states(self):
        while not self.stop.is_set():
            started = time.monotonic_ns()
            if started/1e9 < self.pause_until:
                self.stop.wait(.025)
                continue
            try:
                with urllib.request.urlopen('http://10.0.0.1:8099/api/state', timeout=.3) as response:
                    raw = response.read(512*1024+1)
                if len(raw) > 512*1024:
                    raise ValueError('oversize camera snapshot')
                out = json.loads(raw)
                received = time.monotonic_ns()
                if out['source_id'] != 'hailo15l.imx678' or out['frame'] != dict(width=1280, height=720):
                    raise ValueError('unexpected physical source/geometry')
                if self.latest_jpeg is None:
                    self.stop.wait(.025)
                    continue
                _, _, clock, _ = self.pixels.snapshot()
                result = dict(output=out, sequence=out['sequence'], jpeg=self.latest_jpeg,
                    request_started_ns=started, received_ns=received, ingress_ns=started,
                    age_ms=out['age_ms']+(received-started)/1e6, range_m=None, depth_paired=False,
                    sim_ns=clock[0] if clock else 0, live_camera=True, overlay_matched=False,
                    preview_received_ns=self.jpeg_at, raw_detections=[])
                try:
                    self.results.get_nowait()
                except queue.Empty:
                    pass
                self.results.put_nowait(result)
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.event('camera_transport', str(error))
                self.stop.wait(.2)
            self.stop.wait(.025)

    def command(self, row):
        self.commands.put_nowait(row)

    def send_commands(self):
        while not self.stop.is_set():
            try:
                row = self.commands.get(timeout=.1)
            except queue.Empty:
                continue
            cmd = row['cmd']
            route = {'unlock': '/api/unlock', 'select': '/api/select', 'lock_point': '/api/mono_click'}[cmd]
            query = urllib.parse.urlencode({k:v for k,v in row.items() if k != 'cmd'})
            try:
                request = urllib.request.Request('http://10.0.0.1:8099'+route+'?'+query, method='POST')
                with urllib.request.urlopen(request, timeout=.5) as response:
                    answer = json.loads(response.read(4096))
                self.event('selection', answer)
            except (OSError, ValueError) as error:
                self.event('selection', dict(ok=False, error=str(error)))

    def close(self):
        self.stop.set()
        for worker in self.workers:
            worker.join(timeout=1.2)
