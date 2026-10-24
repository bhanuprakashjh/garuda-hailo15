#!/usr/bin/env python3
"""Trim a timestamped SSE capture to the active window: from <margin> s before the first row
with any track (or lock) to <margin> s after the last such row.
usage: trim_capture.py <in> <out> [margin_s=3]"""
import json, sys

src, dst = sys.argv[1], sys.argv[2]
margin = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
rows = []
for line in open(src):
    ts, _, js = line.partition(" ")
    rows.append((float(ts), line))
active = [ts for ts, line in rows if '"tracks":[]' not in line or '"identity_locked":true' in line]
if not active:
    print("no active rows; nothing written")
    sys.exit(1)
t0, t1 = active[0] - margin, active[-1] + margin
kept = [line for ts, line in rows if t0 <= ts <= t1]
open(dst, "w").writelines(kept)
print("kept %d of %d rows, %.1f s active window -> %s" % (len(kept), len(rows), active[-1] - active[0], dst))
