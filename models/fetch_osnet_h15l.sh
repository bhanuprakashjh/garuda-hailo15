#!/usr/bin/env bash
# Pinned bench artifact; see osnet_h15l.md for source/weight licence distinction.
set -euo pipefail
URL='https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/osnet_x1_0.hef'
SHA='49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7'
OUT="${1:-/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef}"
mkdir -p "$(dirname "$OUT")"
if [ -f "$OUT" ] && [ "$(sha256sum "$OUT" | cut -d ' ' -f1)" = "$SHA" ]; then
  echo "already present and SHA-256 verified: $OUT"; exit 0
fi
PART="$(mktemp "${OUT}.part.XXXXXX")"
trap 'rm -f "$PART"' EXIT
curl -fsS --connect-timeout 20 --max-time 300 -o "$PART" "$URL"
GOT="$(sha256sum "$PART" | cut -d ' ' -f1)"
if [ "$GOT" != "$SHA" ]; then echo "OSNet SHA-256 mismatch" >&2; exit 1; fi
mv "$PART" "$OUT"
echo "fetched and SHA-256 verified: $OUT"
