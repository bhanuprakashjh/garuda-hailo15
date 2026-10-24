#!/usr/bin/env python3
"""Replay every exact recorded frame through the real tracker with one initial class selection.

Uses recorded detections, appearance and camera motion; does not rerun recognition.
Original processing timestamps are preserved, never reported as candidate runtime.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
from fresh_target_score import read_recording


def replay(rows, binary, label, config=None):
    commands = [{"cmd": "target", "class": label, "now_ms": rows[0]["frame"]["capture_ms"]-1}]
    commands.extend(row["frame"] for row in rows)
    argv = [str(binary), "-"] + ([str(config)] if config else [])
    process = subprocess.run(argv,input="".join(json.dumps(c,allow_nan=False)+"\n" for c in commands),
                             capture_output=True,text=True,timeout=120,check=True)
    outputs = [json.loads(line) for line in process.stdout.splitlines()]
    if len(outputs) != len(rows)+1 or outputs[0].get("ok") is not True:
        raise ValueError("replay output/selection mismatch")
    provenance = {"kind": "actual_cpp_tracker_replay", "label_selection": label,
                  "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                  "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest() if config else None,
                  "latency_scope": "preserved original timestamps; not candidate runtime",
                  "inputs": "original detections, appearance and motion; no detector rerun"}
    result = []
    for row, out in zip(rows, outputs[1:]):
        if out["sequence"] != row["frame"]["sequence"] or out["capture_monotonic_ms"] != row["frame"]["capture_ms"]:
            raise ValueError("tracker rejected source frame correspondence")
        result.append({**{k:row[k] for k in ("recording_id","source_id","stream_id","clock_domain","nv12_sha256")},
                       **({"source_nv12_sha256":row["source_image"]["sha256"]} if "source_image" in row else {}),
                       "sequence": row["frame"]["sequence"], "capture_ms": row["frame"]["capture_ms"],
                       "detections": row["frame"]["detections"], "output": out, "provenance": provenance})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=pathlib.Path)
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--label", choices=("person","cell phone"), required=True)
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    results = replay(read_recording(args.recording),args.binary,args.label,args.config)
    with args.output.open("x") as output:
        for row in results: output.write(json.dumps(row,allow_nan=False)+"\n")
