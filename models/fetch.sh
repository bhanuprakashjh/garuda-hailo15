#!/usr/bin/env bash
# Fetch Hailo-10H depth-model HEFs into the models/ EVALUATION ZONE. Idempotent.
# Some models are EVAL-ONLY by licence (see LICENCES.md) — evaluate on the bench, never ship.
# Usage: ./fetch.sh            # all
#        ./fetch.sh fast_depth # one
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.4.0/hailo10h"

fetch() {  # <s3-name> <local-name> <licence>
    if [ -f "$DIR/$2" ]; then echo "have $2 ($3)"; return; fi
    curl -fSL -o "$DIR/$2" "$BASE/$1"
    echo "fetched $2 ($(du -h "$DIR/$2" | cut -f1), $3)"
}

want="${*:-stereonet fast_depth scdepthv3}"
case " $want " in *" stereonet "*)  fetch stereonet.hef  stereonet_h10.hef  "UNLICENSED, eval-only";; esac
case " $want " in *" fast_depth "*) fetch fast_depth.hef fast_depth_h10.hef "MIT, ship-eligible";; esac
case " $want " in *" scdepthv3 "*)  fetch scdepthv3.hef  scdepthv3_h10.hef  "GPL-3.0, eval-only";; esac
