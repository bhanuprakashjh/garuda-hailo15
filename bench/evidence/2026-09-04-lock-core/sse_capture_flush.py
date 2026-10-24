#!/usr/bin/env python3
"""Same as bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py but flushes every
line, so a capture stopped early (SIGTERM) keeps everything up to the last row.
usage: sse_capture_flush.py <url> <seconds> <outfile>"""
import sys, time, urllib.request

url, secs, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
t_end = time.time() + secs
n = 0
with urllib.request.urlopen(url, timeout=10) as r, open(out, "w") as f:
    while time.time() < t_end:
        line = r.readline()
        if not line:
            break
        if line.startswith(b"data: "):
            f.write("%.3f %s\n" % (time.time(), line[6:].decode().strip()))
            f.flush()
            n += 1
print("captured", n, "snapshots ->", out)
