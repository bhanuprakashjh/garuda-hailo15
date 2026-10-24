#!/usr/bin/env bash
# Idempotent deploy of garuda-perception to the Hailo-15L SBC. Usage: hosts/hailo15l/deploy.sh [--no-restart]
set -euo pipefail
HOST=${GARUDA_H15L_HOST:-root@10.0.0.1}
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$ROOT/services/garuda-perception"
BIN="$SVC/build-h15l/garuda-perception"
# libjpeg-turbo runtime (IJG/BSD-3 licence): the board image lacks libturbojpeg.so.0; the SDK sysroot has it.
SDK_LIB="/media/bhanu1234/Development/hailo15/sdk/sysroots/armv8a-poky-linux/usr/lib/libturbojpeg.so.0.2.0"
# yolo26m model + its post-process plugin/config (Task 4, M2). PC-side HEF cache is outside the repo;
# models/fetch_yolo26m_h15l.sh re-fetches it there if missing (md5-verified).
POST_SO="$SVC/build-h15l/postprocess/libyolo26_post.so"
POST_CFG="$SVC/config/yolo26_post.json"
HEF_PC="/media/bhanu1234/Development/hailo15/models/yolo26m_hailo15l_v5.3.0.hef"
HEF_MD5="3aef604ab89ddaf9ecb4cefa9c6ea8af"
# Which perception.json lands on the board: default yolo26m; set to config/perception-yolov8n.json
# to roll back to the stock detector. Whatever its source filename, it always lands as
# /opt/garuda/perception.json.
CFG="${GARUDA_PERCEPTION_CONFIG:-$SVC/config/perception.json}"
[ -x "$BIN" ] || { echo "build first: see services/garuda-perception/README.md (cross build)"; exit 1; }
[ -f "$SDK_LIB" ] || { echo "SDK sysroot missing libturbojpeg: $SDK_LIB"; exit 1; }
[ -f "$CFG" ] || { echo "config not found: $CFG"; exit 1; }
[ -f "$POST_SO" ] || { echo "postprocess plugin not built: $POST_SO (cross build first)"; exit 1; }
[ -f "$POST_CFG" ] || { echo "postprocess config missing: $POST_CFG"; exit 1; }

# The yolo26m HEF is only needed when the SELECTED config actually references one under
# /opt/garuda/models/ (config/perception.json, the default). The rollback config
# (config/perception-yolov8n.json) points "hef" at a path already baked into the board's stock
# image (/home/root/apps/shared/resources/...) — for that config the HEF requirement and copy step
# below are skipped entirely, so rollback deploys never need the (large, PC-cached-only) yolo26m
# HEF present at all.
CFG_HEF="$(grep -o '"hef"[[:space:]]*:[[:space:]]*"[^"]*"' "$CFG" | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/')"
case "$CFG_HEF" in
  /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef) NEED_HEF=1 ;;   # the pinned, PC-cached model: verified + copied below
  /opt/garuda/models/*) NEED_HEF=2 ;;                              # another model under /opt/garuda/models (e.g. the yolov8m/yolov11m/yolov11s A/B): must already be on the board
  *) NEED_HEF=0 ;;
esac
if [ "$NEED_HEF" = 2 ]; then
  ssh "$HOST" "test -f '$CFG_HEF'" || { echo "selected config's hef ($CFG_HEF) is not on the board — copy it to /opt/garuda/models/ first"; exit 1; }
  echo "selected config's hef ($CFG_HEF) is present on the board (not the pinned yolo26m — no md5 check, no copy)"
fi
if [ "$NEED_HEF" = 1 ]; then
  [ -f "$HEF_PC" ] || { echo "yolo26m HEF not cached on the PC: $HEF_PC (run models/fetch_yolo26m_h15l.sh)"; exit 1; }
  # Verify the PC-side cache's integrity against the pinned md5 BEFORE any scp — a corrupted or
  # stale cache must fail fast here, not partway through a board deploy.
  PC_HEF_MD5="$(md5sum "$HEF_PC" | cut -c1-32)"
  if [ "$PC_HEF_MD5" != "$HEF_MD5" ]; then
    echo "yolo26m HEF on the PC does not match the pinned md5: $HEF_PC is $PC_HEF_MD5, expected $HEF_MD5 (re-run models/fetch_yolo26m_h15l.sh)"
    exit 1
  fi
elif [ "$NEED_HEF" = 0 ]; then
  echo "selected config's hef ($CFG_HEF) is not under /opt/garuda/models/ — skipping yolo26m HEF requirement and copy"
fi

# Board has no RTC/NTP (boots reading 2018) -- set its clock from the PC on every deploy. Not
# persistent across reboot; that is expected.
ssh "$HOST" "date -s @$(date +%s)"

# Stop before copy: overwriting a running binary fails with "text file busy". Stop the service if
# its init script is already installed, then anchor-kill any hand-started stragglers from earlier
# manual runs. Anchored (never -x, never an unanchored -f) so this can't hit an unrelated process.
ssh "$HOST" '
  [ -x /etc/init.d/garuda-perception ] && /etc/init.d/garuda-perception stop
  pkill -f "^\./bin/garuda-perception" || true
  pkill -f "^/opt/garuda/bin/garuda-perception" || true
  pkill -f "^python3 bin/garuda_mono_shim\.py" || true
  pkill -f "^/usr/bin/python3 /opt/garuda/bin/garuda_mono_shim\.py" || true
  for i in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "^\./bin/garuda-perception" >/dev/null 2>&1 || pgrep -f "^/opt/garuda/bin/garuda-perception" >/dev/null 2>&1 || break
    sleep 0.5
  done
  pkill -9 -f "^\./bin/garuda-perception" || true
  pkill -9 -f "^/opt/garuda/bin/garuda-perception" || true
  true
'

ssh "$HOST" 'mkdir -p /opt/garuda/bin /opt/garuda/lib /opt/garuda/medialib/profile /opt/garuda/medialib/backups /opt/garuda/state /opt/garuda/models'
scp -q "$BIN" "$SVC/shim/garuda_mono_shim.py" "$HOST:/opt/garuda/bin/"
scp -q "$CFG" "$HOST:/opt/garuda/perception.json"
scp -q "$POST_SO" "$HOST:/opt/garuda/lib/"
scp -q "$POST_CFG" "$HOST:/opt/garuda/yolo26_post.json"
scp -q "$SVC/config/yolov8m_post.json" "$HOST:/opt/garuda/yolov8m_post.json"   # stock post-process labels for the yolov8m A/B config
# Both top-level medialib configs (default_profile "Garuda" and "GarudaYolov8n" respectively) — each
# perception*.json's own "medialib_config" field selects between them (see medialib/make_profile.py).
scp -q "$ROOT/hosts/hailo15l/medialib/garuda_medialib_config"*.json "$HOST:/opt/garuda/medialib/"
scp -q "$ROOT/hosts/hailo15l/medialib/profile/"*.json "$HOST:/opt/garuda/medialib/profile/"
scp -q "$ROOT/hosts/hailo15l/garuda-perception.init" "$HOST:/etc/init.d/garuda-perception"
scp -q "$SDK_LIB" "$HOST:/opt/garuda/lib/"
ssh "$HOST" 'ln -sf libturbojpeg.so.0.2.0 /opt/garuda/lib/libturbojpeg.so.0'
# HEF is large (~22 MB) and rarely changes: skip the copy when the board's copy already matches the
# PC-side pinned md5. Skipped entirely (no board round-trip either) when the selected config
# doesn't need the yolo26m HEF at all (NEED_HEF=0, rollback config — see the check above).
if [ "$NEED_HEF" = 1 ]; then
  BOARD_HEF_MD5="$(ssh "$HOST" 'md5sum /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef 2>/dev/null | cut -c1-32' || true)"
  if [ "$BOARD_HEF_MD5" != "$HEF_MD5" ]; then
    scp -q "$HEF_PC" "$HOST:/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef"
  else
    echo "yolo26m HEF already on board and md5-verified, skipping copy"
  fi
fi
# Boot order: run at S99 (the vendor's own boot-time app used S99 and got the camera reliably).
# Re-run every deploy — idempotent (remove-then-add is harmless when the priority is unchanged).
ssh "$HOST" 'chmod +x /etc/init.d/garuda-perception /opt/garuda/bin/garuda-perception; update-rc.d -f garuda-perception remove >/dev/null 2>&1 || true; update-rc.d garuda-perception defaults 99 >/dev/null'
if [ "${1:-}" != "--no-restart" ]; then
  ssh "$HOST" 'pkill -f "^camera-viewer-server" || true; /etc/init.d/garuda-perception restart; sleep 4; /etc/init.d/garuda-perception status'
fi
echo "deployed to $HOST"
