# garuda-perception — Hailo-15L perception node (frontend -> detect -> track -> depth -> feed)
#
# SKELETON, UNBUILT (CLAUDE.md §6 rule 6). M0 implementation lands on the bench in the branch
# feat/hailo15l-perception, merged to master. The node drives the `hailo_analytics` framework
# pipeline on the Hailo-15L SBC (see docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md).
# Production tier will inherit this recipe after Phase 9.
#
# LICENCE: project — check repo LICENSE file.

SUMMARY = "Garuda perception node for Hailo-15 (frontend -> detect -> track -> depth -> feed)"
LICENSE = "CLOSED"
# Project licence to be set with the repo's LICENSE file; depends on Hailo proprietary SDK layers (meta-hailo-soc).
SRC_URI = "git://github.com/bhanuprakashjh/garuda-sdk-bench.git;protocol=https;branch=master"
SRCREV = "${AUTOREV}"
S = "${WORKDIR}/git/services/garuda-perception"
DEPENDS = "hailort hailo-analytics-api media-library jpeg hailo-postprocess-tools"
inherit cmake
EXTRA_OECMAKE = "-DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF"

# M2: postprocess/ builds libyolo26_post.so (the yolo26m post-process plugin, see
# services/garuda-perception/postprocess/CMakeLists.txt) alongside the garuda-perception binary;
# the default FILES:${PN} only picks up bindir, so the plugin's install location needs its own entry.
FILES:${PN} += "${libdir}/libyolo26_post.so"
