#!/usr/bin/env python3
"""garuda-mono-shim: presents garuda-mono's HTTP contract (port 8098) on top of garuda-perception's local feed.
Standard library only (the board has no numpy/pyzmq). See docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md §4.
"""
import argparse, json, socket, socketserver, struct, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SSE_MAX_HZ = 30.0
# On-board fix round 9: 15 -> 30. The node encodes at jpeg_fps 30 in every demo config, so the shim
# was discarding half the frames it was handed and the viewer saw a 15 fps stream of a 30 fps
# pipeline -- which is also half the temporal evidence when judging whether the lock is jumpy.
MJPEG_MAX_FPS = 30.0

# On-board fix round 9 (Ruling 31) -- THE BOARD-TRUTH VIEWER.
#
# Until this round "/" was a debug page: a raw MJPEG <img> and a JSON dump, no boxes and no click.
# The owner has therefore been judging the lock on the PC portal (:8080), which runs its OWN
# ByteTrack over the board's tracks and keeps its own target -- so nobody has yet SEEN what the
# board's lock core actually publishes. This page is the one place that shows exactly that, and
# nothing else: the boxes are drawn from the node's own snapshot, the lock box is LockCore's own
# published box, and clicking sends the click straight to the node's lock_point command.
#
# Constraints, all deliberate: no external resources of any kind (it has to work over an SSH tunnel
# on a board with no internet), plain JS with no framework, and redraw driven by the SSE stream
# (30 Hz) rather than by polling. The overlay canvas is sized to the DISPLAYED image and rescaled on
# every resize, so frame pixels (1280x720, or whatever the snapshot's `frame` says) map correctly at
# any window size. The MJPEG <img> and the SSE snapshots are independent streams, so the overlay can
# lead or lag the picture by a frame -- stated here rather than papered over.
INDEX_HTML = b"""<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<title>garuda board truth</title>
<style>
 body{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0d0f12;color:#dfe3e8;margin:0;padding:10px}
 h1{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#8b95a1;margin:0 0 8px}
 #wrap{position:relative;display:inline-block;max-width:100%;line-height:0}
 #v{display:block;max-width:100%;height:auto}
 #c{position:absolute;left:0;top:0;cursor:crosshair}
 #hud{margin:8px 0 0;font-size:13px;white-space:pre-wrap;line-height:1.5}
 .bar{margin:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 button{font:inherit;font-size:12px;background:#1b2027;color:#dfe3e8;border:1px solid #333b45;
        border-radius:4px;padding:5px 10px;cursor:pointer}
 button:hover{background:#232a33}
 pre{background:#14181d;border:1px solid #222a32;border-radius:4px;padding:8px;font-size:11px;
     overflow:auto;max-height:45vh;line-height:1.4}
</style>
<h1>garuda-perception &mdash; board truth (this is the board's own lock)</h1>
<div class="bar">
  <button id="bPerson">target: person</button>
  <button id="bClear">clear target</button>
  <button id="bRaw">raw &#9662;</button>
  <span id="conn" style="font-size:12px;color:#8b95a1">connecting&hellip;</span>
</div>
<div id="wrap"><img id="v" src="/stream" alt="stream"><canvas id="c"></canvas></div>
<div id="hud">no snapshot yet</div>
<pre id="s" hidden></pre>
<script>
"use strict";
var img=document.getElementById('v'), cv=document.getElementById('c'), ctx=cv.getContext('2d');
var hud=document.getElementById('hud'), raw=document.getElementById('s'), conn=document.getElementById('conn');
var snap=null;

// Frame -> display scale. The snapshot carries the node's own frame size; 1280x720 is the fallback
// for a row that predates the `frame` object.
function frameSize(){
  var f=(snap&&snap.frame)||{}; return [f.width||1280, f.height||720];
}
function fit(){
  var w=img.clientWidth||img.naturalWidth||1280, h=img.clientHeight||img.naturalHeight||720;
  if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
  draw();
}
function box(x,y,w,h,sx,sy){ return [x*sx,y*sy,w*sx,h*sy]; }

function draw(){
  ctx.clearRect(0,0,cv.width,cv.height);
  if(!snap) return;
  var fs=frameSize(), sx=cv.width/fs[0], sy=cv.height/fs[1];
  ctx.font='11px ui-monospace,Menlo,Consolas,monospace';
  ctx.textBaseline='bottom';

  // Every published track: thin, dashed while coasting.
  var tr=snap.tracks||[];
  for(var i=0;i<tr.length;i++){
    var t=tr[i], b=box(t.x,t.y,t.w,t.h,sx,sy);
    ctx.setLineDash(t.coasting?[4,3]:[]);
    ctx.lineWidth=1;
    ctx.strokeStyle=t.coasting?'#6c7683':'#7fb4ff';
    ctx.strokeRect(b[0],b[1],b[2],b[3]);
    var lab=t.label+' '+t.id+' '+(Math.round(t.conf*100)/100);
    ctx.fillStyle=t.coasting?'#6c7683':'#7fb4ff';
    ctx.fillText(lab,b[0]+2,b[1]-2);
  }
  ctx.setLineDash([]);

  // The lock: LockCore's OWN box, thick, coloured by state. lost/none draw nothing at all -- that
  // is the contract (the core publishes no box in those states), not an omission by this page.
  var lk=snap.lock||{}, st=lk.state||'none', col=null, frozen=false;
  if(st==='confirmed'){col='#31d158';}
  else if(st==='occluded'||st==='reacquiring'){col='#ffb020';frozen=true;}
  if(col&&lk.box){
    var lb=box(lk.box.x,lk.box.y,lk.box.w,lk.box.h,sx,sy);
    ctx.lineWidth=3; ctx.strokeStyle=col; ctx.strokeRect(lb[0],lb[1],lb[2],lb[3]);
    if(frozen){
      ctx.fillStyle=col; ctx.font='bold 12px ui-monospace,Menlo,Consolas,monospace';
      ctx.fillText('FROZEN',lb[0]+3,lb[1]+lb[3]+14);
    }
  }

  var q=(lk.quality===undefined)?'-':(Math.round(lk.quality*1000)/1000);
  var age=(lk.obs_age_ms===undefined)?'-':Math.round(lk.obs_age_ms);
  var line=st+' \\u00b7 '+(lk.class||'-')+' \\u00b7 id '+(lk.id===null||lk.id===undefined?'-':lk.id)+
           ' \\u00b7 epoch '+(lk.epoch===undefined?'-':lk.epoch)+' \\u00b7 q='+q+' \\u00b7 age='+age+'ms'+
           ' \\u00b7 control_valid='+(lk.control_valid===undefined?'n/a':lk.control_valid);
  var d=snap.diag;
  if(d) line+='\\n diag raw='+d.raw_dets+' sdk='+d.sdk_tracks+' live_raw='+d.live_raw+
              ' published='+d.published+' core='+d.core_candidates+
              '   snapshot age='+(snap.age_ms===null||snap.age_ms===undefined?'-':snap.age_ms)+'ms';
  hud.textContent=line;
  hud.style.color=col||'#8b95a1';
  if(!raw.hidden) raw.textContent=JSON.stringify(snap,null,1);
}

function post(u){ var r=new XMLHttpRequest(); r.open('POST',u,true); r.send(); }

cv.addEventListener('click',function(e){
  var r=cv.getBoundingClientRect(), fs=frameSize();
  var fx=Math.round((e.clientX-r.left)*fs[0]/(r.width||1));
  var fy=Math.round((e.clientY-r.top)*fs[1]/(r.height||1));
  post('/api/mono_click?x='+fx+'&y='+fy);
});
document.getElementById('bPerson').onclick=function(){post('/api/mono_target?class=person');};
document.getElementById('bClear').onclick=function(){post('/api/mono_target?class=');};
document.getElementById('bRaw').onclick=function(){raw.hidden=!raw.hidden;draw();};

var es=new EventSource('/api/events');
es.onmessage=function(e){
  try{snap=JSON.parse(e.data);}catch(_){return;}
  conn.textContent='live';
  fit();
};
es.onerror=function(){conn.textContent='reconnecting\\u2026';};
img.addEventListener('load',fit);
window.addEventListener('resize',fit);
fit();
</script>"""

def recv_exact(sock, n):
    """Read exactly n bytes; returns b'' on EOF. Never rely on MSG_WAITALL: with a timeout set, CPython's recv returns short."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            return b""
        buf += chunk
    return bytes(buf)

class Feed:
    """Reconnecting reader of the framed feed; keeps the latest snapshot and JPEG."""
    def __init__(self, host, port):
        self.host, self.port = host, port; self.lock = threading.Lock(); self.cv = threading.Condition(self.lock)
        self.snap = None; self.snap_seq = 0; self.jpeg = None; self.jpeg_seq = 0
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        while True:
            try:
                with socket.create_connection((self.host, self.port), timeout=5) as s:
                    s.settimeout(5.0)
                    while True:
                        try:
                            t = recv_exact(s, 1); hdr = recv_exact(s, 4)
                            if len(t) != 1 or len(hdr) != 4: break
                            ln = struct.unpack(">I", hdr)[0]
                            if ln > 16 * 1024 * 1024: break
                            p = recv_exact(s, ln)
                            if len(p) != ln: break
                        except socket.timeout:
                            break
                        with self.cv:
                            if t == b"S": self.snap = p; self.snap_seq += 1
                            elif t == b"J": self.jpeg = p; self.jpeg_seq += 1
                            self.cv.notify_all()
            except OSError:
                pass
            time.sleep(0.5)
    def wait_snap(self, seen, timeout=1.0):
        with self.cv:
            changed = self.cv.wait_for(lambda: self.snap_seq != seen, timeout); return self.snap, self.snap_seq, changed
    def wait_jpeg(self, seen, timeout=1.0):
        with self.cv:
            changed = self.cv.wait_for(lambda: self.jpeg_seq != seen, timeout); return self.jpeg, self.jpeg_seq, changed

class Commands:
    def __init__(self, host, port): self.host, self.port = host, port; self.lock = threading.Lock(); self.sock = None; self.rfile = None
    def call(self, obj):
        with self.lock:
            last_err = "node unreachable"
            for attempt in (1, 2):
                try:
                    if self.sock is None:
                        self.sock = socket.create_connection((self.host, self.port), timeout=3)
                        self.rfile = self.sock.makefile("r")
                    self.sock.sendall((json.dumps(obj) + "\n").encode())
                    line = self.rfile.readline()
                    if not line: raise OSError("closed")
                    return json.loads(line)
                except (OSError, ValueError) as e:
                    if isinstance(e, ValueError): last_err = "bad reply"
                    try:
                        if self.rfile is not None: self.rfile.close()
                    except Exception: pass
                    try:
                        if self.sock is not None: self.sock.close()
                    except Exception: pass
                    self.sock = None; self.rfile = None
                    if attempt == 2: return {"ok": False, "error": last_err}

POST_MAP = {  # path -> (cmd, {query key: (json key, type)})
    "/api/mono_click": ("lock_point", {"x": ("x", float), "y": ("y", float)}),
    "/api/mono_target": ("target", {"class": ("class", str)}),
    "/api/mono_calibrate": ("cal_add", {"true_m": ("true_m", float)}),
    "/api/mono_calibrate_reset": ("cal_reset", {}),
    "/api/detector": ("detector", {"mode": ("mode", str)}),
    "/api/depth_engine": ("depth_engine", {"engine": ("engine", str)}),
}

def make_handler(feed, cmds):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *a): pass
        def _json(self, code, body):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            p = urlparse(self.path).path
            if p == "/": self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(INDEX_HTML))); self.end_headers(); self.wfile.write(INDEX_HTML); return
            if p == "/api/state":
                return self._json(200, feed.snap or b'{"v":2,"tracks":[],"error":"no snapshot yet"}')
            if p == "/api/events":
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*"); self.close_connection = True; self.end_headers()
                seen = 0; min_gap = 1.0 / SSE_MAX_HZ; last = 0.0
                try:
                    while True:
                        snap, seen, changed = feed.wait_snap(seen, timeout=1.0)
                        if not changed: self.wfile.write(b": keepalive\n\n"); self.wfile.flush(); continue
                        gap = time.monotonic() - last
                        if gap < min_gap: time.sleep(min_gap - gap)
                        self.wfile.write(b"data: " + snap + b"\n\n"); self.wfile.flush(); last = time.monotonic()
                except (BrokenPipeError, ConnectionResetError): return
            if p == "/stream":
                self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.close_connection = True; self.end_headers()
                seen = 0; min_gap = 1.0 / MJPEG_MAX_FPS; last = 0.0
                try:
                    while True:
                        jpg, seen, changed = feed.wait_jpeg(seen, timeout=1.0)
                        if not changed: continue
                        gap = time.monotonic() - last
                        if gap < min_gap: time.sleep(min_gap - gap)
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"); self.wfile.flush(); last = time.monotonic()
                except (BrokenPipeError, ConnectionResetError): return
            self._json(404, {"error": "not found"})
        def do_POST(self):
            u = urlparse(self.path); q = parse_qs(u.query, keep_blank_values=True)
            if u.path not in POST_MAP: return self._json(404, {"error": "not found"})
            cmd, spec = POST_MAP[u.path]; obj = {"cmd": cmd}
            try:
                for qk, (jk, typ) in spec.items():
                    if qk in q: obj[jk] = typ(q[qk][0])
            except ValueError:
                return self._json(400, {"ok": False, "error": f"bad value for {qk}"})
            rep = cmds.call(obj)
            if rep.get("ok"): return self._json(200, rep)
            code = 501 if cmd in ("detector", "depth_engine", "cal_add") else 400
            return self._json(code, rep)
    return H

class ShimHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer without the reverse-DNS lookup HTTPServer.server_bind does on the bound address
    (socket.getfqdn) — that lookup can stall for seconds on a host with an unreachable resolver."""
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = "garuda-mono-shim"
        self.server_port = port

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--feed", default="127.0.0.1:8971"); ap.add_argument("--cmd", default="127.0.0.1:8972"); ap.add_argument("--port", type=int, default=8098)
    a = ap.parse_args(); fh, fp = a.feed.split(":"); ch, cp = a.cmd.split(":")
    srv = ShimHTTPServer(("0.0.0.0", a.port), make_handler(Feed(fh, int(fp)), Commands(ch, int(cp)))); srv.daemon_threads = True
    print(f"garuda-mono-shim on :{a.port} (feed {a.feed}, cmd {a.cmd})", flush=True); srv.serve_forever()

if __name__ == "__main__": main()
