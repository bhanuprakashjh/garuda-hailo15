# CLIP image encoder on Hailo-15L — experimental appearance cue

The factory image and local SDK contain
`/home/root/apps/clip/resources/clip_vit_b_32_image_encoder_nv12.hef`.
SHA-256 on both is
`458be87c32f34b9d6066dcfb222687e04f5a54b8b51f08901e20486dfea0a5dd`.
No model download or weight distribution is introduced by this change.

The board parses this artifact as HAILO15L, compiler 5.2.0, 41 contexts,
`input_layer1 UINT8 NV12(112x224x3)` and `conv50 UINT8 NHWC(1x1x512)`.
Physical input is **224×224 NV12**, because the reported NV12 height is halved.
Inference through the existing HailoRT 5.3.0 succeeds. HailoRT dequantizes output
to 512 floats; the host L2-normalizes it. No extra host mean/std operation is applied.

[Hailo's pinned v5.3 model configuration](https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo/v5.3.0/hailo_model_zoo/cfg/networks/clip_vit_b_32_image_encoder.yaml)
identifies OpenAI CLIP as the upstream source. [CLIP source is MIT licensed](https://raw.githubusercontent.com/openai/CLIP/main/LICENSE).
The factory compiled artifact's exact source checkpoint and preprocessing have not
been independently matched to that public version. Weight/data/product clearance
remains pending: **EVAL-ONLY, not-product-cleared**. The associated Yocto recipe
is a disabled skeleton. No CLIP encoder is enabled in a camera profile.

The [upstream model card](https://raw.githubusercontent.com/openai/CLIP/main/model-card.md)
describes a classification representation, including limitations with fine-grained
tasks. It does not establish physical instance identity. A high cosine score cannot
alone authorize reacquisition of the selected phone.

The host's `ImageEmbedding` adapter now accepts explicit even physical dimensions
and a bounded timeout; `PersonEmbedding` remains a compatibility alias with the
unchanged 128×256 / 100 ms OSNet defaults. The bench probe's `--clip` mode selects
224×224 and a 500 ms diagnostic timeout. It does not relax the camera's freshness
or control budgets. The adapter rejects mismatched HEF shapes before inference.

On the actual board, 17 sequential CLIP calls had median inference 20.084 ms and
p95 20.152 ms, with median CPU crop 5.796 ms. Model load was 510.646 ms; process
peak RSS 13,456 KiB does not include all accelerator/driver memory. These short,
unloaded calls do not establish sustained detector-plus-encoder performance.

Eight sparse views of the user's phone and seven COCO phone images show overlapping
same-phone and cross-phone cosine ranges when all reference views are considered.
A printed-phone example also scores highly. This candidate is retained for further
appearance experiments, **not promoted to a phone identity gate**. See the
[complete evidence](../bench/results/2026-09-10-fresh-tracking/object-embedding/README.md).
