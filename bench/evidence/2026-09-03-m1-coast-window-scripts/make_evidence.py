#!/usr/bin/env python3
"""Assemble bench/evidence/2026-09-03-m1-coast-window.txt from the two captures (person rows + episode lists)."""
import subprocess, sys, pathlib
E = pathlib.Path(__file__).resolve().parent
def timeline(name):
    out = subprocess.run([sys.executable, str(E / "timeline.py"), str(E / name)], capture_output=True, text=True, check=True).stdout
    rows = out.split("--- coasting")[0].splitlines()
    person_rows = [r for r in rows if "'face'" not in r or "lock=" in r and "(coasting)" in r]
    episodes = "--- coasting" + out.split("--- coasting", 1)[1]
    return person_rows, episodes
parts = ["# Coast-window validation on the Hailo-15L SBC, 2026-09-03, owner present at the bench.",
         "# Capture: sse_capture.py = PC-side wall-clock timestamp per SSE snapshot from http://10.0.0.1:8098/api/events",
         "# (shim cap 10 Hz, so times are +-0.1 s). timeline.py prints each change of (lock id, lock coasting, track ids,",
         "# coasting ids) relative to the first snapshot, then every coasting episode of the LOCKED track and its outcome.",
         "# Routine performed by the owner each time: in view 5 s; out ~1 s; back 5 s; out ~3 s; back 5 s; out ~10 s; back.",
         "# Rows are filtered to changes involving a person track (face-only changes dropped) to keep the file short.", ""]
for title, name in [("## BEFORE — node b0ea29b, config track.max_lost=25 reacq=5 (mono's values), 150 s capture started 10:45:35 local", "before.txt"),
                    ("## AFTER — same node binary, config track.max_lost=75 reacq=15 (deployed 10:48), 240 s capture started 10:53:04 local", "after2.txt")]:
    rows, ep = timeline(name)
    parts += [title, "$ python3 timeline.py " + name, *rows, ep.rstrip(), ""]
parts += ["## AFTER (first attempt, discarded): 150 s capture started 10:48:44 — the person track never coasted (owner did not leave",
          "## the frame within the window; the lock changed id only after the capture ended). Kept in the scratchpad as after.txt.", ""]
(pathlib.Path(sys.argv[1])).write_text("\n".join(parts))
print("wrote", sys.argv[1], sum(len(p) for p in parts), "chars")
