#!/usr/bin/env python3
"""Hailo metadata -> Garuda viewer adapter with viewer-only person selection.

ISP capture time is preserved, NOT equated with Python CLOCK_MONOTONIC.
Freshness measures arrival of advancing source timestamps, not image age.
"""
import argparse
import json
import math
import pathlib
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
MAX_MESSAGE_BYTES = 1024 * 1024


def load_frame_type(descriptor_path):
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
    descriptor = descriptor_pb2.FileDescriptorSet.FromString(descriptor_path.read_bytes())
    pool = descriptor_pool.DescriptorPool()
    for file in descriptor.file:
        pool.Add(file)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("hailo_analytics.Frame"))


def decode_tracks(frame, target_label="person"):
    width, height = frame.frame_width, frame.frame_height
    if not (0 < width <= 16384 and 0 < height <= 16384 and frame.isp_timestamp_ns > 0):
        raise ValueError("invalid frame geometry or timestamp")
    if len(frame.detections) > 1000:
        raise ValueError("too many detections")
    tracks, seen = [], set()
    for det in frame.detections:
        if (target_label != "all" and det.label != target_label) or not det.HasField("tracking_id"):
            continue
        b = det.bbox
        values = [b.xmin, b.ymin, b.xmax, b.ymax, det.confidence]
        if not all(math.isfinite(v) for v in values) or not 0 <= det.confidence <= 1:
            raise ValueError("invalid track values")
        if not (0 <= b.xmin < b.xmax <= width and 0 <= b.ymin < b.ymax <= height):
            raise ValueError("invalid track box")
        if det.tracking_id in seen:
            raise ValueError("duplicate track ID")
        seen.add(det.tracking_id)
        tracks.append({"id": det.tracking_id, "label": det.label, "conf": det.confidence,
                       "x": b.xmin, "y": b.ymin, "w": b.xmax-b.xmin, "h": b.ymax-b.ymin,
                       "measurement_status": "not_exposed_by_source"})
    return {"width": width, "height": height}, tracks


def decode_diagnostics(frame):
    payload = getattr(frame, 'garuda_diagnostics_json', '')
    if not payload:
        return None
    obj = json.loads(payload)
    if obj.get('v') != 1 or type(obj.get('detector_ran')) is not bool:
        raise ValueError('invalid diagnostics version or marker')
    stamp = obj.get('source_timestamp_ns')
    if not isinstance(stamp, str) or not stamp.isdigit():
        raise ValueError('invalid diagnostic timestamp')
    raw = obj.get('raw')
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError('invalid raw detection list')
    out = []
    for d in raw:
        if not isinstance(d, dict) or not isinstance(d.get('label'), str):
            raise ValueError('invalid raw detection')
        vals = [d.get(k) for k in ('x', 'y', 'w', 'h', 'conf')]
        if not all(type(v) in (int, float) and math.isfinite(v) for v in vals):
            raise ValueError('invalid raw values')
        x, y, w, h, conf = vals
        if not (0 <= conf <= 1 and w > 0 and h > 0):
            raise ValueError('invalid raw bounds')
        # Preserve diagnostic geometry: clipping would hide upstream errors.
        out.append(dict(label=d['label'], conf=conf, x=x*frame.frame_width,
                        y=y*frame.frame_height, w=w*frame.frame_width, h=h*frame.frame_height))
    return dict(detector_ran=obj['detector_ran'], source_timestamp_ns=stamp,
                aligned=stamp == str(frame.isp_timestamp_ns), raw=out)


class State:
    def __init__(self, stale_ms=300, target_label="person"):
        if target_label not in ("person", "cell phone", "all"):
            raise ValueError("unsupported target label")
        self.target_label = target_label
        self.lock = threading.Lock()
        self.stale_ms = stale_ms
        self.session = str(uuid.uuid4())
        self.sequence = 0
        self.timestamp = None
        self.received_ms = None
        self.connected = False
        self.frame = {"width": 0, "height": 0}
        self.tracks = []
        self.error = "waiting for Hailo metadata"
        self.history = deque(maxlen=20)
        self.selected = None
        self.selection_lost = False
        self.diagnostics = None
        self.last_detection = None
        self.last_detection_ms = None
        self.diagnostic_error = None

    def select(self, track_id, session, sequence, now_ms=None):
        now_ms = time.monotonic()*1000 if now_ms is None else now_ms
        if type(track_id) is not int or type(sequence) is not int or not 0 <= track_id <= 0xffffffff:
            raise ValueError("Invalid track ID or sequence")
        with self.lock:
            displayed = next((row for row in self.history if row[0] == sequence and row[1] == session), None)
            if session != self.session or displayed is None:
                raise ValueError("Source changed; select from the current view")
            if (not self.connected or now_ms-displayed[2] > self.stale_ms
                    or self.received_ms is None or now_ms-self.received_ms > self.stale_ms):
                raise ValueError("View is stale; wait for a current frame")
            if track_id not in displayed[3] or not any(t['id'] == track_id for t in self.tracks):
                raise ValueError("Track is no longer visible; select again")
            self.selected = (session, track_id)
            self.selection_lost = False

    def clear_selection(self):
        with self.lock:
            self.selected = None
            self.selection_lost = False

    def reconnect(self):
        with self.lock:
            self.diagnostics = self.last_detection = self.last_detection_ms = None
            self.session = str(uuid.uuid4())
            self.timestamp = self.received_ms = None
            self.connected = True
            self.tracks = []
            self.error = "waiting for advancing source frame"
            self.history.clear()
            self.selection_lost = self.selected is not None

    def disconnect(self, error):
        with self.lock:
            self.connected = False
            self.tracks = []
            self.error = error
            self.selection_lost = self.selected is not None

    def ingest(self, frame, now_ms=None):
        geometry, tracks = decode_tracks(frame, self.target_label)
        try:
            diagnostics, diagnostic_error = decode_diagnostics(frame), None
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            diagnostics, diagnostic_error = None, str(exc)
        now_ms = time.monotonic()*1000 if now_ms is None else now_ms
        with self.lock:
            timestamp = frame.isp_timestamp_ns
            if timestamp == self.timestamp:
                return False  # Repeated cached frames must not renew freshness.
            if self.timestamp is not None and timestamp < self.timestamp:
                self.session = str(uuid.uuid4())
                self.last_detection = self.last_detection_ms = None
                self.history.clear()
                self.selection_lost = self.selected is not None
            if self.selected and (self.received_ms is None or now_ms-self.received_ms > self.stale_ms):
                self.selection_lost = True
            self.timestamp = timestamp
            self.received_ms = now_ms
            self.sequence += 1
            self.frame, self.tracks = geometry, tracks
            self.diagnostics, self.diagnostic_error = diagnostics, diagnostic_error
            if diagnostics and diagnostics['detector_ran']:
                self.last_detection, self.last_detection_ms = diagnostics, now_ms
            self.connected = True
            self.error = None
            ids = {t['id'] for t in tracks}
            self.history.append((self.sequence, self.session, now_ms, ids))
            if self.selected and (self.selected[0] != self.session or self.selected[1] not in ids):
                self.selection_lost = True
            return True

    def snapshot(self, now_ms=None):
        now_ms = time.monotonic()*1000 if now_ms is None else now_ms
        with self.lock:
            age = None if self.received_ms is None else max(0, now_ms-self.received_ms)
            live = self.connected and age is not None and age <= self.stale_ms
            if self.selected and not live:
                self.selection_lost = True
            selection = {"id": None, "source_session": None, "state": "none", "reason": "not_selected"}
            if self.selected:
                selection = {"id": self.selected[1], "source_session": self.selected[0],
                             "state": "lost" if self.selection_lost else "selected",
                             "reason": "manual_reselection_required" if self.selection_lost else "present_in_hailo_output"}
            return {"v": 2, "tracker_contract": "garuda.hailo.viewer.v1",
                    "source": "hailo-diagnostics" if self.target_label == "all" else "hailo-stock-phone" if self.target_label == "cell phone" else "hailo-stock-person",
                    "target_label": self.target_label, "source_session": self.session,
                    "sequence": self.sequence, "sequence_kind": "adapter_received_frames",
                    "source_capture_timestamp_ns": str(self.timestamp) if self.timestamp else None,
                    "source_clock_domain": "hailo.isp.unmapped",
                    "timestamp_valid": False, "age_ms": None,
                    "arrival_age_ms": age, "metadata_live": live,
                    "connection": "live" if live else "stale" if self.connected else "disconnected",
                    "frame": dict(self.frame), "tracks": list(self.tracks) if live else [],
                    "diagnostics": self.diagnostics if live else None,
                    "last_detection": self.last_detection if live else None,
                    "last_detection_arrival_age_ms": None if self.last_detection_ms is None else max(0, now_ms-self.last_detection_ms),
                    "diagnostic_error": self.diagnostic_error,
                    "selection": selection,
                    "lock": {"id": None, "state": "none", "control_valid": False,
                             "observation_valid": False, "reason": "viewer_only"},
                    "image_target": {"valid": False}, "error": self.error}


def receive_forever(state, source, frame_type, stop):
    import websocket
    while not stop.is_set():
        ws = None
        try:
            ws = websocket.create_connection(source, timeout=1, suppress_origin=True)
            state.reconnect()
            while not stop.is_set():
                payload = ws.recv()
                if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_MESSAGE_BYTES:
                    raise ValueError("invalid metadata message")
                frame = frame_type.FromString(payload)
                state.ingest(frame)
        except Exception as exc:
            state.disconnect(type(exc).__name__)
        finally:
            if ws is not None:
                ws.close()
        stop.wait(0.5)


def handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_bytes(self, data, content_type, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.send_bytes((ROOT / "hailo_viewer.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/hailo_viewer.js":
                self.send_bytes((ROOT / "hailo_viewer.js").read_bytes(), "text/javascript")
            elif path in ("/api/snapshot", "/api/mono"):
                self.send_bytes(json.dumps(state.snapshot(), allow_nan=False).encode(), "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in ("/api/select", "/api/unlock"):
                self.send_bytes(b'{"ok":false,"error":"Unsupported viewer command"}', 'application/json', 405)
                return
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                self.send_bytes(b'{"ok":false,"error":"Origin rejected"}', 'application/json', 403)
                return
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('JSON request required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Invalid request size')
                self.connection.settimeout(2)
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError('Invalid request')
                if path == '/api/select':
                    state.select(request['id'], request['source_session'], request['sequence'])
                else:
                    state.clear_selection()
                result, code = {'ok': True, 'snapshot': state.snapshot()}, 200
            except (ValueError, KeyError, TypeError, TimeoutError) as exc:
                result, code = {'ok': False, 'error': str(exc)}, 409
            self.send_bytes(json.dumps(result, allow_nan=False).encode(), 'application/json', code)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--target-label", choices=("person", "cell phone", "all"), default="person")
    parser.add_argument("--source", default="ws://127.0.0.1:8765")
    parser.add_argument("--descriptor", type=pathlib.Path, default=ROOT / "analytics_metadata.desc")
    args = parser.parse_args()
    state, stop = State(target_label=args.target_label), threading.Event()
    frame_type = load_frame_type(args.descriptor)
    server = ThreadingHTTPServer((args.bind, args.port), handler(state))
    server.daemon_threads = True
    threading.Thread(target=receive_forever, args=(state, args.source, frame_type, stop), daemon=True).start()
    print(f"Garuda Hailo viewer on :{args.port}; metadata {args.source}; viewer selection only", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
