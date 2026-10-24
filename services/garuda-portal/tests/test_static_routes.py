import sys, pathlib, json, threading, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import portal

PANEL_IDS = ["panel-overview", "panel-camera", "panel-inference",
             "panel-calibration", "panel-readiness", "panel-settings", "panel-system"]

# --- list_hef_models -----------------------------------------------------

def test_list_hef_models_filters_and_sorts(tmp_path):
    (tmp_path / "yolov8m_h10.hef").write_bytes(b"x")
    (tmp_path / "yolov5s_h10.hef").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    (tmp_path / "yolov8m_h8.hef").write_bytes(b"x")  # wrong device family, must be excluded

    models = portal.list_hef_models(str(tmp_path))

    assert models == ["yolov5s_h10.hef", "yolov8m_h10.hef"]

def test_list_hef_models_missing_dir_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert portal.list_hef_models(str(missing)) == []

# --- capture_still ---------------------------------------------------------

class StubStream:
    def __init__(self, latest=None):
        self.latest = latest

def test_capture_still_no_frame_returns_not_ok(tmp_path):
    result = portal.capture_still(StubStream(latest=None), out_dir=str(tmp_path))
    assert result == {"ok": False}

def test_capture_still_saves_frame(tmp_path):
    out_dir = tmp_path / "portal_stills"
    result = portal.capture_still(StubStream(latest=b"\xff\xd8\xfffakejpeg\xff\xd9"),
                                  out_dir=str(out_dir))
    assert result["ok"] is True
    saved = pathlib.Path(result["file"])
    assert saved.exists()
    assert saved.parent == out_dir
    assert saved.read_bytes() == b"\xff\xd8\xfffakejpeg\xff\xd9"

# --- service_action (configd passthrough) -----------------------------------

def test_service_action_passes_through_to_injected_call():
    calls = []
    def fake_call(op, args):
        calls.append((op, args))
        return {"ok": True, "detail": "restarted", "result": None}

    result = portal.service_action({"unit": "garuda-cam-portal", "action": "restart"},
                                   call=fake_call)

    assert calls == [("unit.action", {"unit": "garuda-cam-portal", "action": "restart"})]
    assert result == {"ok": True, "detail": "restarted", "result": None}

def test_service_action_returns_rejection_verbatim():
    def fake_call(op, args):
        return {"ok": False, "detail": "unit not whitelisted", "result": None}

    result = portal.service_action({"unit": "sshd", "action": "restart"}, call=fake_call)

    assert result["ok"] is False
    assert "not whitelisted" in result["detail"]

# --- full server smoke: static page + models/logs routes --------------------

def _start_server(deps, port):
    server = portal.build_server(port, deps)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return server

def test_index_html_contains_all_seven_panels():
    deps = {"health": lambda: {}}
    server = _start_server(deps, 8099)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8099/")
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "text/html"
        body = resp.read().decode()
        for panel_id in PANEL_IDS:
            assert f'id="{panel_id}"' in body, f"missing {panel_id}"
    finally:
        server.shutdown()

def test_api_models_route_returns_json_list(tmp_path):
    (tmp_path / "yolov8m_h10.hef").write_bytes(b"x")
    deps = {
        "health": lambda: {},
        "get_routes": {"/api/models": lambda h: h._json(portal.list_hef_models(str(tmp_path)))},
    }
    server = _start_server(deps, 8100)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8100/api/models")
        assert resp.status == 200
        assert json.loads(resp.read()) == ["yolov8m_h10.hef"]
    finally:
        server.shutdown()

def test_api_logs_route_returns_text_plain():
    def logs_handler(handler):
        body = b"line1\nline2\n"
        handler.send_response(200)
        handler.send_header("Content-Type", "text/plain")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    deps = {"health": lambda: {}, "get_routes": {"/api/logs": logs_handler}}
    server = _start_server(deps, 8101)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8101/api/logs")
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "text/plain"
        assert resp.read() == b"line1\nline2\n"
    finally:
        server.shutdown()

def test_api_actions_capture_still_route_end_to_end():
    stream = StubStream(latest=b"\xff\xd8\xffjpeg\xff\xd9")
    stills_dir = None
    import tempfile
    tmp = tempfile.mkdtemp()

    def capture_handler(handler, body):
        handler._json(portal.capture_still(stream, out_dir=tmp))

    deps = {"health": lambda: {}, "post_routes": {"/api/actions/capture-still": capture_handler}}
    server = _start_server(deps, 8102)
    try:
        req = urllib.request.Request("http://127.0.0.1:8102/api/actions/capture-still",
                                     data=b"{}", method="POST")
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        assert data["ok"] is True
        assert pathlib.Path(data["file"]).exists()
    finally:
        server.shutdown()

# --- /api/actions/inference and /api/actions/service, wired exactly as main() does ---

class FakeManager:
    """Stands in for InferenceManager: same start()/stop() contract, no threads/subprocess."""
    def __init__(self):
        self.calls = []
    def start(self):
        self.calls.append("start")
        return {"ok": True, "mode": "inference"}
    def stop(self):
        self.calls.append("stop")
        return {"ok": True, "mode": "stream"}

def _post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req)
    return resp.status, json.loads(resp.read())

def test_inference_action_route_start_http_level():
    manager = FakeManager()
    # Wired identically to main()'s inference_action_handler: a thin closure
    # delegating to the pure portal.inference_action dispatcher.
    def inference_action_handler(handler, body):
        handler._json(portal.inference_action(body, manager))

    deps = {"health": lambda: {}, "post_routes": {"/api/actions/inference": inference_action_handler}}
    server = _start_server(deps, 8103)
    try:
        status, data = _post_json("http://127.0.0.1:8103/api/actions/inference", {"action": "start"})
        assert status == 200
        assert data == {"ok": True, "mode": "inference"}
        assert manager.calls == ["start"]
    finally:
        server.shutdown()

def test_inference_action_route_bogus_action_http_level():
    manager = FakeManager()
    def inference_action_handler(handler, body):
        handler._json(portal.inference_action(body, manager))

    deps = {"health": lambda: {}, "post_routes": {"/api/actions/inference": inference_action_handler}}
    server = _start_server(deps, 8104)
    try:
        status, data = _post_json("http://127.0.0.1:8104/api/actions/inference", {"action": "sideways"})
        assert status == 200
        assert data["ok"] is False
        assert "unknown action" in data["error"]
        assert manager.calls == []  # never dispatched to start()/stop()
    finally:
        server.shutdown()

def test_service_action_route_http_level_passthrough():
    calls = []
    def fake_call(op, args):
        calls.append((op, args))
        return {"ok": True, "detail": "restarted", "result": None}
    # Wired identically to main()'s service_action_handler, with an injected
    # fake configd call instead of a real socket.
    def service_action_handler(handler, body):
        handler._json(portal.service_action(body, call=fake_call))

    deps = {"health": lambda: {}, "post_routes": {"/api/actions/service": service_action_handler}}
    server = _start_server(deps, 8105)
    try:
        payload = {"unit": "garuda-cam-portal", "action": "restart"}
        status, data = _post_json("http://127.0.0.1:8105/api/actions/service", payload)
        assert status == 200
        assert data == {"ok": True, "detail": "restarted", "result": None}
        assert calls == [("unit.action", payload)]  # exact op/args passthrough
    finally:
        server.shutdown()

def test_readiness_report_route_http_level():
    """GET /api/readiness/report with injected health and config callables."""
    def fake_health():
        return {"throttled": "0x0", "temp_c": 50.0, "npu": "HAILO10H",
                "services": {"garuda-portal": True, "garuda-configd": True,
                            "garuda-ptp4l-client": True},
                "disk_free_gb": 100.0, "uptime_s": 600.0}

    def fake_config_call(op, args):
        # Simulate successful config.get
        return {"ok": True, "result": {"bridge.agent_ip": None}}

    def readiness_handler(handler):
        handler._json(portal.readiness_report(health_fn=fake_health, config_call=fake_config_call))

    deps = {"health": lambda: {}, "get_routes": {"/api/readiness/report": readiness_handler}}
    server = _start_server(deps, 8106)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8106/api/readiness/report")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "overall" in data
        assert data["overall"] == "go"
        assert "checks" in data
        assert "t_ns" in data
        assert len(data["checks"]) > 0
        # Verify at least one check has the expected structure
        check = data["checks"][0]
        assert "id" in check
        assert "status" in check
        assert "evidence" in check
    finally:
        server.shutdown()

def test_readiness_report_configd_exception_graceful_fallback():
    """IMPORTANT: configd socket missing (OSError) must not crash; config defaults to {}."""
    def fake_health():
        return {"throttled": "0x0", "temp_c": 50.0, "npu": "HAILO10H",
                "services": {"garuda-portal": True, "garuda-configd": True,
                            "garuda-ptp4l-client": True},
                "disk_free_gb": 100.0, "uptime_s": 600.0}

    def failing_config_call(op, args):
        # Simulate dev PC: configd socket missing
        raise OSError("socket not found")

    def readiness_handler(handler):
        handler._json(portal.readiness_report(health_fn=fake_health, config_call=failing_config_call))

    deps = {"health": lambda: {}, "get_routes": {"/api/readiness/report": readiness_handler}}
    server = _start_server(deps, 8107)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8107/api/readiness/report")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "overall" in data
        assert "checks" in data
        # With empty config (fallback), bridge.session should be "na"
        bridge = next(c for c in data["checks"] if c["id"] == "bridge.session")
        assert bridge["status"] == "na"
    finally:
        server.shutdown()
