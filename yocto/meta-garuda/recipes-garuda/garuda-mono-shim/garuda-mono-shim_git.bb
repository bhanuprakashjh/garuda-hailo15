# garuda-mono-shim — garuda-mono HTTP contract over the perception feed (python3 stdlib)
#
# SKELETON, UNBUILT (CLAUDE.md §6 rule 6). M0 implementation lands on the bench in the branch
# feat/hailo15l-perception, merged to master. The shim consumes the framed TCP feed from
# garuda-perception and serves the HTTP contract that garuda-portal expects (see
# docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md, §3).
# Production tier will inherit this recipe after Phase 9.
#
# LICENCE: project — check repo LICENSE file.

SUMMARY = "Garuda mono shim: garuda-mono HTTP contract over the perception feed (python3 stdlib)"
LICENSE = "CLOSED"
SRC_URI = "git://github.com/bhanuprakashjh/garuda-sdk-bench.git;protocol=https;branch=master"
SRCREV = "${AUTOREV}"
S = "${WORKDIR}/git/services/garuda-perception/shim"
RDEPENDS:${PN} = "python3-core python3-json python3-netserver"
do_install() { install -d ${D}${bindir}; install -m 0755 ${S}/garuda_mono_shim.py ${D}${bindir}/garuda-mono-shim; }
