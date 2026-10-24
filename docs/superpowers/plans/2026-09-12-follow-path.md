# Follow Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the owner-approved follow path on the Hailo-15L fresh node — single-tile full view + a target-ROI crop for the locked target's class + OSNet-embedding-gated person identity — with the validated re-acquire radius fix deployed, the whole path measured offline on VisDrone-SOT (oracle ROI + real embeddings), and the board left running the follow profile ready for the owner's live session.

**Architecture:** The pieces already exist and are wired in `hosts/hailo15l/fresh_node.cpp`: a second `RegionDetector` planned by `garuda::fresh::RoiAssist` (currently hard-wired to `cell phone`), and `garuda::fresh::TargetOwner` (OSNet embedding identity, enabled by `tracking.learned_person_identity`; when active it replaces the histogram re-acquire layer). This plan generalizes the ROI assist to the locked class, adds one profile that turns both on with the controlled YOLO11s HEF for both detectors, extends the VisDrone-SOT harness with an oracle-ROI detection flavour and real OSNet embeddings computed on the board, and deploys.

**Tech Stack:** C++17 (`services/garuda-tracking`, `hosts/hailo15l`), CMake + Yocto SDK cross build (`hosts/hailo15l/build_fresh_tracking.sh`), Python 3 (bench tools, `numpy`, `PIL`), HailoRT 5.3.0 on the board (`root@10.0.0.1`), pytest / ctest.

**Spec:** `docs/superpowers/specs/2026-09-12-follow-platform-and-reacquire-design.md` (§3 re-acquire, §3a follow-ups) and the rulings in `docs/decisions.md` dated 2026-09-12 (later): radius growth 2.0, "histograms are not identity evidence; embedding required for persons", architecture recommendation single-tile + target ROI.

## Global Constraints

- Rule 1: every number in docs comes from a harness run recorded in `bench/benchlog.md`; unknown = `TBD-bench`.
- Rule 6: no new dependencies; datasets stay under `/media/bhanu1234/Development/hailo-export/` (research-use), never committed; no frames committed.
- Rule 7: every code change lands with its test; native suite = `ctest` in the tracking build, Python = `pytest` in `bench/hailo_reference`.
- Board: `ssh root@10.0.0.1`; node lifecycle only through `hosts/hailo15l/fresh_tracking_ctl.sh`; staging only through `hosts/hailo15l/stage_fresh_tracking.sh` (never edit `/opt/garuda-fresh` by hand); the live model file is never overwritten by bench tools.
- Board resource limit: the second detector needs ≥ 192 MiB free (`fresh_node.cpp` headroom check); the node embeds at most 4 persons per frame within a 150 ms budget.
- Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JogVqDZh1otFFRGqEZqawg`.
- Scratch build dirs: native tests `$SP/gt-tests` (`SP=/tmp/claude-1000/-media-bhanu1234-Development-GARUDASDK/da816c20-c7e1-44ef-ac61-47b48882508c/scratchpad`), ARM `GARUDA_FRESH_BUILD=/tmp/garuda-fresh-deploy`.

---

### Task 1: Deploy the radius-growth fix on the current tiles profile

**Files:**
- Run: `hosts/hailo15l/build_fresh_tracking.sh`, `hosts/hailo15l/stage_fresh_tracking.sh`, `hosts/hailo15l/fresh_tracking_ctl.sh`
- Modify: `bench/benchlog.md` (deploy note), memory file

**Interfaces:**
- Consumes: `reacquire_radius_growth=2.0` default (commit d981ed0).
- Produces: board binary `/opt/garuda-fresh/garuda-fresh-tracking` with sha256 equal to the local `/tmp/garuda-fresh-deploy/h15l/garuda-fresh-tracking`; OSNet HEF staged at `/opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef` (sha `49a46e48…`).

- [ ] **Step 1: Build (native tests + ARM)**

```bash
cd /media/bhanu1234/Development/GARUDASDK/.worktrees/hailo15l-fresh-tracking
GARUDA_FRESH_BUILD=/tmp/garuda-fresh-deploy bash hosts/hailo15l/build_fresh_tracking.sh 2>&1 | tail -5
```
Expected: `Built /tmp/garuda-fresh-deploy/h15l/garuda-fresh-tracking`; ctest 100 % passed; unittest OK.

- [ ] **Step 2: Stage with the OSNet HEF, restart the tiles profile**

```bash
bash hosts/hailo15l/fresh_tracking_ctl.sh stop
GARUDA_FRESH_BUILD=/tmp/garuda-fresh-deploy \
GARUDA_FRESH_REID_HEF=/media/bhanu1234/Development/hailo15/models/osnet_x1_0_hailo15l_v5.3.0.hef \
bash hosts/hailo15l/stage_fresh_tracking.sh
bash hosts/hailo15l/fresh_tracking_ctl.sh start-tiles
sleep 8; bash hosts/hailo15l/fresh_tracking_ctl.sh status | head -2 | cut -c1-200
sha256sum /tmp/garuda-fresh-deploy/h15l/garuda-fresh-tracking; ssh root@10.0.0.1 sha256sum /opt/garuda-fresh/garuda-fresh-tracking
```
Expected: two pids, `"accepted":true`, `rejected_frames:0`, both sha256 equal.

- [ ] **Step 3: Record**
Append to `bench/benchlog.md` under the 2026-09-12 (later) VisDrone-MOT entry: "Deployed <sha8> to the board (tiles profile) at <time>; status accepted, rejected 0." Update the memory file's last entry (board now on the new default). No commit needed beyond the benchlog line (commit with Task 3).

### Task 2: Generalize the target-ROI assist to the locked target's class

**Files:**
- Modify: `services/garuda-tracking/src/search_region.cpp:85-88` (plan eligibility)
- Modify: `hosts/hailo15l/fresh_node.cpp:71-81` (ROI detector construction), `:96` (move `coco` up)
- Test: `services/garuda-tracking/tests/test_search_region.cpp`

**Interfaces:**
- Consumes: `RoiAssist::plan(const Frame&, const Target& previous, int w, int h)`, `RegionDetector(hef, group, const std::vector<std::string>& class_labels, threshold, sw, sh, cut_margin)`.
- Produces: `RoiAssist` plans for any non-empty `previous.label`; the node's ROI detector emits all 80 COCO labels at `tracker.config().low_confidence`, cut margin `cfg.value("target_roi_cut_margin", 0.015)`.

- [ ] **Step 1: Failing test** — append to `test_search_region.cpp` before `main`:

```cpp
void roi_follows_selected_class() {
    // The follow target is whatever the owner locked; the ROI assist must plan
    // and merge for that class, not only for a phone.
    RoiAssist assist;auto t=phone();t.label="person";t.box=Box{.45,.30,.06,.20};
    Frame f1;f1.sequence=1;f1.capture_ms=1050;f1.now_ms=1110;f1.timestamp_valid=true;
    f1.detections.push_back({*t.box,"person",.6,{}, {}});
    CHECK(!assist.plan(f1,t,1280,720));
    Frame f2=f1;f2.sequence=2;f2.capture_ms=1100;f2.now_ms=1160;
    const auto region=assist.plan(f2,t,1280,720);CHECK(region&&!region->full_frame);
    Detection local{*t.box,"person",.9,{}, {}};
    f2.detections.clear();CHECK(assist.merge(f2,*region,{local},128)==1);
    local.label="cell phone";CHECK(assist.merge(f2,*region,{local},128)==0);
    Target none=t;none.label="";Frame f3=f2;f3.sequence=3;f3.capture_ms=1150;f3.now_ms=1210;
    CHECK(!assist.plan(f3,none,1280,720));
}
```
and add `roi_follows_selected_class();` to `main` (update the count string to `7 search region scenarios passed`).

- [ ] **Step 2: Run, expect FAIL** — `cmake --build $SP/gt-tests -j8 && $SP/gt-tests/test_search_region` → fails at `region&&!region->full_frame` (plan refuses non-phone).

- [ ] **Step 3: Implement** — in `search_region.cpp` `RoiAssist::plan` replace
`if(!epoch_||previous.label!="cell phone"||!previous.id||!previous.box||(!tracking&&!searching))`
with
`if(!epoch_||previous.label.empty()||!previous.id||!previous.box||(!tracking&&!searching))`.
In `fresh_node.cpp`: move `std::vector<std::string> coco(garuda::yolo26::COCO,garuda::yolo26::COCO+80);` above the ROI block and construct
`roi_detector=std::make_unique<garuda::h15l::RegionDetector>(cfg.at("target_roi_hef").get<std::string>(),"garuda-fresh",coco,tracker.config().low_confidence,width,height,cfg.value("target_roi_cut_margin",0.015));`
Update the comment/throw text "target ROI bench requires…" to "target ROI requires…".

- [ ] **Step 4: Run, expect PASS** — `$SP/gt-tests/test_search_region` prints `7 search region scenarios passed`; `ctest --test-dir $SP/gt-tests` 7/7.

- [ ] **Step 5: Commit** — `git commit -m "feat(tracking): target-ROI assist follows the locked class, not only the phone"`.

### Task 3: Follow profile, control action, profile test

**Files:**
- Create: `hosts/hailo15l/fresh/perception-follow.json`
- Modify: `hosts/hailo15l/fresh_tracking_ctl.sh:10-40`, `bench/hailo_reference/run_visdrone_det.py:19-20` (PROFILE_FILES)
- Test: `services/garuda-tracking/tests/test_fresh_profiles.py` (new, unittest style like the other `test_*.py` there)

**Interfaces:**
- Produces: profile JSON keys `target_roi: "assist"`, `target_roi_hef: "/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef"`, `tracking.learned_person_identity: true`, `person_reid_hef: "/opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef"`, `person_reid_model_id: "osnet_x1_0-hailo15l-5.3.0-sha256:49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7"`; ctl action `start-follow`.

- [ ] **Step 1: Failing test** — `services/garuda-tracking/tests/test_fresh_profiles.py`:

```python
import json, pathlib, re, unittest
ROOT = pathlib.Path(__file__).resolve().parents[3]
FRESH = ROOT / 'hosts' / 'hailo15l' / 'fresh'
CTL = (ROOT / 'hosts' / 'hailo15l' / 'fresh_tracking_ctl.sh').read_text()

class FreshProfiles(unittest.TestCase):
    def profiles(self):
        return {p.name: json.loads(p.read_text()) for p in FRESH.glob('perception*.json')}

    def test_every_profile_parses_with_the_shared_keys(self):
        for name, p in self.profiles().items():
            for key in ('hef', 'frame_w', 'frame_h', 'input_w', 'input_h', 'input_geometry', 'tracking'):
                self.assertIn(key, p, name)
            self.assertIn(p.get('target_roi', 'off'), ('off', 'assist', 'shadow'), name)
            if p['tracking'].get('learned_person_identity'):
                self.assertIn('person_reid_hef', p, name); self.assertIn('person_reid_model_id', p, name)
            if p.get('target_roi', 'off') != 'off':
                self.assertIn('target_roi_hef', p, name)

    def test_follow_profile_is_single_tile_roi_plus_embedding(self):
        p = self.profiles()['perception-follow.json']
        self.assertFalse(p.get('detection_tiles', False))
        self.assertEqual(p['target_roi'], 'assist')
        self.assertEqual(p['target_roi_hef'], p['hef'])          # one validated model for both detectors
        self.assertTrue(p['tracking']['learned_person_identity'])
        self.assertEqual(p['input_geometry'], 'letterbox')

    def test_ctl_knows_every_profile(self):
        actions = re.search(r'^\s*(start\|[^)]*)\)', CTL, re.M).group(1).split('|')
        mapped = dict(re.findall(r'if \[ "\$ACTION" = (start-[a-z-]+) \]; then CONFIG_NAME=(perception-[a-z0-9-]+\.json)', CTL))
        self.assertEqual(mapped.get('start-follow'), 'perception-follow.json')
        for action in mapped:
            self.assertIn(action, actions)

if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m unittest services.garuda-tracking... ` (run as `cd services/garuda-tracking/tests && python3 -m unittest test_fresh_profiles -v`) → KeyError `perception-follow.json`.

- [ ] **Step 3: Implement** — write `perception-follow.json` as `perception-letterbox.json` plus:
```json
  "target_roi": "assist",
  "target_roi_hef": "/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef",
  "target_roi_cut_margin": 0.015,
  "person_reid_hef": "/opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef",
  "person_reid_model_id": "osnet_x1_0-hailo15l-5.3.0-sha256:49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7"
```
and `"learned_person_identity": true` inside `tracking` (keep `freshness_ms` 200, `coast_ms` 1200 — single-tile rate). In `fresh_tracking_ctl.sh`: add `start-follow` to the `case` list, `if [ "$ACTION" = start-follow ]; then CONFIG_NAME=perception-follow.json; fi`, and extend the OSNet checksum guard `if [ "$1" = perception-person-reid-bench.json ]` to `case "$1" in perception-person-reid-bench.json|perception-follow.json)`. Add `'start-follow': 'perception-follow.json'` to `PROFILE_FILES` in `run_visdrone_det.py`. Update the usage line.

- [ ] **Step 4: Run, expect PASS** — the three unittest cases pass; `bash -n hosts/hailo15l/fresh_tracking_ctl.sh`.

- [ ] **Step 5: Commit** — `git commit -m "feat(hailo15l): perception-follow profile — single tile + target ROI + OSNet identity"`.

### Task 4: Oracle-ROI flavour in the VisDrone-SOT harness

**Files:**
- Modify: `bench/hailo_reference/prepare_visdrone_sot.py` (add `--roi`), `bench/hailo_reference/score_visdrone_det.py` (`load_results` groups by `method`), `bench/hailo_reference/sot_to_replay.py` (flavour `roi`), `bench/hailo_reference/run_sot_replays.py` (flavours loop)
- Test: `bench/hailo_reference/test_visdrone_tools.py`
- Evidence: `bench/results/2026-09-12-visdrone-sot/` (re-run), README, benchlog

**Interfaces:**
- Produces: `prepare_visdrone_sot.oracle_roi(gt_xywh, w, h, context=2.5, minimum_side=640) -> dict(x,y,w,h,full_frame=False)` mirroring `SearchPlanner::next` with `position_std=0`; regions gain `method='oracle_roi'`, `tile=5`; `load_results` returns `{'full': [], 'corners': [], 'roi': []}` per image; `sot_to_replay.roi_merge(full_dets, roi_dets, label, region) -> list` mirroring `RoiAssist::merge` (label only, conf ≥ .15, `cuts_object` margin .015 in network space, duplicate at IoU ≥ .4 dropped) plus the 400 ms primary-evidence deadline (ROI detections used only when a full-view box overlapped the target at IoU ≥ .3 within the last 12 frames).

- [ ] **Step 1: Failing tests** — append to `test_visdrone_tools.py`:

```python
def test_oracle_roi_mirrors_search_planner_geometry():
    import prepare_visdrone_sot as sot
    r = sot.oracle_roi([648, 370, 34, 95], 1280, 720)          # 95 px target: 2.5x = 238 < minimum 640
    assert (r['w'], r['h'], r['full_frame']) == (640, 640, False)
    assert r['x'] == 344 and r['y'] == 80                       # centre (665,417) - 320, floored to even, clamped
    r = sot.oracle_roi([10, 10, 300, 300], 1280, 720)           # 2.5x = 750 > min(1280,720): full frame
    assert r['full_frame']

def test_roi_merge_mirrors_roi_assist():
    region = dict(source_w=1280, source_h=720, x=344, y=80, w=640, h=640, full_frame=False)
    full = [dict(label='person', score=.6, box=[648, 370, 682, 465])]
    same = dict(label='person', score=.9, box=[650, 372, 684, 467])     # duplicate of a full-view box
    new = dict(label='person', score=.7, box=[400, 200, 430, 280])      # new person inside the crop
    other = dict(label='car', score=.9, box=[400, 200, 460, 240])       # not the target class
    merged = sot_to_replay.roi_merge(full, [same, new, other], 'person', region)
    assert merged == full + [new]
```

- [ ] **Step 2: Run, expect FAIL** (no `oracle_roi`, no `roi_merge`).

- [ ] **Step 3: Implement**
`prepare_visdrone_sot.py`:
```python
def oracle_roi(gt_xywh, w, h, context=2.5, minimum_side=640):
    """SearchPlanner::next with position_std 0: square crop of context x extent, never below minimum_side."""
    x, y, bw, bh = gt_xywh
    extent = max(bw, bh)
    needed = context * extent
    if needed > min(w, h) or minimum_side > min(w, h):
        return dict(x=0, y=0, w=w, h=h, full_frame=True)
    side = max(minimum_side, int(math.ceil(needed / 2)) * 2)
    cx, cy = x + bw / 2, y + bh / 2
    rx = int(min(max(cx - side / 2, 0), w - side) / 2) * 2
    ry = int(min(max(cy - side / 2, 0), h - side) / 2) * 2
    return dict(x=rx, y=ry, w=side, h=side, full_frame=False)
```
and `--roi` appends `dict(source_w=..., **oracle_roi(...), reuse_source=True, via_1080p=False, method='oracle_roi', tile=5, image_index=index)` after the five tiles (a full-frame oracle result is still recorded with `method='oracle_roi'` so the scorer can ignore it).
`score_visdrone_det.load_results`: `entry = per_image.setdefault(idx, {'full': [], 'corners': [], 'roi': []})`; route by `r.get('method') == 'oracle_roi'` → `'roi'` (skip node corner filters for it; apply nothing but the label filter), else the existing full/corner logic.
`sot_to_replay.py`:
```python
def roi_merge(full_dets, roi_dets, label, region, cut_margin=.015):
    kept = list(full_dets)
    for d in roi_dets:
        if d['label'] != label or d['score'] < .15 or region['full_frame']:
            continue
        net = to_network(region, d['box'])                     # x1,y1,x2,y2 in 0..1 of the 640 square
        if cuts_object(region, net, cut_margin):
            continue
        if any(k['label'] == d['label'] and iou(k['box'], d['box']) >= .4 for k in full_dets):
            continue
        kept.append(d)
    return kept
```
with `to_network` inverting `map_box` (scale = 640/side, content offset, letterbox padding) and `cuts_object` imported from `score_visdrone_det`. Flavour loop becomes `('single', 'five', 'roi')`; the `roi` flavour = `roi_merge(entry['full'], entry['roi'], 'person', region_for_frame)` gated by the 400 ms primary-evidence rule (`last_primary` = last frame index where a full-view person box had IoU ≥ .3 with the GT; use ROI only if `index - last_primary <= 12`). `run_sot_replays.py`: flavours `('single', 'five', 'roi')`; skip a flavour whose input file is absent.

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest -q test_visdrone_tools.py`.

- [ ] **Step 5: Regenerate streams and re-run the board** for the three sequences with `--roi` (`prepare_visdrone_sot.py … --roi` into `hailo-export/visdrone-sot-replay-20260912-roi/<seq>`; `run_visdrone_det.py … bench/results/2026-09-12-visdrone-sot/<seq>-roi --restart-profile <current>`; then `run_sot_replays.py` for all three). Gzip `letterbox.jsonl`.

- [ ] **Step 6: Record and commit** — add a `roi` column to the README tables (detector-on-target and tracker rows), a benchlog paragraph, commit `bench: VisDrone-SOT oracle target-ROI flavour`.

### Task 5: Real OSNet embeddings in the SOT replay (identity check)

**Files:**
- Create: `bench/hailo_reference/embed_visdrone_sot.py`
- Modify: `bench/hailo_reference/sot_to_replay.py` (`--embeddings`), `bench/hailo_reference/run_sot_replays.py` (`--embeddings`, config `identity`)
- Test: `bench/hailo_reference/test_visdrone_tools.py`
- Evidence: `bench/results/2026-09-12-visdrone-sot/<seq>/embeddings.jsonl.gz`, README, benchlog, decisions

**Interfaces:**
- Consumes: `garuda-embedding-probe model.hef - <model_id>` on the board (`/tmp/garuda-fresh-deploy/h15l/garuda-embedding-probe`, aarch64): reads packed 128x256 NV12 crops from stdin, prints one JSON line per crop with `model` and `embedding` (512 values).
- Produces: `embed_visdrone_sot.crop_nv12(y_plane, uv_plane, box_norm) -> bytes` mirroring `resize_nv12_crop` (even floor/ceil crop, bilinear to 128x256, Y then interleaved UV); `embeddings.jsonl` rows `{frame, flavour_box: [x1,y1,x2,y2], label, model, values}`; `sot_to_replay --embeddings FILE` attaches `embedding: {model, values}` to every detection whose `(frame, box)` matches; replay config `identity.json` = `{"learned_person_identity": true}`.

- [ ] **Step 1: Failing tests**

```python
def test_crop_nv12_matches_resize_nv12_crop_rounding():
    import embed_visdrone_sot as emb
    y = np.arange(720*1280, dtype=np.uint32).reshape(720, 1280) % 251
    y = y.astype(np.uint8); uv = np.full((360, 1280), 128, np.uint8)
    out = emb.crop_nv12(y, uv, (0.5, 0.5, 0.1, 0.2))
    assert len(out) == 128*256*3//2
    # box 0.5..0.6 x 0.5..0.7 -> x 640..768, y 360..504 (already even): the top-left output pixel is the source pixel
    assert out[0] == y[360, 640]

def test_embeddings_attach_by_frame_and_box():
    rows = [dict(frame=3, box=[10, 20, 30, 80], model='m', values=[0.0]*512)]
    dets = [dict(label='person', score=.9, box=[10, 20, 30, 80]), dict(label='person', score=.9, box=[0, 0, 5, 5])]
    attached = sot_to_replay.attach_embeddings(dets, 3, sot_to_replay.index_embeddings(rows))
    assert attached[0]['embedding'] == dict(model='m', values=[0.0]*512) and 'embedding' not in attached[1]
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** `embed_visdrone_sot.py`: for each frame, for every person detection in the union of the frame's `full`, aggregated `five`, and `roi` lists (deduplicated by box, at most 8 per frame, conf ≥ .15), crop with `crop_nv12`, write the packed crops to a temp file, stream them to the board probe via `ssh root@10.0.0.1 'LD_BIND_NOW=1 <stage>/garuda-embedding-probe <stage>/osnet.hef - osnet_x1_0-hailo15l-5.3.0-sha256:49a46e48…'` with the node stopped/restored exactly as `run_visdrone_det.py` does (same profile guard, hash-verified HEF copy to a `mktemp -d /tmp/garuda-visdrone.XXXXXX` stage dir); pair the probe's output lines with the crop order; write `embeddings.jsonl` (+ a `run.json` with hashes and probe stderr summary). `sot_to_replay.py`: `index_embeddings(rows) -> dict[(frame, tuple(round(v,2) for v in box))] -> {model, values}`, `attach_embeddings(dets, frame, index)`, `--embeddings` flag applied to every flavour. `run_sot_replays.py`: `--embeddings FILE` passed through; add config `identity` = `{"learned_person_identity": true}` (written by the driver to the work dir).

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Run on the board** for the three sequences (embeddings), then the driver with `--embeddings` and configs `default`, `identity`, `off` on `single`, `five`, `roi`. Compute the OSNet separability numbers the histogram analysis used (target self-distance over time, target vs others per frame, fraction under `max_anchor_distance` 0.25) with a small script saved as `bench/hailo_reference/embedding_separability.py` (argparse: replay input with embeddings + truth; prints/writes JSON).

- [ ] **Step 6: Record and commit** — README section "Real embeddings" with the table (024 single/five/roi × default/identity/off: on-target, off-target-while-valid, losses), the separability numbers, and an explicit verdict on the decisions.md recommendation (confirmed / refuted / partial); benchlog paragraph; decisions.md addendum. Commit `bench: VisDrone-SOT with real OSNet embeddings — identity gate measured`.

### Task 6: Switch the board to the follow profile; live-session checklist

**Files:**
- Run: `build_fresh_tracking.sh`, `stage_fresh_tracking.sh`, `fresh_tracking_ctl.sh start-follow`
- Modify: `bench/results/2026-09-12-visdrone-sot/README.md` (live procedure), `bench/benchlog.md`, `docs/decisions.md`, memory, `CLAUDE.md` §7 resume note is NOT edited (master file; decisions.md carries state)

- [ ] **Step 1: Rebuild + stage** (Task 2/3 code and profile): same commands as Task 1 with `GARUDA_FRESH_REID_HEF` set; `fresh_tracking_ctl.sh stop && start-follow`.

- [ ] **Step 2: Verify without a person** — `status` shows `diag.target_roi.mode == "assist"` with `reason` `not_eligible` (no lock yet), `diag.person_embedding.enabled == true`, `accepted:true`, `rejected_frames:0`, publisher interval ≈ single-tile rate (record `interval_ms` and `age_ms` from three samples 10 s apart), and `/proc/meminfo` headroom after start (record MemAvailable). If the node refuses to start for headroom, record it and fall back to `start-letterbox` (single tile, no ROI) — do not force.

- [ ] **Step 3: Live-session procedure (owner)** written into the README under "Live check (TBD-bench until run)": (a) `python3 bench/hailo_reference/golden_capture.py <out.jsonl> 180` while the owner click-locks themselves at http://10.0.0.1:8099/, walks out of frame ≥ 1.5 s and returns, then has a second person cross in front; (b) expected fields to read from the capture: `lock.state` sequence `tracking → coasting → lost/occluded → reacquiring → tracking`, `lock.identity_retained`, `lock.reason == identity_verified`, `diag.target_roi.inferences` climbing while locked, `diag.person_embedding.inferences` climbing; (c) numbers to enter in benchlog: re-acquire latency, wrong-bind count (0 expected), ROI/embedding inference ms, node rate.

- [ ] **Step 4: Record and commit** — benchlog "board switched to perception-follow" with the Step 2 samples; decisions.md line; memory resume entry; commit `deploy(hailo15l): follow profile live — target ROI + OSNet identity`.

---

## Self-review

- Spec coverage: §3 gates untouched (Task 2 changes only ROI eligibility); §3a item 1 (five-tile) is superseded by the owner's 2026-09-12 approval of single-tile + ROI — recorded in decisions.md by Task 6; item 2 (stable lock id) already landed. The decisions.md embedding recommendation is measured by Task 5 rather than assumed.
- Placeholders: none; every code step carries its code. Numbers in Tasks 1/5/6 are produced by runs, never pre-filled.
- Type consistency: `oracle_roi` returns the dict shape `prepare_visdrone_det.five_tile_layout` uses; `load_results` keeps `full`/`corners` and adds `roi`; `roi_merge` consumes `score_visdrone_det.iou`/`cuts_object` and the region dict shape from `regions.json`; embeddings use the replay's `{"model","values"}` contract from `json.hpp`.
