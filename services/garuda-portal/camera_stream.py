"""MJPEG child-process reader with the cam_portal wedge lessons baked in."""
from __future__ import annotations
import subprocess, threading, time, sys

def split_mjpeg(buf: bytes):
    frames = []
    while True:
        s = buf.find(b"\xff\xd8\xff")
        e = buf.find(b"\xff\xd9", s + 3) if s >= 0 else -1
        if s < 0 or e < 0:
            return frames, (buf[s:] if s > 0 else buf)
        frames.append(buf[s:e + 2])
        buf = buf[e + 2:]

DEFAULT_CMD = ["rpicam-vid", "--nopreview", "-t", "0", "--codec", "mjpeg",
               "--width", "1280", "--height", "720", "--framerate", "15", "-o", "-"]


class FrameSource:
    """A frame buffer with the same latest/cond/stalled surface mjpeg_client_loop
    consumes, but fed externally via feed() instead of owning a subprocess. Used
    for the inference preview stream (annotated JPEGs pushed from an inference
    child's stdout) so /api/stream can serve either source with one code path."""
    def __init__(self):
        self.latest: bytes | None = None
        self.t_last_ns = 0
        self.cond = threading.Condition()

    def feed(self, jpeg: bytes):
        with self.cond:
            self.latest = jpeg
            self.t_last_ns = time.monotonic_ns()
            self.cond.notify_all()

    def stalled(self, max_age_s=15.0) -> bool:
        return self.t_last_ns > 0 and (time.monotonic_ns() - self.t_last_ns) > int(max_age_s * 1e9)

class CameraStream:
    def __init__(self, cmd=None):
        self.cmd = cmd or DEFAULT_CMD
        self.latest: bytes | None = None
        self.t_last_ns = 0
        self.cond = threading.Condition()
        self._proc = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._proc: self._proc.kill()

    def stalled(self, max_age_s=15.0) -> bool:
        return self.t_last_ns > 0 and (time.monotonic_ns() - self.t_last_ns) > int(max_age_s * 1e9)

    def _reader(self):
        while not self._stop.is_set():
            try:
                self._proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL)
            except OSError as e:
                print(f"CameraStream: failed to start {self.cmd[0]}: {e}", file=sys.stderr)
                self._stop.wait(2.0)
                continue
            buf = b""
            while not self._stop.is_set():
                chunk = self._proc.stdout.read(65536)
                if not chunk: break
                frames, buf = split_mjpeg(buf + chunk)
                if frames:
                    with self.cond:
                        self.latest = frames[-1]
                        self.t_last_ns = time.monotonic_ns()
                        self.cond.notify_all()
            if not self._stop.is_set():
                self._proc.kill()
            self._stop.wait(2.0)   # relaunch loop = the Restart=always lesson, in-process
