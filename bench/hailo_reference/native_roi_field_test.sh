#!/usr/bin/env bash
# Field test of the native-pixel crop: start the compare profile on the board, record the
# console state for DURATION seconds while the operator locks a person at distance, restore the
# desk profile, and print the per-target-height table (native vs paired-copy confidence).
# Needs a network path PC -> board (10.0.0.1 by default). Nothing here arms or commands anything.
# usage: native_roi_field_test.sh OUT_DIR [DURATION_S=600] [PROFILE=start-follow-native-compare]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:?OUT_DIR required}"; DURATION="${2:-600}"; PROFILE="${3:-start-follow-native-compare}"
HOST="${GARUDA_H15L_HOST:-root@10.0.0.1}"
mkdir -p "$OUT"
[ -e "$OUT/capture.jsonl" ] && { echo "$OUT already holds a capture; use a new directory" >&2; exit 2; }
bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" stop || true
bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" "$PROFILE"
ssh -o BatchMode=yes "$HOST" 'sha256sum /opt/garuda-fresh/garuda-fresh-tracking; cat /opt/garuda-fresh/current.json' > "$OUT/board.txt"
echo "Recording $DURATION s from ${HOST#*@}:8099 ($PROFILE). Lock a person at distance now; walk, step out and return."
python3 "$ROOT/bench/hailo_reference/native_roi_capture.py" "$OUT/capture.jsonl" "$DURATION" "${HOST#*@}" | tee "$OUT/capture-summary.json"
bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" stop || true
bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" start-follow
python3 "$ROOT/bench/hailo_reference/score_native_roi_capture.py" "$OUT/capture.jsonl" --bands --out "$OUT/score.json" | tail -n +1
echo "Evidence in $OUT (capture.jsonl, score.json, board.txt); desk profile restored."
