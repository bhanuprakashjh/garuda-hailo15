# SKELETON, UNBUILT, not-product-cleared. Never include in a product image.
# Upstream CLIP source: MIT. Factory HEF checkpoint/weight/data clearance pending.
SUMMARY = "Factory Hailo-15L CLIP image encoder bench model (disabled)"
LICENSE = "CLOSED"
# Artifact exists only in the factory image/SDK; no redistributable fetch is asserted.
SRC_URI = ""
EXCLUDE_FROM_WORLD = "1"
python () {
    raise bb.parse.SkipRecipe("Bench-only skeleton; factory CLIP model product clearance is outstanding")
}
