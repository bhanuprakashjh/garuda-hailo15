#!/usr/bin/env python3
"""Tally person-tracking stats from one or more PC-side timestamped SSE captures
(bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py output: "<unix_time> <json>"
per line, http://10.0.0.1:8098/api/events, shim cap 10 Hz).

Columns: span (s), person ids (distinct ids of person-labelled tracks), lock id sequence
(chronological list of distinct consecutive non-null lock.id values, collapsing consecutive
repeats and coalescing across coasting so a coasting id that returns live is not counted twice;
a run of lock.id == None is shown as "None"), live-person states (snapshots with >=1 person
track that is not coasting) and their % of n, no-person states (snapshots with zero
person-labelled tracks, live or coasting), lock coasting (snapshots with lock.coasting true),
lock None (snapshots with lock.id is null), x range (min/max box x of person-labelled tracks,
live + coasting; a capture with zero person-labelled tracks prints "n/a" for both bounds instead
of a fake [0, 0] range), age max (ms, from the snapshot's own age_ms field).

usage: compare_person_runs.py <label> <file> [<label> <file> ...]
"""
import gzip
import json
import sys

LABEL = "person"


def load(path):
    rows = []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            t, _, js = line.partition(" ")
            rows.append((float(t), json.loads(js)))
    return rows


def tally(name, path):
    rows = load(path)
    if not rows:
        print(name, "EMPTY CAPTURE")
        return
    n = len(rows)
    span = rows[-1][0] - rows[0][0]

    person_ids = set()
    live_states = 0
    no_person_states = 0
    lock_coasting = 0
    lock_none = 0
    xs = []
    age_max = 0

    lock_seq = []
    prev_lock = "__unset__"

    for t, d in rows:
        age_max = max(age_max, d.get("age_ms", 0))
        lid = d["lock"]["id"]
        if lid is None:
            lock_none += 1
        if d["lock"]["coasting"]:
            lock_coasting += 1
        if lid != prev_lock:
            lock_seq.append(lid)
            prev_lock = lid

        person_tracks = [tr for tr in d["tracks"] if tr["label"] == LABEL]
        if not person_tracks:
            no_person_states += 1
        live_here = False
        for tr in person_tracks:
            person_ids.add(tr["id"])
            xs.append(tr["x"])
            if not tr["coasting"]:
                live_here = True
        if live_here:
            live_states += 1

    # xs is empty iff there is not a single person-labelled track entry anywhere in the capture
    # (person_ids is then also empty) -- print "n/a" for the x range, don't fake a [0, 0] range.
    x_range_s = "[%7d, %7d]" % (int(min(xs)), int(max(xs))) if xs else "[    n/a,    n/a]"
    seq_str = " -> ".join(str(v) for v in lock_seq)
    print(
        "%-20s n=%-5d %5.1fs | person ids %3d | live-person states %4d (%2d%%) | "
        "no-person states %4d | lock coasting %4d | lock None %4d | x range %s | "
        "age max %4d"
        % (
            name,
            n,
            span,
            len(person_ids),
            live_states,
            int(100.0 * live_states / n),
            no_person_states,
            lock_coasting,
            lock_none,
            x_range_s,
            age_max,
        )
    )
    print("%-20s lock id sequence: %s" % (name, seq_str))


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) % 2 != 0 or not args:
        sys.exit(__doc__)
    for i in range(0, len(args), 2):
        tally(args[i], args[i + 1])
