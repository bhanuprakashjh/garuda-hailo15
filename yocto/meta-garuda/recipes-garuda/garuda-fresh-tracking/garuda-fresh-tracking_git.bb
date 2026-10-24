# SKELETON, UNBUILT. Pin SRCREV after the isolated development branch is published.
# Our code is BSD-3-Clause. Runtime dependencies retain their separate SDK licences.
# Detector weights/config deployment are bench-only and deliberately absent from this recipe.
SUMMARY = "Garuda independent Hailo-15L object/person tracking"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://../../LICENSE;md5=d2c76156ced293ab11bef56931dfe806"
SRC_URI = "git://github.com/bhanuprakashjh/garuda-sdk-bench.git;protocol=https;branch=feat/hailo15l-fresh-tracking"
SRCREV = "${AUTOREV}"
S = "${WORKDIR}/git/services/garuda-perception"
DEPENDS = "hailort hailo-analytics-api media-library jpeg hailo-postprocess-tools"
inherit cmake
EXTRA_OECMAKE = "-DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF -DGARUDA_BUILD_FRESH_TRACKING=ON"
