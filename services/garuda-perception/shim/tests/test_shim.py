"""Runs the shim against a fake node (feed + command sockets) and checks the HTTP contract."""
import json, socket, struct, subprocess, sys, threading, time, urllib.request, pathlib
HERE = pathlib.Path(__file__).resolve().parent; SHIM = HERE.parent / "garuda_mono_shim.py"
# "lock" carries LockCore's eight additive fields (F1 lock-core, include/garuda/lock_core.hpp; `epoch`
# and `box` added by the final-fix wave, review findings I2/I5) alongside the pre-existing
# id/class/coasting -- the shim must pass all of them through unmodified (it forwards the node's raw
# snapshot bytes verbatim, never rebuilds the dict; see main()'s assertions below). `box` is carried
# here as a populated object (not null) precisely so a shim that re-serialised the dict rather than
# forwarding bytes would be caught on a nested value, not just a scalar.
SNAP = {"v": 2, "age_ms": 12, "tracks": [{"id": 0, "label": "person", "conf": 0.9, "x": 1, "y": 2, "w": 3, "h": 4, "coasting": False}],
        "lock": {"id": None, "class": "", "coasting": False, "state": "none", "identity_locked": False,
                 "observation_valid": False, "control_valid": False, "quality": 0.0, "obs_age_ms": 0.0,
                 "uncertainty_px": 0.0,
                 "epoch": 2, "box": {"x": 100.5, "y": 50.25, "w": 40.0, "h": 120.0}},
        "distance": {"raw_m": None, "est_m": None, "valid": False},
        "depth_engine": "y26d", "detector": {"mode": "primary", "prompt": []}, "cal": {"n": 0, "fit": None},
        "frame": {"width": 1280, "height": 720}, "gesture": {"name": None, "track_id": None, "held_ms": 0},
        # On-board fix round 9: `lock.control_valid` (Ruling 30) and the `diag` counters both ride
        # through the shim as part of the raw snapshot bytes, like everything else -- the fixture
        # carries them so a shim that ever started re-serialising the dict would be caught on them.
        "diag": {"raw_dets": -1, "sdk_tracks": 5, "live_raw": 4, "published": 3, "core_candidates": 4}}
JPEG = b"\xff\xd8" + b"\x00" * 100 + b"\xff\xd9"
BIG_JPEG = b"\xff\xd8" + b"\x00" * 220000 + b"\xff\xd9"  # forces short recv()s on the shim side once a socket timeout is set
received = []

def fake_feed(port):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", port)); srv.listen(1)
    c, _ = srv.accept()
    for i in range(40):
        s = dict(SNAP); s["age_ms"] = i; p = json.dumps(s).encode()
        c.sendall(b"S" + struct.pack(">I", len(p)) + p); c.sendall(b"J" + struct.pack(">I", len(JPEG)) + JPEG); time.sleep(0.05)
    # Regression: a >=200 KB J frame sent in small (8 KB) chunks with a delay between each — this is
    # exactly the shape that forces socket.recv() to return short once a timeout is set (the bug
    # recv_exact fixes; MSG_WAITALL cannot be trusted with a timeout under CPython).
    big_frame = b"J" + struct.pack(">I", len(BIG_JPEG)) + BIG_JPEG
    for off in range(0, len(big_frame), 8192):
        c.sendall(big_frame[off:off + 8192]); time.sleep(0.005)
    for i in range(5):
        s = dict(SNAP); s["age_ms"] = 100 + i; p = json.dumps(s).encode()
        c.sendall(b"S" + struct.pack(">I", len(p)) + p); time.sleep(0.05)
    time.sleep(2); c.close(); srv.close()

def fake_cmd(port):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", port)); srv.listen(1)
    c, _ = srv.accept(); f = c.makefile("rw")
    for line in f:
        req = json.loads(line); received.append(req)
        ok = req["cmd"] in ("lock_point", "target", "cal_reset") or (req["cmd"] == "detector" and req.get("mode") == "primary")
        f.write(json.dumps({"ok": ok} if ok else {"ok": False, "error": "only primary in v1"}) + "\n"); f.flush()

def read_mjpeg_part(m):
    """Read one multipart/x-mixed-replace part off an already-open /stream response: skip any blank
    separator line from the previous part, the "--frame" boundary, the headers up to the blank line,
    then exactly Content-Length body bytes. Returns (content_length, body)."""
    line = m.readline()
    while line in (b"\r\n", b"\n"):
        line = m.readline()
    assert line.startswith(b"--frame"), line
    headers = {}
    while True:
        hline = m.readline()
        if hline in (b"\r\n", b"\n", b""): break
        if b":" in hline:
            k, v = hline.split(b":", 1); headers[k.strip().lower()] = v.strip()
    length = int(headers[b"content-length"])
    body = m.read(length)
    return length, body

def main():
    threading.Thread(target=fake_feed, args=(28971,), daemon=True).start()
    threading.Thread(target=fake_cmd, args=(28972,), daemon=True).start()
    proc = subprocess.Popen([sys.executable, str(SHIM), "--feed", "127.0.0.1:28971", "--cmd", "127.0.0.1:28972", "--port", "28098"])
    try:
        time.sleep(1.0)
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:28098/api/state", timeout=3).read()); assert st["v"] == 2 and st["tracks"][0]["label"] == "person"
        # LockCore's eight additive fields ride through /api/state unmodified (the shim never rebuilds
        # the "lock" dict -- it forwards the node's raw snapshot bytes verbatim).
        assert st["lock"]["state"] == "none" and st["lock"]["identity_locked"] is False
        assert st["lock"]["observation_valid"] is False and st["lock"]["quality"] == 0.0
        assert st["lock"]["obs_age_ms"] == 0.0 and st["lock"]["uncertainty_px"] == 0.0
        assert st["lock"]["epoch"] == 2 and isinstance(st["lock"]["epoch"], int)
        assert st["lock"]["box"] == {"x": 100.5, "y": 50.25, "w": 40.0, "h": 120.0}
        # Round 9 (Rulings 30 + diag): both new fields survive the shim untouched.
        assert st["lock"]["control_valid"] is False
        assert st["diag"] == {"raw_dets": -1, "sdk_tracks": 5, "live_raw": 4, "published": 3, "core_candidates": 4}
        # Round 9 (Ruling 31): "/" is the board-truth viewer, not the old debug dump -- an overlay
        # canvas over the MJPEG image, and a click that posts straight to the node's lock_point
        # endpoint. Asserted as strings because the point is that the page needs nothing external:
        # if it renders at all over an SSH tunnel, these two are what make it show the board's lock.
        idx = urllib.request.urlopen("http://127.0.0.1:28098/", timeout=3)
        assert idx.headers["Content-Type"].startswith("text/html")
        page = idx.read()
        assert b"<canvas" in page, page[:200]
        assert b"/api/mono_click?x=" in page
        assert b"/api/mono_target?class=" in page
        assert b"/api/events" in page and b"/stream" in page
        assert b"http://" not in page and b"https://" not in page, "the viewer must load no external resource"
        r = urllib.request.urlopen("http://127.0.0.1:28098/api/events", timeout=3); assert r.headers["Content-Type"].startswith("text/event-stream")
        t0 = time.time(); lines = []
        while time.time() - t0 < 1.0:
            l = r.readline();
            if l.startswith(b"data: "): lines.append(l)
        assert 3 <= len(lines) <= 22, f"SSE rate out of bounds: {len(lines)}/s"      # SSE_MAX_HZ is 30 (6c8c041), so the 20 Hz test feed bounds the rate
        m = urllib.request.urlopen("http://127.0.0.1:28098/stream", timeout=3); assert "multipart/x-mixed-replace" in m.headers["Content-Type"]
        chunk = m.read(120); assert b"Content-Type: image/jpeg" in chunk  # <=1 frame's body now that /stream no longer resends unchanged frames (item 2)
        req = urllib.request.Request("http://127.0.0.1:28098/api/mono_click?x=140&y=130", method="POST"); assert urllib.request.urlopen(req, timeout=3).status == 200
        req = urllib.request.Request("http://127.0.0.1:28098/api/mono_click?x=foo&y=1", method="POST")
        try: urllib.request.urlopen(req, timeout=3); assert False, "expected 400"
        except urllib.error.HTTPError as e: assert e.code == 400
        req = urllib.request.Request("http://127.0.0.1:28098/api/detector?mode=world", method="POST")
        try: urllib.request.urlopen(req, timeout=3); assert False, "expected 501"
        except urllib.error.HTTPError as e: assert e.code == 501
        assert received[0] == {"cmd": "lock_point", "x": 140.0, "y": 130.0}, received
        assert received[1] == {"cmd": "detector", "mode": "world"}
        time.sleep(0.3)  # let the >=200KB J frame (sent right after the 40 small frames) finish landing
        big = urllib.request.urlopen("http://127.0.0.1:28098/stream", timeout=5)
        length = None
        for _ in range(5):
            length, body = read_mjpeg_part(big)
            if length == len(BIG_JPEG): break
        assert length == len(BIG_JPEG), f"never saw the big frame on /stream (last length={length})"
        assert body[:2] == b"\xff\xd8", body[:2]
        # Actively drain (not just sleep): the fake feed's last frame(s) may still be in flight, and a passive
        # sleep would leave that backlog sitting unread, misattributing it to the measurement window below.
        t_drain = time.time()
        while time.time() - t_drain < 1.0:
            r.readline()
        t1 = time.time(); post_lines = []
        while time.time() - t1 < 1.5:
            post_lines.append(r.readline())
        assert not any(pl.startswith(b"data: ") for pl in post_lines), post_lines
        assert any(pl.startswith(b": keepalive") for pl in post_lines), post_lines
        print("shim ok")
    finally:
        proc.terminate(); proc.wait(timeout=5)

if __name__ == "__main__":
    main()
