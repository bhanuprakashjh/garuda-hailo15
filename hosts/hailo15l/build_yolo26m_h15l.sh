#!/usr/bin/env bash
# Recompile yolo26m for the Hailo-15L (640x640, level-2 PTQ, 1024 calib images). Runs on the PC (DFC never on-device).
# Idempotent: re-running reuses the copied weights and overwrites only work-h15l/. Takes tens of minutes on the RTX 3060.
# LICENCE: Ultralytics YOLO26 is AGPL-3.0 — bench/eval only, not-product-cleared (see CLAUDE.md §1).
set -euo pipefail
ROOT=${GARUDA_HAILO_EXPORT:-/media/bhanu1234/Development/hailo-export}
W="$ROOT/work-h15l"; mkdir -p "$W" "$ROOT/tmp"
export TMPDIR="$ROOT/tmp" XDG_CACHE_HOME="$ROOT/.cache"

# Fail-fast guard: level-2 PTQ (with QAT finetune disabled) is not a flag this script passes —
# it lives as a hand-patched string in the venv's ultralytics exporter (docs/decisions.md
# 2026-08-07 evening: "Venv exporter patch state now: level 2 + finetune disabled"). QAT finetune
# OOM'd the 6 GB RTX 3060 at every batch size tried; if the venv were ever reinstalled/reset this
# patch would silently vanish and re-enable QAT. Refuse to run rather than export unpatched.
EXPORTER=$(find "$ROOT/venv/lib" -path "*/ultralytics/engine/exporter.py" 2>/dev/null | head -1)
if [ -z "$EXPORTER" ] || \
   ! grep -q 'model_optimization_flavor(optimization_level=2)' "$EXPORTER" || \
   ! grep -q 'post_quantization_optimization(finetune, policy=disabled' "$EXPORTER"; then
  echo "ERROR: venv exporter ('$EXPORTER') is not patched to level-2 PTQ with QAT finetune" \
       "disabled (see docs/decisions.md 2026-08-07 evening). Refusing to export." >&2
  exit 1
fi

[ -f "$W/yolo26m.pt" ] || cp "$ROOT/work/yolo26m.pt" "$W/yolo26m.pt"
cd "$W"
export TF_FORCE_GPU_ALLOW_GROWTH=true MALLOC_ARENA_MAX=2
"$ROOT/venv/bin/yolo" export model=yolo26m.pt format=hailo name=hailo15l imgsz=640 data="$ROOT/datasets/depth-calib.yaml" 2>&1 | tee "$W/export_yolo26m_h15l.log"
echo "HEF + metadata in: $W/yolo26m_hailo_model/"
