"""Record the follow console's state per unique board frame while a demo runs.

Polls http://HOST:PORT/api/state at 10 Hz, keeps one row per board output sequence, and
flushes rows as they arrive so a signal or timeout never loses the session. Rows carry what
a demo verification needs: the board profile and schedule the console reports, the lock and
its control validity, receiver age and the freshness verdict, the requested heading and
the command the PC decided on. Nothing is interpreted here.

usage: console_capture.py OUT.jsonl [timeout_s=300] [host=127.0.0.1] [port=8100]
"""
import json
import signal
import sys
import time
import urllib.request

out_path = sys.argv[1]
timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
host = sys.argv[3] if len(sys.argv) > 3 else '127.0.0.1'
port = int(sys.argv[4]) if len(sys.argv) > 4 else 8100
seen, rows, t0, stop = set(), [], time.monotonic(), False


def _stop(signum, frame):
    global stop
    stop = True


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)
out = open(out_path, 'w')
while not stop and time.monotonic() - t0 < timeout_s:
    try:
        s = json.load(urllib.request.urlopen(f'http://{host}:{port}/api/state', timeout=2))
        o = s.get('output') or {}
        seq = o.get('sequence')
        if seq is not None and seq not in seen:
            seen.add(seq)
            lock = o.get('lock') or {}
            row = dict(sequence=seq, wall=time.time(), pixel_source=s.get('pixel_source'),
                       board_profile=s.get('board_profile'), board_schedule=s.get('board_schedule'),
                       detector_passes=s.get('detector_passes'), inference_ms=s.get('inference_ms'),
                       receiver_age_ms=s.get('receiver_age_ms'), command=s.get('command'), reason=s.get('reason'),
                       follow_enabled=s.get('follow_enabled'), flight=s.get('flight'),
                       heading_deg=s.get('heading_deg'), requested_heading_deg=s.get('requested_heading_deg'),
                       requested_setpoint=s.get('requested_setpoint'),
                       lock={k: lock.get(k) for k in ('id', 'track_id', 'state', 'reason', 'control_valid', 'observation_valid',
                                                       'box', 'obs_age_ms', 'identity_retained')},
                       tracks=len(o.get('tracks') or []), raw_detections=len(s.get('raw_detections') or []))
            rows.append(row)
            out.write(json.dumps(row) + '\n')
            out.flush()
    except Exception:
        pass
    time.sleep(0.1)
out.close()
print(json.dumps(dict(frames=len(rows), locked=sum(1 for r in rows if r['lock']['id'] is not None),
                      control_valid=sum(1 for r in rows if r['lock']['control_valid']),
                      follow_commands=sum(1 for r in rows if r['command'] == 'FOLLOW'), out=out_path)))
