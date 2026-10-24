#!/usr/bin/env python3
"""Capture the board's SSE state stream with PC-side wall-clock timestamps.
usage: sse_capture.py <url> <seconds> <outfile>   -> lines: "<unix_time> <json>"
"""
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
            n += 1
print("captured", n, "snapshots ->", out)
