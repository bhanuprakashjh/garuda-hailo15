#!/usr/bin/env bash
set -euo pipefail
# Build a deployment directory only; never modify or restart the board here.
if [ "$#" -ne 2 ]; then
  echo 'Usage: stage_hailo_adapter.sh HAILO_SOURCE_ROOT OUTPUT_DIRECTORY' >&2
  exit 2
fi
adapter_repo="$(cd "$(dirname "$0")/../.." && pwd)"
adapter_source="$1"
adapter_output="$2"
adapter_sdk=/media/bhanu1234/Development/hailo15/sdk
test "$(git -C "$adapter_source" rev-parse HEAD)" = 9e06d3b9926e9154afdc3c76a86f17a9ef07ab9f
mkdir -p "$adapter_output"
python3 -m pip install --target "$adapter_output/vendor" --platform any --only-binary=:all: --no-deps --require-hashes \
  -r "$adapter_repo/services/garuda-tracking/hailo_adapter_requirements.txt"
"$adapter_sdk/sysroots/x86_64-pokysdk-linux/usr/bin/protoc" \
  --descriptor_set_out="$adapter_output/analytics_metadata.desc" \
  --proto_path="$adapter_source/hailo-analytics/hailo_analytics_api/src/pipeline/codecs/protos" \
  "$adapter_source/hailo-analytics/hailo_analytics_api/src/pipeline/codecs/protos/analytics_metadata.proto"
for adapter_file in hailo_adapter.py hailo_viewer.html hailo_viewer.js hailo_adapter_requirements.txt; do
  cp "$adapter_repo/services/garuda-tracking/$adapter_file" "$adapter_output/"
done
