#!/usr/bin/env python3
"""Cut one or more relative-time windows out of a timestamped SSE capture, in a single pass.

Input is `lock_metrics.py`'s format -- `"<unix_time> <json>"` per line, the M1 capture script's
output (bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py) -- and each output is the
same format, so the pieces feed straight back into `lock_metrics.py`, `rows.py`, `classify_rows.py`
and `phone_detect_stats.py`. Times are SECONDS SINCE THE CAPTURE'S FIRST ROW, matching what every
other script in this directory calls `rel`, and both bounds are inclusive.

Written for run 10e (bench/benchlog.md's "Run 10e — phone"), a 900 s capture whose one interesting
window is 15 s long: cutting every window in one pass keeps the three sub-captures on exactly the
same row boundaries as each other, which a per-window `awk` would not guarantee. Plain text only --
unlike `lock_metrics.py` this does not read `.gz`; `zcat run10e_routine5_phone.txt.gz > /tmp/r10e.txt`
first.

usage: cut_windows.py <capture> <out>:<t0>:<t1> [<out>:<t0>:<t1> ...]
       cut_windows.py /tmp/r10e.txt /tmp/A.txt:78.3:93.7 /tmp/B.txt:97.5:900
"""
import sys


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src = sys.argv[1]
    specs = []
    for spec in sys.argv[2:]:
        # rsplit so a Windows-style or otherwise colon-bearing output path still parses: only the
        # last two colons are the time bounds.
        out, t0, t1 = spec.rsplit(":", 2)
        specs.append([out, float(t0), float(t1), open(out, "w"), 0])

    first = None
    for line in open(src):
        ts = float(line.split(" ", 1)[0])
        if first is None:
            first = ts
        rel = ts - first
        for spec in specs:
            if spec[1] <= rel <= spec[2]:
                spec[3].write(line)
                spec[4] += 1

    for out, t0, t1, fh, n in specs:
        fh.close()
        print("%s: %d rows (%.1f-%.1f s)" % (out, n, t0, t1))


if __name__ == "__main__":
    main()
