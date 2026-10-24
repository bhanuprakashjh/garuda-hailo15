# SKELETON, UNBUILT. PC bench dependencies only, never install on the board.
SUMMARY = "Gazebo follow simulation dependencies and actor asset (bench only)"
LICENSE = "Apache-2.0 & BSD-3-Clause & HPND & CC-BY-4.0 & LGPL-3.0-only"
SRC_URI = "https://fuel.gazebosim.org/1.0/Mingfei/models/actor/1"
EXCLUDE_FROM_WORLD = "1"
python () {
    raise bb.parse.SkipRecipe("PC evaluation only; dependency and asset attribution in docs/dependencies/gazebo-follow-bench.md")
}
