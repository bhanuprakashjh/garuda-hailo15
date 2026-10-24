# SKELETON, UNBUILT. Existing vendor OpenCV is reused by the bench plugin.
SUMMARY = "OpenCV camera-motion and selected-visual-target dependency for Garuda (disabled port skeleton)"
LICENSE = "Apache-2.0"
SRC_URI = "git://github.com/opencv/opencv.git;protocol=https;branch=4.x"
# Pin the verified 4.5.5 source commit, licence checksum and vendor configuration
# when implementing the product recipe; this skeleton deliberately cannot build.
EXCLUDE_FROM_WORLD = "1"
python () {
    raise bb.parse.SkipRecipe("Disabled dependency skeleton; use vendor SDK on the bench")
}
