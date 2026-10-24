"""Capture a golden tiles session for offline replay: per unique node frame,
record the full raw per-tile detections, node capture/publish timestamps, the
freshness budget, all tracks with boxes, and the lock. Deduplicated by the
node's frame sequence so the offline harness sees each frame once.

Poll :8099 fast; the node publishes ~7.5 fps in tiles mode, so 10 Hz catches
essentially every unique sequence. Auto-stops after enough frames + a lock +
a loss/re-acquire cycle, or on timeout.
"""
import json
import sys
import time
import urllib.request

out_path = sys.argv[1]
timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
seen = set()
rows = []
saw_lock = False
saw_lost_after_lock = False
saw_reacquire_after_lost = False
t0 = time.monotonic()
while time.monotonic() - t0 < timeout_s:
    try:
        s = json.load(urllib.request.urlopen('http://10.0.0.1:8099/api/state', timeout=2))
        seq = s.get('sequence')
        if seq is not None and seq not in seen and s.get('accepted'):
            seen.add(seq)
            dt = s.get('diag', {}).get('detection_tiles', {})
            L = s['lock']
            rows.append(dict(sequence=seq,
                capture_monotonic_ms=s.get('capture_monotonic_ms'),
                publish_monotonic_ms=s.get('publish_monotonic_ms'),
                freshness_budget_ms=s.get('freshness_budget_ms'),
                raw=dt.get('raw') or [], reason=dt.get('reason'),
                inference_ms=dt.get('inference_ms'),
                tracks=[{'id': t['id'], 'label': t['label'], 'conf': t['conf'],
                         'coasting': t.get('coasting'),
                         'x': t['x'], 'y': t['y'], 'w': t['w'], 'h': t['h']} for t in s['tracks']],
                lock={'id': L['id'], 'track_id': L.get('track_id'), 'state': L['state'],
                      'reason': L['reason'], 'control_valid': L['control_valid']}))
            if L['id'] is not None:
                saw_lock = True
            if saw_lock and L['state'] == 'lost':
                saw_lost_after_lock = True
            if saw_lost_after_lock and L['state'] in ('reacquiring', 'tracking') and L['id'] is not None:
                saw_reacquire_after_lost = True
        # Enough for a full offline replay: a lock, a loss, a re-acquire, and >200 frames.
        if saw_reacquire_after_lost and len(rows) > 200:
            break
    except Exception:
        pass
    time.sleep(0.1)
with open(out_path, 'w') as f:
    for r in rows:
        f.write(json.dumps(r) + '\n')
person_frames = sum(1 for r in rows if any(t['label'] == 'person' for t in r['tracks'])
                    or any(d['label'] == 'person' for d in r['raw']))
print(json.dumps(dict(frames=len(rows), person_frames=person_frames, saw_lock=saw_lock,
                      saw_lost=saw_lost_after_lock, saw_reacquire=saw_reacquire_after_lost,
                      out=out_path)))
