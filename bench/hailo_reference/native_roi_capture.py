"""Record the node's target-ROI diagnostics per unique frame for the native-crop A/B.

Polls the fresh shim's state at 10 Hz (the node publishes at most ~25 fps, so a few
frames may be skipped; every recorded row is one real node frame, deduplicated by
sequence). Rows keep what `score_native_roi_capture.py` needs: the ROI source and
region, the best confidence the crop gave the locked target, the paired-copy
comparison the compare profile runs on the same exposure, pairing statistics, the
lock state and box, and the frame age. Nothing is interpreted here.

usage: native_roi_capture.py OUT.jsonl [timeout_s=300] [host=10.0.0.1]
"""
import json
import signal
import sys
import time
import urllib.request

out_path = sys.argv[1]
timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
host = sys.argv[3] if len(sys.argv) > 3 else '10.0.0.1'
seen, rows, t0, stop = set(), [], time.monotonic(), False


def _stop(signum, frame):   # rows are flushed as they arrive; a signal just ends the session cleanly
    global stop
    stop = True


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)
out = open(out_path, 'w')
while not stop and time.monotonic() - t0 < timeout_s:
    try:
        s = json.load(urllib.request.urlopen(f'http://{host}:8099/api/state', timeout=2))
        seq = s.get('sequence')
        if seq is not None and seq not in seen and s.get('accepted'):
            seen.add(seq)
            d = s.get('diag', {})
            lock = s.get('lock', {})
            row = dict(sequence=seq, wall=time.time(), capture_monotonic_ms=s.get('capture_monotonic_ms'),
                       publish_monotonic_ms=s.get('publish_monotonic_ms'), age_ms=s.get('age_ms'),
                       target_roi=d.get('target_roi'), native_pairing=d.get('native_pairing'),
                       source_pairing=d.get('source_pairing'), person_embedding=d.get('person_embedding'),
                       detector_passes=(d.get('detection_tiles') or {}).get('detector_passes_this_frame'),
                       lock={k: lock.get(k) for k in ('id', 'track_id', 'state', 'reason', 'control_valid', 'box',
                                                       'identity_best_distance', 'identity_runner_up_distance')},
                       tracks=[{k: t.get(k) for k in ('id', 'label', 'conf', 'x', 'y', 'w', 'h')} for t in s.get('tracks', [])])
            rows.append(row)
            out.write(json.dumps(row) + '\n')
            out.flush()
    except Exception:
        pass
    time.sleep(0.1)
out.close()
locked = sum(1 for r in rows if r['lock']['id'] is not None)
roi = sum(1 for r in rows if (r['target_roi'] or {}).get('reason') == 'inferred')
compared = sum(1 for r in rows if ((r['target_roi'] or {}).get('compare_paired') or {}).get('region'))
print(json.dumps(dict(frames=len(rows), locked_frames=locked, roi_frames=roi, compared_frames=compared, out=out_path)))
