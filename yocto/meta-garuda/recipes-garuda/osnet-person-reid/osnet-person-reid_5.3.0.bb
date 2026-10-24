# SKELETON, UNBUILT, not-product-cleared. Never include in a product image.
# Upstream source is MIT; this compiled weight artifact/dataset clearance is pending.
SUMMARY = "OSNet Hailo-15L person re-identification bench model (disabled)"
LICENSE = "CLOSED"
SRC_URI = "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo15l/osnet_x1_0.hef"
SRC_URI[sha256sum] = "49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7"
EXCLUDE_FROM_WORLD = "1"
python () {
    raise bb.parse.SkipRecipe("Bench-only skeleton; model product licence review is outstanding")
}
