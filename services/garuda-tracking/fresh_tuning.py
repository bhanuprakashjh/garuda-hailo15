"""Bounded, local bench controls. No shell commands or caller-supplied paths."""
import copy
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from urllib.parse import urlparse


LIMITS = {
    "detector_fps": (5, 30), "preview_fps": (1, 30),
    "birth_confidence": (.20, .95), "control_confidence": (.15, .95),
    "confirm_ms": (50, 1000), "coast_ms": (300, 3000),
}


def validate(values, limits):
    if not isinstance(values, dict) or set(values) != set(limits):
        raise ValueError("Supply exactly the displayed settings")
    for key, (lo, hi) in limits.items():
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError("%s must be between %s and %s" % (key, lo, hi))
        if key.endswith(("fps", "_ms")) and int(value) != value:
            raise ValueError(key + " must be a whole number")
    return values


class Tuning:
    def __init__(self, feed, root="/opt/garuda-fresh"):
        self.feed = feed
        self.root = Path(root)
        self.mutex = threading.Lock()
        self.config_path = self.root / "current.json"
        self.baseline_path = self.root / "tuning-baseline.json"

    def read(self, path):
        return json.loads(path.read_text())

    def local_path(self, name):
        path = Path(name).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Tuning requires a local bench profile")
        return path

    def configs(self):
        cfg = self.read(self.config_path)
        media = self.read(self.local_path(cfg["medialib_config"]))
        profile = next(p for p in media["profiles"] if p["name"] == cfg["profile"])
        profile = self.read(self.local_path(profile["config_file"]))
        app_path = self.local_path(profile["application_settings"])
        return cfg, app_path, self.read(app_path)

    def v4l(self, arg):
        return subprocess.run(["v4l2-ctl", "-d", "/dev/video0", arg],
                              capture_output=True, text=True, check=True, timeout=4).stdout

    def camera(self):
        out = self.v4l("--get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain")
        vals = dict(re.findall(r"(isp_ae_\w+):\s*(\d+)", out))
        return {"auto": bool(int(vals["isp_ae_enable"])),
                "exposure_ms": int(vals["isp_ae_integration_time"]) / 1000,
                "gain": int(vals["isp_ae_gain"]) / 1024}

    def set_camera(self, values):
        if values["auto"]:
            self.v4l("--set-ctrl=isp_ae_enable=1")
        else:
            self.v4l("--set-ctrl=isp_ae_enable=0")
            self.v4l("--set-ctrl=isp_ae_gain=%d" % round(values["gain"] * 1024))
            self.v4l("--set-ctrl=isp_ae_integration_time=%d" % round(values["exposure_ms"] * 1000))

    def snapshot(self):
        return json.loads(self.feed._raw_snap or b"{}")

    def state(self):
        cfg, _, app = self.configs()
        streams = {r["stream_id"]: r for r in app["application_input_streams"]["resolutions"]}
        settings = {k: cfg["tracking"][k] for k in LIMITS if k not in ("detector_fps", "preview_fps")}
        settings.update(detector_fps=streams[cfg["ai_stream"]]["framerate"], preview_fps=cfg["jpeg_fps"])
        snap = self.snapshot()
        aged = json.loads(getattr(self.feed, "snap", None) or b"{}")
        return {"ok": True, "model": Path(cfg.get("hef", "unknown")).name, "settings": settings, "camera": self.camera(),
                "sequence": snap.get("sequence"), "capture_ms": snap.get("capture_monotonic_ms"),
                "age_ms": max(0, time.monotonic()*1000-snap.get("capture_monotonic_ms", 0)),
                "lock": aged.get("lock", snap.get("lock", {})), "baseline_saved": self.baseline_path.exists()}

    def write(self, path, data):
        temp = path.with_suffix(path.suffix + ".tuning-tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(temp, path)

    def pids(self):
        expected = str(self.root / "garuda-fresh-tracking").encode()
        found = []
        for path in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                args = path.read_bytes().split(b"\0")
                if args[:3] == [expected, b"--config", str(self.config_path).encode()]:
                    found.append(int(path.parent.name))
            except (FileNotFoundError, ProcessLookupError):
                pass
        return found

    def restart(self):
        for pid in self.pids():
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 8
        while self.pids():
            if time.monotonic() > deadline:
                raise RuntimeError("Tracker did not stop; no second instance was started")
            time.sleep(.1)
        started = time.monotonic()*1000
        env = dict(os.environ, LD_LIBRARY_PATH=str(self.root / "lib"))
        with open("/tmp/garuda-fresh.log", "ab") as log:
            proc = subprocess.Popen([str(self.root / "garuda-fresh-tracking"), "--config", str(self.config_path)],
                                    cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, start_new_session=True)
        Path("/tmp/garuda-fresh.pid").write_text(str(proc.pid) + "\n")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("Tracker exited; see /tmp/garuda-fresh.log")
            if self.snapshot().get("capture_monotonic_ms", 0) > started:
                return
            time.sleep(.2)
        raise RuntimeError("Tracker did not produce fresh frames")

    def apply(self, request):
        if not self.mutex.acquire(blocking=False):
            raise ValueError("Another tuning change is still being applied")
        try:
            action = request.get("action")
            if action not in ("camera", "pipeline", "restore"):
                raise ValueError("Unknown tuning action")
            if action == "camera":
                values = request.get("values")
                if not isinstance(values, dict) or type(values.get("auto")) is not bool:
                    raise ValueError("auto must be true or false")
                validate({k: v for k, v in values.items() if k != "auto"},
                         {"exposure_ms": (.1, 33), "gain": (1, 30)})
            elif action == "pipeline":
                values = validate(request.get("values"), LIMITS)
                if values["control_confidence"] > values["birth_confidence"]:
                    raise ValueError("Lock confidence must not exceed new-track confidence")
            cfg, app_path, app = self.configs()
            if action == "pipeline":
                if values["birth_confidence"] <= cfg["tracking"].get("low_confidence", .15):
                    raise ValueError("New-track confidence must exceed the low-confidence threshold")
                if values["control_confidence"] < cfg["tracking"].get("low_confidence", .15):
                    raise ValueError("Lock confidence is below the low-confidence threshold")
                if values["coast_ms"] < cfg["tracking"].get("max_gap_ms", 250):
                    raise ValueError("Coast retention must exceed the track gap limit")
            camera = self.camera()
            before = {"config": cfg, "app_path": str(app_path), "app": app, "camera": camera}
            if not self.baseline_path.exists():
                self.write(self.baseline_path, before)
            if action == "camera":
                try:
                    self.set_camera(values)
                except Exception:
                    self.set_camera(camera)
                    raise
            else:
                if action == "restore":
                    target = self.read(self.baseline_path)
                    if self.local_path(target["app_path"]) != app_path:
                        raise ValueError("Baseline profile differs; restore the original bench profile first")
                else:
                    target = copy.deepcopy(before)
                    for k in LIMITS:
                        if k not in ("detector_fps", "preview_fps"):
                            target["config"]["tracking"][k] = values[k]
                    target["config"]["jpeg_fps"] = values["preview_fps"]
                    for stream in target["app"]["application_input_streams"]["resolutions"]:
                        if stream["stream_id"] == cfg["ai_stream"]:
                            stream["framerate"] = values["detector_fps"]
                        elif stream["stream_id"] == cfg["jpeg_stream"]:
                            stream["framerate"] = values["preview_fps"]
                try:
                    self.write(self.config_path, target["config"])
                    self.write(app_path, target["app"])
                    self.restart()
                    self.set_camera(target["camera"])
                except Exception as error:
                    self.write(self.config_path, before["config"])
                    self.write(app_path, before["app"])
                    try:
                        self.restart()
                        self.set_camera(camera)
                    except Exception as rollback:
                        raise RuntimeError("Apply failed: %s; recovery failed: %s" % (error, rollback))
                    raise RuntimeError("Apply failed; previous settings recovered: %s" % error)
            return self.state()
        finally:
            self.mutex.release()


def handler(parent, tuning):
    class H(parent):
        def tuning_json(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path != "/api/tuning":
                return super().do_GET()
            try:
                return self.tuning_json(200, tuning.state())
            except Exception as e:
                return self.tuning_json(503, {"ok": False, "error": str(e)})

        def do_POST(self):
            if urlparse(self.path).path != "/api/tuning":
                return super().do_POST()
            try:
                # JSON + custom header require CORS preflight; no CORS is granted here.
                origin = self.headers.get("Origin")
                if (self.headers.get("X-Garuda-Tuning") != "1" or
                        self.headers.get("Content-Type") != "application/json" or
                        (origin and urlparse(origin).netloc != self.headers.get("Host"))):
                    raise ValueError("Tuning must be submitted from this viewer")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Invalid request length")
                self.connection.settimeout(90)
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("Expected an object")
                return self.tuning_json(200, tuning.apply(request))
            except ValueError as e:
                self.close_connection = True
                return self.tuning_json(400, {"ok": False, "error": str(e)})
            except Exception as e:
                return self.tuning_json(503, {"ok": False, "error": str(e)})
    return H
