# OSNet person re-identification on Hailo-15L — bench only

Pinned Hailo model-zoo v5.3.0 artifact:
`https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/osnet_x1_0.hef`

SHA-256: `49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7`.
Size: 3,244,032 bytes. Fetch with `bash models/fetch_osnet_h15l.sh`.

The [pinned model configuration](https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo/v5.3.0/hailo_model_zoo/cfg/networks/osnet_x1_0.yaml)
identifies the source as deep-person-reid (MIT), trained on Market1501. Model-weight and training
dataset terms have not been independently cleared for the product. **EVAL-ONLY, not-product-cleared.**
No upstream model code or weights are embedded in the host-independent tracking service. The
optional Hailo runtime adapter and bench config live in `hosts/hailo15l/`.

`hailortcli parse-hef` on this board reports HAILO15L / compiler5.3.0, 12 contexts,
`osnet_x1_0/input_layer1 UINT8 NV12(128x128x3)` and `osnet_x1_0/fc1 UINT8 NC(512)`.
NV12's reported height is half the physical image height: supply **256 high ×128 wide** Y and UV
planes, not RGB. The first probe caught this mismatch before inference. Output is dequantized
by HailoRT into512 floats and L2-normalized by our adapter. Network normalization is already in
this HEF; do not add mean/std normalization on the host.

The camera adapter crops the **current detector image's full-FOV content**, chroma-aligns the
clipped crop and bilinearly resizes the NV12 planes to128×256. This is not a high-resolution DSP
crop. Its descriptor tag includes the pinned model identifier and preprocessing revision. At
most4 person crops run per frame, with an input-age admission check; missing/incompatible
features withhold identity verification. Accelerator faults latch until restart.

The model is for people. It does not provide phone identity. Learned reacquisition thresholds
are experimental cosine-distance gates, not probabilities or calibrated accuracy results.
The anchor is immutable; the recent history is bounded. Similar candidates, missing descriptors,
stale observations and expired identity memory cannot produce valid target control.

Measurements and limitations are recorded in `bench/benchlog.md` and
`bench/results/2026-09-10-fresh-tracking/`. Vendor rank1/FPS figures are not our drone benchmark.
