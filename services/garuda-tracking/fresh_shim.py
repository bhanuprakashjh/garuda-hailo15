#!/usr/bin/env python3
"""Local Hailo fresh-tracker viewer. Node and shim MUST share CLOCK_MONOTONIC (same board)."""
import argparse
import json
import math
import pathlib
import sys
import time

# Reuse the proven feed framing/MJPEG implementation; leave the legacy shim unchanged.
try:
    import garuda_mono_shim as base
except ModuleNotFoundError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "garuda-perception" / "shim"))
    import garuda_mono_shim as base


def age_snapshot(raw, now_ms=None):
    if raw is None:
        return None
    now_ms = time.monotonic() * 1000 if now_ms is None else now_ms
    try:
        snap = json.loads(raw)
        if snap.get("tracker_contract") != "garuda.fresh.v1":
            raise ValueError("wrong tracker contract")
        capture = float(snap["capture_monotonic_ms"])
        publish = float(snap["publish_monotonic_ms"])
        budget = float(snap["freshness_budget_ms"])
        remaining = float(snap["valid_for_ms"])
        if not all(math.isfinite(x) for x in (now_ms, capture, publish, budget, remaining)):
            raise ValueError("nonfinite timestamp")
        if not 0 < budget <= 5000 or not 0 <= remaining <= budget:
            raise ValueError("invalid validity budget")
        elapsed = now_ms - publish
        valid_clock = bool(snap["timestamp_valid"]) and 0 <= capture <= publish <= now_ms
        lock = snap["lock"]
        # Two different things go stale: the FRAME (clock invalid or older than the
        # budget) and the lock's OBSERVATION (the node's remaining validity used up).
        # Only the first may overwrite the node's reason; a lock the node already
        # reports as unobserved (occluded / lost / reacquiring) keeps its reason, or
        # the identity path's diagnostics vanish behind "source_stale".
        frame_stale = not valid_clock or now_ms - capture > budget
        stale = frame_stale or elapsed > remaining
        node_observed = bool(lock.get("observation_valid"))
        snap["age_ms"] = max(0, now_ms - capture) if valid_clock else None
        snap["transport_age_ms"] = max(0, elapsed)
        snap["sample_monotonic_ms"] = now_ms
        snap["valid_for_ms"] = max(0, remaining - max(0, elapsed))
        lock["obs_age_ms"] = max(0, float(lock.get("obs_age_ms", 0)) + max(0, elapsed))
        if stale:
            snap.setdefault("image_target", {})["valid"] = False
            lock["control_valid"] = False
            lock["observation_valid"] = False
            if frame_stale or node_observed:
                lock["reason"] = "source_stale" if valid_clock else "invalid_clock"
            # Only a currently BOUND track (track_id) degrades to coasting; a lock
            # that is already lost/reacquiring keeps its state (lock.id is the
            # stable identity and stays set through loss until unlock).
            if lock.get("track_id") is not None:
                lock["state"] = "coasting"
                lock["coasting"] = True
            for track in snap.get("tracks", []):
                track["coasting"] = True
        return json.dumps(snap, allow_nan=False, separators=(",", ":")).encode()
    except (ValueError, TypeError, KeyError, OverflowError):
        return b'{"v":2,"tracks":[],"lock":{"id":null,"state":"none","control_valid":false,"observation_valid":false},"error":"invalid fresh snapshot"}'


class FreshFeed(base.Feed):
    @property
    def snap(self):
        return age_snapshot(self._raw_snap)

    @snap.setter
    def snap(self, value):
        self._raw_snap = value

    def wait_snap(self, seen, timeout=1.0):
        snap, sequence, changed = super().wait_snap(seen, timeout=min(timeout, .1))
        # Send a newly aged state even after the C++ process dies; never keep a cached true flag.
        return snap, sequence, changed or snap is not None


base.POST_MAP["/api/mono_click"][1]["sequence"] = ("sequence", int)
base.POST_MAP["/api/unlock"] = ("unlock", {})
base.POST_MAP["/api/select"] = ("select", {"id": ("id", int), "sequence": ("sequence", int)})
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"garuda-perception &mdash; board truth (this is the board's own lock)",
    b"Garuda fresh tracking &mdash; click a box to select; ambiguous or stale observations hold")
base.INDEX_HTML = base.INDEX_HTML.replace(b"st==='confirmed'", b"(st==='confirmed'||st==='tracking')")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"st==='occluded'||st==='reacquiring'", b"st==='occluded'||st==='reacquiring'||st==='coasting'||st==='ambiguous'")
base.INDEX_HTML = base.INDEX_HTML.replace(b"'FROZEN'", b"'HOLD'")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"post('/api/mono_click?x='+fx+'&y='+fy);",
    b"if(snap) post('/api/mono_click?x='+fx+'&y='+fy+'&sequence='+snap.sequence);")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"post('/api/mono_target?class=');", b"post('/api/unlock');")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"function post(u){ var r=new XMLHttpRequest(); r.open('POST',u,true); r.send(); }",
    b"""function post(u){fetch(u,{method:'POST'}).then(function(r){return r.json();}).then(function(j){
      if(!j.ok) alert(j.error||'Selection rejected');}).catch(function(){alert('Node unavailable');});}""")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"var es=new EventSource('/api/events');",
    b"""var lastEvent=0;
setInterval(function(){if(snap&&performance.now()-lastEvent>300){
  snap.lock.control_valid=false; snap.lock.observation_valid=false; snap.lock.state='coasting';
  conn.textContent='stale';draw();}},100);
var es=new EventSource('/api/events');""")
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"conn.textContent='live';", b"lastEvent=performance.now();conn.textContent='live';")


base.INDEX_HTML = base.INDEX_HTML.replace(
    b'<button id="bPerson">target: person</button>',
    b'<button id="bPerson">target: person</button><button id="bPhone">target: phone</button>')
base.INDEX_HTML = base.INDEX_HTML.replace(
    b"document.getElementById('bPerson').onclick=",
    b"document.getElementById('bPhone').onclick=function(){post('/api/mono_target?class=cell%20phone');}; document.getElementById('bPerson').onclick=")

def main():
    import fresh_tuning
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--feed-port", type=int, default=8981)
    parser.add_argument("--command-port", type=int, default=8982)
    args = parser.parse_args()
    panel = pathlib.Path(__file__).with_name("fresh_tuning.html").read_bytes()
    base.INDEX_HTML = base.INDEX_HTML.replace(b'<div id="wrap">', b'<main id="bench-layout"><section id="video-pane" aria-label="Live tracking video"><div id="wrap">')
    base.INDEX_HTML = base.INDEX_HTML.replace(b'<pre id="s" hidden></pre>', b'<pre id="s" hidden></pre></section>' + panel + b'</main>')
    feed = FreshFeed("127.0.0.1", args.feed_port)
    server = base.ShimHTTPServer(("0.0.0.0", args.port), fresh_tuning.handler(base.make_handler(
        feed, base.Commands("127.0.0.1", args.command_port)), fresh_tuning.Tuning(feed)))
    server.daemon_threads = True
    print(f"fresh tracker viewer on :{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
