#!/usr/bin/env bash
# Fetch Hailo's pre-compiled yolov11m for the Hailo-15L (model zoo, release line v5.3.0 = the board's HailoRT).
# Idempotent: skips the download when the file already matches the pinned md5. See models/yolov11m_h15l.md.
# LICENCE: the HEF is Hailo's compiled artifact of Ultralytics YOLO11 weights — AGPL-3.0 upstream,
# bench/eval only, not-product-cleared (CLAUDE.md §1 relaxed policy).
set -euo pipefail
URL="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/yolov11m.hef"
MD5="1d199595320154d0b62be010b9d374a7"
OUT="${1:-/media/bhanu1234/Development/hailo15/models/yolov11m_hailo15l_v5.3.0.hef}"
mkdir -p "$(dirname "$OUT")"
if [ -f "$OUT" ] && [ "$(md5sum "$OUT" | cut -c1-32)" = "$MD5" ]; then
  echo "already present and md5-verified: $OUT"; exit 0
fi
curl -fsS -m 600 -o "$OUT.part" "$URL"
GOT="$(md5sum "$OUT.part" | cut -c1-32)"
if [ "$GOT" != "$MD5" ]; then echo "md5 mismatch: got $GOT want $MD5 (zoo object changed? update the card)"; rm -f "$OUT.part"; exit 1; fi
mv "$OUT.part" "$OUT"
echo "fetched and md5-verified: $OUT"
echo "board copy: scp $OUT root@10.0.0.1:/opt/garuda/models/"
