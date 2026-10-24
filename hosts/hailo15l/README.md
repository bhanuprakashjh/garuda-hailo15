# hosts/hailo15l — Hailo-15L SBC toolchain

Cross-compilation setup for the Hailo-15L single-board computer. The SDK is
installed once, outside the repo, then sourced for every cross build.

## 1. Install the SDK (one-time, ~8 GB, no sudo)

```bash
sh /media/bhanu1234/Development/hailo15/vpsp-1.12.0/prebuilt/sbc/sdk/poky-glibc-x86_64-core-image-hailo-dev-armv8a-hailo15l-sbc-toolchain-4.0.23.sh -y -d /media/bhanu1234/Development/hailo15/sdk
ls /media/bhanu1234/Development/hailo15/sdk/
```
Produces `environment-setup-armv8a-poky-linux`, `sysroots/`, `version-armv8a-poky-linux`
in the target directory.

## 2. Cross-build (source the env, then use the SDK's CMake toolchain file)

```bash
source /media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux
cd hosts/hailo15l/hello
cmake -B build-h15l -G Ninja -DCMAKE_TOOLCHAIN_FILE=$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake
cmake --build build-h15l
file build-h15l/hello_hailort   # ELF 64-bit LSB pie executable, ARM aarch64
```

`cmake/hailo15l.cmake` can be included from a project's `CMakeLists.txt` after
the environment is sourced; it fails fast with a clear error if
`OECORE_TARGET_SYSROOT` is not set, so a native build can never silently
masquerade as a cross build.

Native x86 builds (e.g. unit tests that don't touch the board) use plain
`cmake` with no SDK environment sourced — the toolchain file is opt-in per
build, never global.

## 3. Copy to the board and run

```bash
scp hosts/hailo15l/hello/build-h15l/hello_hailort root@10.0.0.1:/tmp/
ssh root@10.0.0.1 /tmp/hello_hailort   # hailort 5.3.0
```

## Board access

- `ssh root@10.0.0.1` — key auth is already installed, no password prompt.
- If SSH times out, the PC's wired port may not be pointed at the board's
  subnet: run `nmcli con up h15-link` on the PC (re-points it to
  `10.0.0.2/24`) and retry.

## 4. Media-library profile (M0 history; current state is two profiles, see below)

`hosts/hailo15l/medialib/make_profile.py` generates the node's media-library
config from the stock `hailo15l/imx678` daylight detection profile. Only
`application_input_streams` is ours; ISP/sensor/stabilizer settings stay
Hailo's, referenced in place by absolute path. `encoded_output_streams` is
empty — no H.264 in any profile so far.

**M0 history:** the original (single) profile had `sink0` 640x384 (stretched)
for the detector, `sink1` 1280x720 for JPEG, both NV12 30 fps — the stock
`hailo_yolov8n_384_640` HEF's native input shape.

**Current state (M2):** the script now generates **two named profiles**,
each with its own `application_settings*.json`, and **two top-level
`garuda_medialib_config*.json` files** (not one — see §8's "Rollback
command" for why a single shared file with `set_profile()` switching between
them does not actually work):

| Profile name | sink0 | Required by | Top-level config (its `default_profile`) |
|---|---|---|---|
| `Garuda` | 640x640, `LETTERBOX_MIDDLE` | yolo26m (square input) | `garuda_medialib_config.json` (`Garuda`) |
| `GarudaYolov8n` | 640x384, stretched (M0 geometry) | stock `hailo_yolov8n_384_640` (fixed 640x384 input) | `garuda_medialib_config_yolov8n.json` (`GarudaYolov8n`) |

`sink1` (1280x720 NV12 30 fps, JPEG feed) is identical in both. Each
`services/garuda-perception/config/perception*.json` selects its pair via its
own `medialib_config` + `profile` fields — `config/perception.json` points at
`garuda_medialib_config.json`/`Garuda`, `config/perception-yolov8n.json` at
`garuda_medialib_config_yolov8n.json`/`GarudaYolov8n`. Both top-level configs
list both profiles (harmless — keeps them interchangeable; only
`default_profile` differs).

```bash
python3 hosts/hailo15l/medialib/make_profile.py
ssh root@10.0.0.1 'mkdir -p /opt/garuda/medialib/profile /opt/garuda/medialib/backups'
scp hosts/hailo15l/medialib/garuda_medialib_config.json root@10.0.0.1:/opt/garuda/medialib/
scp hosts/hailo15l/medialib/profile/*.json root@10.0.0.1:/opt/garuda/medialib/profile/
```

(M0-era manual example, one profile/one top-level file — kept as history.
`hosts/hailo15l/deploy.sh` now does this step for real, both top-level
`garuda_medialib_config*.json` files included via a glob.)

**YOLO11 A/B (2026-09-04):** a third profile, `GarudaYolov8m` (640×640, stretched;
`garuda_medialib_config_yolov8m.json`), was added for the yolov8m A/B (`bench/benchlog.md`
2026-09-03) and is not in the table above — it is reused unchanged, no new profile or plugin, for
the `yolov11m`/`yolov11s` detector A/B added on `feat/hailo15l-kalman-tracker`
(`models/yolov11m_h15l.md`, `models/yolov11s_h15l.md`): both zoo HEFs report the same
`hailortcli parse-hef` input (`UINT8, NV12(320x640x3)`) and on-chip-NMS output shape
(`HAILO NMS BY CLASS`, 80 classes) as yolov8m, so the stock `libyolo_hailortpp_post.so`
post-process + `config/yolov8m_post.json` apply as-is. **`config/perception-yolov11s.json` is the
follow profile** since 2026-09-04 (owner decision after the A/B below — `docs/decisions.md`), so the
deploy command for the follow use case is

```bash
env GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov11s.json \
    hosts/hailo15l/deploy.sh
```

Swap the config path for `perception-yolov11m.json` or `perception-yolov8m.json` (the A/B alternative,
and what every capture before 2026-09-04 evening ran on) to switch detectors the same way. Hailo's
published COCO numbers (float/quantised mAP, fps batch 1, `HAILO15L_object_detection.rst`): yolov11m 50.7/49.5, 33.4 fps; yolov11s 46.1/45.3, 86.7 fps; vs
yolov8m 49.6/48.8, 39.7 fps — quoted from Hailo, not measured on this bench (`TBD-bench` in the
cards). Licence: AGPL-3.0 (Ultralytics YOLO11, compiled by Hailo), eval-only, `not-product-cleared`,
same as yolov8m and yolo26m. On-bench detection numbers for these three HEFs (a phone routine, one
run per model, still-candidate) are in `bench/benchlog.md`, "Hailo-15L SBC: detector A/B on the
phone" (2026-09-04 evening).

**Phone-demo config (on-board fix round 8, Ruling 25):** `config/perception-yolov11s-phone.json` is
`perception-yolov11s.json` plus a two-class allow-list (`tracker.hailo.classes ["person", "cell
phone"]`) and `classification_id -1`, for a person+phone demo without the all-classes clutter — see
§9's `classes` bullet and "Phone-demo config" subsection for the mechanism and full detail. Deploy the
same way as any other detector config, swapping the config path:

```bash
env GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov11s-phone.json \
    hosts/hailo15l/deploy.sh
```

### Resize interpolation method (tried AREA, reverted to BILINEAR, 2026-09-03)

`application_input_streams.method` (all three `application_settings*.json` profiles share the one
`application_settings()` helper in `make_profile.py`) had been `INTERPOLATION_TYPE_BILINEAR` since
M0. Tried switching it to `INTERPOLATION_TYPE_AREA` (libmedialib's schema lists AREA/BICUBIC/
BILINEAR/NEAREST_NEIGHBOR) on the theory that sink0 is a ~6x reduction of the 4K ISP output and
bilinear can alias small targets under a large downscale factor, where AREA (box-filter averaging)
is the textbook-correct resampling method. Regenerated the JSONs and deployed — this board's
currently-flashed DSP resize path **rejects it at runtime**:

```
[hailodsp] [error] [resize.cpp:980] [dsp_telescopic_multi_crop_and_resize_perf] Error: Interpolation type (2) not supported
```

and the pipeline never produced a single frame while it was selected (`/api/state` stuck at
`{"v":2,"tracks":[],"error":"no snapshot yet"}`, no `frames=...` line ever appeared in the log).
Reverted to `INTERPOLATION_TYPE_BILINEAR` (verified: `git diff` of the three `application_settings*.json`
files against their pre-attempt content is empty — regenerating with BILINEAR reproduces them
byte-for-byte) and redeployed; the pipeline was healthy again within one restart (`frames=277
fps=27.7` on the very next log line). `make_profile.py`'s comment records the exact error inline so
a future attempt doesn't have to rediscover it. AREA (or BICUBIC) remains an option worth revisiting
if a future board image's DSP build supports more interpolation types — this board's does not.

### Letterbox for M2

Step 1 lookup (records the scaling-mode enum spellings and per-resolution
keys for the letterbox decision to be made in M2), run verbatim on the
board:

```bash
ssh root@10.0.0.1 'grep -rhoE "\"(DSP_SCALING_MODE|SCALING_MODE)[A-Z_]*\"|scaling_mode" /usr/include/hailo/media_library/*.hpp | sort -u; python3 -c "import json;print(json.dumps(json.load(open(\"/etc/imaging/cfg/hailo15l/imx678/theia_sl410m/4k/profiles/daylight/detection_daylight/application_settings.json\"))[\"application_input_streams\"][\"resolutions\"][0],indent=1))"'
```

Verbatim output:

```
scaling_mode
{
 "framerate": 30,
 "height": 384,
 "pool_max_buffers": 20,
 "stream_id": "sink0",
 "width": 640
}
```

Note: the Step-1 glob (`/usr/include/hailo/media_library/*.hpp`) only turns
up the bare unquoted field name `scaling_mode` (a `dsp_scaling_mode_t`
struct member in `media_library_types.hpp`, and `enum class ScalingMode
{STRETCH, LETTERBOX_MIDDLE, LETTERBOX_UP_LEFT, SCALING_MODE_MAX}` in the
same file) — no `"DSP_SCALING_MODE_..."` or `"SCALING_MODE_..."` quoted
strings live in that header set, and the C-style enum itself lives one
directory up, in `/usr/include/hailo/hailodsp.h` (outside the glob).
Checked separately, verbatim (`grep -n "DSP_SCALING_MODE\|dsp_scaling_mode_t"
/usr/include/hailo/hailodsp.h`):

```
    DSP_SCALING_MODE_STRETCH = 0,       /**< Scale to fill without aspect ratio preservation */
    DSP_SCALING_MODE_LETTERBOX_MIDDLE,  /**< Scale to fit, align the image to the middle */
    DSP_SCALING_MODE_LETTERBOX_UP_LEFT, /**< Scale to fit, align the image up or left */
    DSP_SCALING_MODE_SCALE_AND_CROP,    /**< Scale to fill with aspect ratio preservation */
    DSP_SCALING_MODE_COUNT,
    DSP_SCALING_MODE_MAX_ENUM = DSP_MAX_ENUM
} dsp_scaling_mode_t;
```

The stock per-resolution object has no `scaling_mode` key set (only
`stream_id`, `width`, `height`, `framerate`, `pool_max_buffers` as shown
above) — it relies on the default (`DSP_SCALING_MODE_STRETCH`), so M0's
`sink0`/`sink1` resolutions stretch rather than letterbox.

**Correction (M2, was a guess above):** the per-resolution JSON key does
**not** take the C-style `DSP_SCALING_MODE_...` enum spelling. The schema
enum that `application_settings.json` actually parses against is
`enum class ScalingMode {STRETCH, LETTERBOX_MIDDLE, LETTERBOX_UP_LEFT,
SCALING_MODE_MAX}` (same header, `media_library_types.hpp`) — confirmed
working on the board: `"scaling_mode": "LETTERBOX_MIDDLE"` (no `DSP_` prefix,
no padding-colour field; the DSP fills padding with Y=0, not a configurable
colour — see §8 below). `hosts/hailo15l/medialib/make_profile.py`'s `sink0`
now sets exactly that.

## 5. Portal against the SBC

Proves `garuda-portal` (branch `feat/portal-tracking`, worktree
`.claude/worktrees/feat+portal-tracking/services/garuda-portal/`) consumes
the Hailo-15L board's `garuda-mono` HTTP contract unchanged, by pointing it
at the board's shim (port 8098, Task 8) instead of a co-located garuda-mono.
That worktree was read/run only, never modified — confirmed not with
`git status` (this session's git-worktree isolation sandbox refuses any
git invocation, `-C`/`cd`/`--git-dir`+`--work-tree` all tried, that targets
a path outside its own worktree, even read-only) but by checking every
`.py` source file's mtime against the last commit's dates (all unchanged)
and the worktree's own `.gitignore` (the only fresh files were regenerated
`__pycache__/*.pyc`, already ignored there).

Board side first — node + shim, then confirm the shim answers:

```bash
ssh root@10.0.0.1 'pkill -f "^camera-viewer-server"; cd /opt/garuda && LD_LIBRARY_PATH=/opt/garuda/lib HAILO_MEDIA_LIB_SKIP_METADATA_CONFIG_VALIDATION=1 nohup ./bin/garuda-perception --config /opt/garuda/perception.json > /tmp/perception.log 2>&1 < /dev/null & sleep 8; nohup python3 bin/garuda_mono_shim.py > /tmp/shim.log 2>&1 < /dev/null & sleep 2; tail -2 /tmp/perception.log; tail -1 /tmp/shim.log'
curl -s http://10.0.0.1:8098/api/state | head -c 200
```

Note: as written, the `cd /opt/garuda &&` only scopes the first backgrounded
job (`garuda-perception`) — bash's `&&`/`&` precedence means the second
`nohup python3 bin/garuda_mono_shim.py &` runs in the SSH login shell's own
cwd (`/home/root`), not `/opt/garuda`, and fails
(`python3: can't open file '/home/root/bin/garuda_mono_shim.py'`) the first
time through. Re-running just the shim half with an explicit `cd` for that
command fixed it:

```bash
ssh root@10.0.0.1 'cd /opt/garuda && nohup python3 bin/garuda_mono_shim.py > /tmp/shim.log 2>&1 < /dev/null & sleep 2; tail -5 /tmp/shim.log'
```

Both SSH calls also hit their own `timeout` locally (remote nohup'd
background jobs keep the SSH session's transport open past the point the
script itself has finished — a cosmetic detachment quirk, not a failure:
the intended output had already printed before the timeout fired, and `ps
aux` on the board confirmed the right processes stayed up). `pkill -f
"^camera-viewer-server"` matched nothing (no process by that name exists on
this image) and had no effect either time.

Confirmed running (`ps aux | egrep "garuda-perception|garuda_mono_shim"`):

```
root      3354 51.0  3.8 2221328  74784 ?  Sl  12:01  ./bin/garuda-perception --config /opt/garuda/perception.json
root      3426  1.4  0.8  248004  16856 ?  Sl  12:03  python3 bin/garuda_mono_shim.py
```

`curl -s http://10.0.0.1:8098/api/state | head -c 200`:

```json
{"age_ms":34,"cal":{"fit":null,"n":0},"depth_engine":"y26d","detector":{"mode":"primary","prompt":[]},"distance":{"est_m":null,"raw_m":null,"valid":false},"frame":{"height":720,"width":1280},"gesture":{"held_ms":0,"name":null,"track_id":null},"lock":{"class":"","coasting":false,"id":null},"tracks":[],"v":2}
```

v2 JSON confirmed, `frame` is 1280x720 — safe to point the portal at it.

### Run the portal on the PC, pointed at the board

```bash
GARUDA_MONO_URL=http://10.0.0.1:8098 python3 \
  "/media/bhanu1234/Development/GARUDASDK/.claude/worktrees/feat+portal-tracking/services/garuda-portal/portal.py"
```

It started clean — bound `0.0.0.0:8080`, no exception. Its startup log is
empty by design (the module prints nothing on a clean bring-up; only its
`CameraStream` failure path logs, see below).

### Browser step: not performed, and why

The brief's Step 1 also asks to open `http://127.0.0.1:8080/` in a browser
and confirm the follow view shows the board's stream and boxes. That step
was **not performed** in this run: this session has no browser and no
person available to drive one, and — per the architecture finding below —
it would not have worked unmodified anyway. The portal page's own
JavaScript (`static/app.js`) fetches mono's MJPEG stream and posts
`mono_click` against `` `${location.protocol}//${location.hostname}:8098` ``
— i.e. whatever host the browser loaded the portal page *from*, not
`GARUDA_MONO_URL`. With the portal running on the PC (`127.0.0.1:8080`),
the browser would look for the shim at `127.0.0.1:8098` on the PC — nothing
is listening there — instead of the board's real `10.0.0.1:8098`.

The controller-ruled workaround for a browser session: tunnel the board's
shim port to the PC's loopback before opening the page, so the page's
`location.hostname:8098` lands on the board's shim through the tunnel
instead:

```bash
ssh -N -L 8098:127.0.0.1:8098 root@10.0.0.1
```

Run that on the PC (foreground, or backgrounded) before opening
`http://127.0.0.1:8080/` in a browser; then `location.hostname` (`127.0.0.1`)
combined with the tunnel's local port 8098 reaches the board's shim. The
click-to-lock and box-overlay checks that need a person in view of the
board's camera remain **pending** either way (see below) — the tunnel only
addresses the wrong-host problem, not the missing person.

### What worked (verified without a person in view)

`curl -s -m 3 http://127.0.0.1:8080/api/events | head -c 800` (first ticks
off the SSE stream) — the portal's server-side `MonoClient` (reads
`GARUDA_MONO_URL + /api/events`, republishes on the portal's own bus/SSE)
correctly relays the board's live snapshot end to end:

```
data: {"kind": "mono", "data": {"age_ms": 120, "cal": {"fit": null, "n": 0}, "depth_engine": "y26d", "detector": {"mode": "primary", "prompt": []}, "distance": {"est_m": null, "raw_m": null, "valid": false}, "frame": {"height": 720, "width": 1280}, "gesture": {"held_ms": 0, "name": null, "track_id": null}, "lock": {"class": "", "coasting": false, "id": null}, "tracks": [], "v": 2}, "t_ns": 962108578726417}

data: {"kind": "detections", "data": {"detections": [], "frame": {"width": 1280, "height": 720}}, "t_ns": 962108578777572}

data: {"kind": "follow", "data": {"tracks": [], "command": {"t_ns": 962108579078334, "target_id": null, "yaw_rate": 0.0, "forward_vel": 0.0, "vertical_vel": 0.0, "valid": false, "reason": "no target", "schema": "0.1.0"}}, "t_ns": 962108579113400}
```

`frame` is 1280x720 (matches `curl 10.0.0.1:8098/api/state` above) — this is
the board's own snapshot, unmodified, flowing through the portal's SSE
fan-out (`mono` = raw snapshot, `detections` = the adapted `DetectionSet`
`FollowPipeline` consumes, `follow` = the resulting `FollowCommand`).

`curl -s -m 3 http://127.0.0.1:8080/api/health` also answered normally
(uptime/cpu/loadavg/disk from `probes.py`, `services.*` all `false` since no
systemd units exist on this PC, `camera_mode: "stream"`) — the portal stayed
up and serving throughout.

### What was unavailable on the PC, and why (expected, not failures)

- `/api/stream` (the portal's OWN route, defined in `portal.py`) returned
  empty; `portal.log` shows `CameraStream: failed to start rpicam-vid:
  [Errno 2] No such file or directory: 'rpicam-vid'`. This route serves the
  portal's *local* Pi-camera / inference-preview feed
  (`stream_handler_for()` in `portal.py`) — it has nothing to do with the
  board's mono feed and was never expected to work on a PC with no CM3 and
  no `rpicam-vid` binary. The portal caught the exception and kept serving;
  no crash.
- `/api/config` → `{"ok": false, "detail": "configd unavailable"}` and
  `/api/readiness/report` → several `fail`/`na` checks (`npu.identify`,
  `power.flags`, `thermals`, `bridge.session`) and `services.core: warn` — all
  expected: no `garuda-configd` socket, no NPU/power/thermal sysfs, no FC
  endpoint on this PC. `/api/models` → `[]` (`/usr/share/hailo-models`
  doesn't exist here either). None of these touch the mono relay path.
- Architecture note found while tracing the code (not a PC-only gap — this
  would reproduce on any host where the portal and mono don't share an IP):
  the browser-side JS (`static/app.js`) does **not** use `GARUDA_MONO_URL`.
  Its "Tracking tab" derives the mono base itself —
  `` const mbase = `${location.protocol}//${location.hostname}:8098` `` —
  i.e. "same host the browser loaded the portal page from, port 8098". That
  assumption holds for the normal co-located deployment (portal + mono on
  the same Pi/board) but breaks when the portal runs on a different host
  than mono, as in this test: a browser pointed at
  `http://127.0.0.1:8080/` would try to load the video and POST
  `mono_click` against `127.0.0.1:8098` (nothing there), not
  `10.0.0.1:8098`. `GARUDA_MONO_URL` only wires the portal's server-side
  `MonoClient`/`GestureReactor` (Python), confirmed working above. This is
  why the click check below goes straight at the board with `curl`, per the
  task's own guidance, rather than through the portal UI.

### Click-to-lock check: pending

`tracks` was empty in every `/api/state` snapshot taken during this run (no
person in front of the board's camera), so the click check
(`POST /api/mono_click?x=<cx>&y=<cy>` at a detection's box centre, then
confirming `lock.id` in the next `/api/state`) could not be exercised. Left
**pending** — needs a person in view of the board's camera; not attempted
with fabricated coordinates.

### Cleanup

The PC-side portal process was killed after the checks above (port 8080
confirmed free again). `garuda-perception` and `garuda_mono_shim.py` were
left running on the board.

## 6. Tracking parity check (M1)

Task 5 (tracker + lock resolver ported into the node, `cc87ae5`/`24dca06`) asked
for three scenarios in the portal's Tracking tab: click a person → the
highlight persists; walk out and back → dimmed (coasting) then restored;
switch the class dropdown to one the stock model lacks → lock clears.

This run happened at night with nobody at the bench, so — per controller
ruling — only what could be verified over HTTP, with no person in front of
the board's camera, was exercised now; the rest is recorded below as
**pending owner presence**. The setup was the one already up from the M0
section above: `garuda-portal` running on the PC
(`GARUDA_MONO_URL=http://127.0.0.1:8098`, port 8080) plus the SSH tunnel
`ssh -f -N -L 8098:127.0.0.1:8098 root@10.0.0.1`, both left running
throughout and untouched by this check.

**Threshold note (2026-09-03, updated for M2):** the node's detect-stage NMS score threshold was
moved to `track.conf_floor` (0.15, `24dca06`) so ByteTrack's low-score band would have candidates
to re-associate against; under M0/M1 the stock post-process's own `detection_threshold` (0.38,
`/home/root/apps/shared/resources/configs/yolov8.json` on the board) floored higher than that, so
the low band was inert. **The low band is live since M2**: `libyolo26_post.so`'s own
`conf_thresh` (0.15, `/opt/garuda/yolo26_post.json`) matches `track.conf_floor` exactly, so
ByteTrack's `[low_thr=0.12, high_thr=0.40)` re-association band now has real candidates below
0.38 to work with. The stock 0.38 post-process is only reachable via the rollback config (§8
"Rollback command") — see `bench/benchlog.md` 2026-09-03 "Hailo-15L SBC: M2 yolo26m detector" for
the tally evidence, and `docs/decisions.md` 2026-09-03 for the M1-era evidence this note
originally recorded.

### What changes for a portal user vs M0

All of the below is intended mono parity, not new behaviour:

- **Track ids are persistent and 1-based** (M0 published a per-frame 0-based index as the "id",
  which was not stable across frames).
- **Only confirmed tracks are published** — a track needs `min_hits` (2) consecutive hits before it
  appears in `tracks[]`; M0 published every raw detection immediately.
- **Coasting tracks stay visible with a predicted box** and carry `"coasting": true` while missed
  (up to `max_lost` frames) instead of disappearing on the first missed frame.
- **The lock auto-acquires the default class** as soon as a matching track is confirmed — M0 never
  auto-locked anything; a lock required an explicit click.
- **`lock.class` defaults to `"person"`**, where M0 left it empty (`""`) until a click or target
  command set it.

### Verified (no person needed)

Portal page loads:

```
$ curl -s http://127.0.0.1:8080/ | head -c 400
<!doctype html>
<html lang="en">
...
<title>Garuda Portal</title>
```

The portal's server-side state proxy reflects the board's live `lock.class`.
Flipped the class on the board directly (mirrors what the Tracking tab's
class dropdown does — see `static/app.js:1021`,
`` fetch(`${mbase}/api/mono_target?class=...`) ``) and read it back through
the portal's own SSE relay (`/api/events`, `kind: "mono"`):

```
$ curl -s http://10.0.0.1:8098/api/state | head -c 120
{"age_ms":32, ... "lock":{"class":"person","coasting":false,"id":null}, ...

$ curl -s -X POST "http://10.0.0.1:8098/api/mono_target?class=vehicle"
{"ok": true}

$ curl -s http://10.0.0.1:8098/api/state | head -c 120
{"age_ms":32, ... "lock":{"class":"vehicle","coasting":false,"id":null}, ...

$ curl -s -m 3 http://127.0.0.1:8080/api/events | grep -m1 '"kind": "mono"'
data: {"kind": "mono", "data": {..., "lock": {"class": "vehicle", ...}, ...}}
```

Restored to `person` (the resting default) the same way and confirmed both
the board and the portal's relay reported it back:

```
$ curl -s -X POST "http://10.0.0.1:8098/api/mono_target?class=person"
{"ok": true}
$ curl -s http://10.0.0.1:8098/api/state | head -c 120
{"age_ms":36, ... "lock":{"class":"person","coasting":false,"id":null}, ...
$ curl -s -m 3 http://127.0.0.1:8080/api/events | grep -m1 '"kind": "mono"'
data: {"kind": "mono", "data": {..., "lock": {"class": "person", ...}, ...}}
```

Confirmed the Tracking tab's JS talks to the same two endpoints the brief's
scenarios exercise (`static/app.js`, worktree `feat+portal-tracking`):

```
474:  fetch(`${mbase}/api/mono_click?x=...&y=...`, ...)
1021:    fetch(`${mbase}/api/mono_target?class=${encodeURIComponent(e.target.value)}`, { method: "POST" })
```

i.e. clicking a box in the tab posts to `/api/mono_click` (the node's
`lock_point` command) and the class dropdown posts to `/api/mono_target`
(the node's `target` command) — both landed correctly above.

### Pending owner presence

`tracks` was empty throughout this run (no person in front of the board's
camera), so none of the three scenarios that need an actual detection to
lock onto could be exercised:

- **Click persists the highlight** — needs a person in frame to click on.
- **Walk out and back → dimmed (coasting) then restored** — needs a person
  to walk out of and back into frame while locked.
- **Switch to an unsupported class → lock clears** — needs an *established*
  `lock.id` first (a person must already be locked) before switching the
  class can be observed clearing it; with no detections, `lock.id` is
  already `null`, so flipping the dropdown (verified above) doesn't
  distinguish "cleared" from "was never set".

All three remained pending until the owner was at the bench later on 2026-09-03; status now:

- **Walk out and back** — OBSERVED and measured (`bench/benchlog.md` M1 section, "ADDENDUM
  2026-09-03 (owner present) — coast window"): with mono's `max_lost=25` the locked person
  coasted 0.80–0.90 s and then died on every absence of a second or more (the board detects at
  ~30 fps, so 25 frames is 0.8 s of wall-clock); 0.1–0.2 s flickers kept the id. The board config
  now carries `max_lost=75`, `reacq=15` (about 2.5 s / 0.5 s at 30 fps); measured coasts after the
  change: 2.41 s and 2.61 s before dying. Re-entering the frame at a different spot still mints a
  new id even inside the window (the matcher is IoU-only, exactly as in mono), and the lock then
  moved to the live person 0.5 s later (re-acquire rule) — see the evidence file.
- **Click persists the highlight** — seen by the owner in the portal (Follow on a person box held
  until the walk-out) but not captured in a timeline; treat as observed, not measured.
- **Switch to an unsupported class → lock clears** — still pending (not exercised with an
  established lock).
- **M2 detector run (2026-09-03, `bench/benchlog.md` "2026-09-03 — Hailo-15L SBC: M2 yolo26m
  detector")** — a person was in view for the entire 600 s run: `lock.id` was `1` and
  `lock.coasting` was `false` on all 5,969 SSE snapshots (never changed, never coasted), so this
  run adds nothing to the walk-out/back or unsupported-class-clears items above — they remain as
  stated. The run's tally (`bench/evidence/2026-09-03-m2-sse-tally.txt`) lists the distinct COCO
  labels seen across all tracks: `['book', 'cell phone', 'chair', 'person', 'refrigerator',
  'suitcase']`.

## 7. NV12 frame dump (`dump_nv12`, M1)

`config/perception.json` carries an optional `dump_nv12` block:

```json
"dump_nv12": { "path": "", "frames": 0 }
```

Disabled by default (`frames: 0`). When both `path` is non-empty and
`frames > 0`, `det_sink` (`services/garuda-perception/src/node_main.cpp`)
writes the first `frames` `sink0` (detector-input) NV12 frames to `path`
(the file is opened with `std::ios::trunc`, not appended to — a re-run
overwrites any previous capture at the same path),
Y plane then UV plane, each written row-by-row with the media-library
buffer's stride stripped — so the file is a plain, back-to-back NV12
sequence with no per-row padding. After the last frame it logs exactly:

```
dumped <frames> frames to <path>
```

once, closes the file, and stops dumping (no threads; a lazily-opened
`std::ofstream`, closed after the last write).

**File layout** — config-driven since M2 (`dump_nv12.width`/`height` in `perception.json`; under
M0/M1 these were not yet config fields and the layout was fixed at the then-only profile's
`sink0` geometry). `perception.json` (the M2/yolo26m default) sets `dump_nv12.width`/`height` to
640x640, matching the `Garuda` profile's letterboxed `sink0`; `perception-yolov8n.json` (the
rollback config, §8) sets them to 640x384, matching the `GarudaYolov8n` profile's stretched
`sink0` (`hosts/hailo15l/medialib/make_profile.py`). Independent either way of `frame_w`/
`frame_h` in `perception.json`, which is the 1280x720 full-FOV frame used only for detection bbox
scaling:

- 640x640 (M2 default) or 640x384 (rollback) NV12, 30 fps (the profile's configured `sink0`
  framerate).
- Per frame at 640x640: 640x640 = 409600 Y bytes, then 640x320 = 204800 UV bytes →
  **614400 bytes/frame**. Per frame at 640x384 (rollback): 640x384 = 245760 Y bytes, then
  640x192 = 122880 UV bytes → **368640 bytes/frame**. Both stride-stripped (plain, tightly packed
  rows).
- File size = `frames × 614400` (M2) or `frames × 368640` (rollback) bytes.

**Clip captured**: 300 frames (frame count is configured; the profile's
`sink0` framerate is 30 fps, and the det_sink log during this capture read
`frames=277 fps=27.7` — see the transcript below, copied verbatim) to
`/opt/garuda/state/clip-640x384.nv12` on the board, then copied to the PC.
This was an **empty-scene clip** — no person was at the bench (night,
nobody available) — captured purely to prove the dump path end to end; a
person-in-frame clip is pending owner presence, same as §6 above.

```
$ ssh root@10.0.0.1 '... edit /opt/garuda/perception.json dump_nv12 → path/frames ...; /etc/init.d/garuda-perception restart'
$ ssh root@10.0.0.1 'tail -3 /var/log/garuda-perception.log'
frames=277 fps=27.7
dumped 300 frames to /opt/garuda/state/clip-640x384.nv12

$ ssh root@10.0.0.1 'ls -l /opt/garuda/state/clip-640x384.nv12'
-rw-r--r-- 1 root root 110592000 ... clip-640x384.nv12      # 300 * 368640

$ scp root@10.0.0.1:/opt/garuda/state/clip-640x384.nv12 /media/bhanu1234/Development/hailo15/clips/
$ md5sum on both sides matched (a5f4d4100feb04107ad2b8f0721319a0)
```

Not committed — see `docs/decisions.md` (2026-09-03) for the PC-side path.
After the capture, the board's `perception.json` was restored to the
disabled values (via `hosts/hailo15l/deploy.sh`, which always copies the
committed config) and the service restarted; confirmed healthy
(`/etc/init.d/garuda-perception status` → running, log clean, `/api/state`
answering with `lock.class: "person"` as before).

## 8. yolo26m on the board (M2)

Task 4 puts the Hailo model-zoo `yolo26m` HEF and `libyolo26_post.so` (Task 3's
own six-head decode plugin, `services/garuda-perception/postprocess/`) live on
the board in place of the vendor's stock `yolo_hailortpp_post` + `yolov8n`
path. `sink0` (the detector input) is now letterboxed 640x640
(`LETTERBOX_MIDDLE`, §4 above) instead of stretched 640x384, matching
`yolo26m`'s square input; `frame_w`/`frame_h` (1280x720, the full FOV used for
bbox scaling) are unchanged.

### What runs

`/opt/garuda/perception.json` (yolo26m, committed default):

```json
"hef": "/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef",
"postprocess_so": "/opt/garuda/lib/libyolo26_post.so",
"postprocess_config": "/opt/garuda/yolo26_post.json",
```

`/opt/garuda/yolo26_post.json` (deployed from
`services/garuda-perception/config/yolo26_post.json`) carries `conf_thresh`
(0.15, matching `perception.json`'s `track.conf_floor`), `iou_thresh`,
`in_w`/`in_h` (640x640), `frame_w`/`frame_h` (1280x720, must equal
`perception.json`'s), `mode: "letterbox"`, the `yolo26m/` tensor prefix, and
the 80 COCO labels the plugin validates against `garuda::yolo26::COCO` at
init (a mismatch there is a hard init failure, not a silent wrong label).

### The config switch

`hosts/hailo15l/deploy.sh` reads `GARUDA_PERCEPTION_CONFIG` (default
`services/garuda-perception/config/perception.json`) and copies whichever
file it names to `/opt/garuda/perception.json` on the board — the source
filename never survives the copy, so the board only ever sees
`perception.json`. The same run also lands the yolo26m model artifacts
(`libyolo26_post.so`, `yolo26_post.json`, the HEF via an md5-gated copy) and
both top-level media-library configs (`garuda_medialib_config.json`,
`garuda_medialib_config_yolov8n.json`, glob-copied) — unconditional and
harmless when the selected config is the stock one, since the yolo26m
artifacts just sit unused and the "Garuda"-profile top-level file isn't the
one `perception-yolov8n.json` points at.

### Rollback command

```bash
GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json hosts/hailo15l/deploy.sh
```

`config/perception-yolov8n.json` restores the stock detector paths (`hef`,
`postprocess_so`, `postprocess_config`), and — the one addition beyond a
verbatim copy of the pre-Task-4 file — points `medialib_config` at
`garuda_medialib_config_yolov8n.json` and `profile` at `GarudaYolov8n`
(§4's second profile: `sink0` 640x384, the stock HEF's native input shape)
instead of `garuda_medialib_config.json`/`Garuda`; `dump_nv12`'s
`width`/`height` are 640x384 to match.

**A first attempt at this rollback was wrong, and is left here as the
record of what didn't work and why.** The initial fix (round 1, first pass)
added the `GarudaYolov8n` *profile* but kept ONE shared top-level
`garuda_medialib_config.json` (`default_profile: "Garuda"`) with both
profiles listed, relying on the node's `media->set_profile(cfg["profile"])`
call (`node_main.cpp`, after `initialize()`) to hot-switch `sink0` to
640x384 at runtime. It did not work — deploying `perception-yolov8n.json`
that way produced a node that started and stayed up (feed/command ports
open, service reports running) but failed every inference call:

```
[HailoRT] [error] CHECK failed - Input buffer size 614400 is different than expected 368640 for input 'hailo_yolov8n_384_640/input_layer1'
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
[...] [hailo_analytics] [error] [ai_stage.cpp:353] [infer] Failed to start async infer job, status = 6
[...] [hailo_analytics] [error] [ai_stage.cpp:444] [process] [detect] Inference failed
[...] [hailo_analytics] [warning] [stage.cpp:143] [loop] Stage detect failed to process buffer
```

368640 = 640×384×1.5 (the stock HEF's expected input); 614400 = 640×640×1.5
— `sink0` was still physically 640x640 despite `set_profile("GarudaYolov8n")`
succeeding (no "set_profile failed" in the log, node stayed up). Root-caused
by two on-board tests: restarting `isp_media_server` itself (a completely
fresh ISP daemon, ruling out ISP-side stream/format caching) did **not**
clear it; manually flipping the shared file's `default_profile` to
`"GarudaYolov8n"` and restarting only `garuda-perception` **did** — the node
then ran the stock detector cleanly at 640x384. Conclusion: `initialize()`
commits `sink0`'s actual physical geometry from the medialib config's own
`default_profile` at that call; the later `set_profile(cfg["profile"])` call
does not renegotiate an already-different sink geometry — it only succeeds
because the *name* it's given is valid, not because it actually changes
anything sink0-shaped.

**The fix that actually works** (current state, §4): two top-level
`garuda_medialib_config*.json` files, one per profile, each with that
profile as its own `default_profile`; each `perception*.json`'s own
`medialib_config` field (already a per-config key, unrelated to this bug)
selects between them. `set_profile()` still runs afterward and still
succeeds, now as a no-op re-affirmation of whichever profile is already
live. Verified for real — see "Rollback verification, both ways" below for
both directions (rollback and back to yolo26m), each with a clean log and a
timestamped `/api/state` poll.

### Pad-colour observation

A one-frame `dump_nv12` capture at the node's now-current 640x640 geometry
(`dump_nv12.width`/`height`, §7) shows the Y plane's padding rows (0-139 and
500-639) are constant, and the content band (rows 140-499) is not:

```
row0  min/max/mean: (0, 0, 0.0)
row639 min/max/mean: (0, 0, 0.0)
row140 min/max/mean: (30, 154, 108.5953125)
row300 min/max/mean: (32, 213, 103.615625)
row499 min/max/mean: (18, 155, 81.0875)
row500 min/max/mean: (0, 0, 0.0)
```

The Hailo-15L DSP's `LETTERBOX_MIDDLE` pads with **Y=0** (black), not the
Pi's software letterbox padding value of 114 (mid-grey) — there is no
padding-colour field in the schema to change this. The 140-row band on each
side matches the expected geometry exactly: scaling 1280x720 into a 640-wide
frame gives 640×(720/1280) = 360 content rows, centred in 640 with
(640-360)/2 = 140 rows of padding top and bottom.

### What changes for a portal user vs M1

- **COCO-80 labels, not just person/face.** M1 ran the stock detector, whose
  post-process only ever emits `person`/`face`. yolo26m's plugin emits the
  full COCO-80 set; on this bench (a chair, suitcases, books, a ring light,
  a desk) that means labels like `suitcase`, `book`, `chair`, `refrigerator`
  alongside `person` — see the live capture below.
- **The class dropdown now works against real classes.** M1's `target`
  command accepted any string but the stock detector could never produce a
  match for anything but `person`/`face`; with yolo26m, selecting e.g.
  `suitcase` in the Tracking tab can actually acquire a lock.
- **The live confidence band moved, but is not `[low_thr, high_thr)`.**
  `docs/decisions.md` 2026-09-03 (M1) noted the stock post-process floored at
  `detection_threshold 0.38`, above ByteTrack's `low_thr` (0.12) — so the
  coast/re-acquire band never saw a flicker below 0.38. The plugin floors at
  `conf_thresh` (0.15), which is itself ABOVE `low_thr` (0.12), and det_sink
  drops anything below `track.conf_floor` (also 0.15, `node_main.cpp`) before
  it ever reaches the tracker — so the `[0.12, 0.15)` sliver between `low_thr`
  and the plugin's own floor is still unreachable. The actual live band is
  `[0.15, 0.40)`, not `[0.12, 0.40)`: an improvement over M1's `[0.38, ...)`-
  only floor, but the two floors (plugin `conf_thresh` and `track.conf_floor`)
  landing on the same value (0.15) is what makes them look like one live band
  starting at `low_thr` when they don't.

### Live verification (owner present, 2026-09-03)

Deploy:

```
$ hosts/hailo15l/deploy.sh
Thu Sep  3 07:13:40 UTC 2026
garuda-perception stopped
yolo26m HEF already on board and md5-verified, skipping copy
garuda-perception stopped
garuda-perception: starting in background (log: /var/log/garuda-perception.log)
/var/run/garuda-perception.pid running (pid 4889)
/var/run/garuda-mono-shim.pid running (pid 4918)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```

Log tail (`tail -30 /var/log/garuda-perception.log`), plugin init line and
frame-rate lines:

```
Thu Sep  3 07:13:51 UTC 2026 starter begin (pid 4885)
Thu Sep  3 07:13:52 UTC 2026 starter done: node 4889, shim 4918
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
yolo26_post: conf=0.150 iou=0.50 net=640x640 frame=1280x720 mode=letterbox prefix=yolo26m/ dump=/0
garuda-perception running (feed 8971, cmd 8972)
frames=232 fps=23.2
```

`/api/state` polled six times over a minute
(`curl -s http://10.0.0.1:8098/api/state | python3 -c "..."`, printing
`lock` and `(id, label, conf)` per track):

```
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.74), (3, 'book', 0.41), (4, 'suitcase', 0.16), (5, 'book', 0.34), (6, 'suitcase', 0.27), (7, 'book', 0.42), (9, 'book', 0.2), (10, 'book', 0.28), (11, 'person', 0.97)]
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.75), (3, 'book', 0.4), (4, 'suitcase', 0.31), (5, 'book', 0.26), (6, 'suitcase', 0.31), (7, 'book', 0.4), (9, 'book', 0.18), (10, 'book', 0.31), (11, 'person', 0.97)]
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.77), (3, 'book', 0.46), (4, 'suitcase', 0.34), (5, 'book', 0.35), (6, 'suitcase', 0.22), (7, 'book', 0.38), (9, 'book', 0.21), (10, 'book', 0.34), (11, 'person', 0.97)]
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.67), (3, 'book', 0.42), (4, 'suitcase', 0.35), (5, 'book', 0.48), (6, 'suitcase', 0.36), (7, 'book', 0.42), (9, 'book', 0.22), (10, 'book', 0.27), (11, 'person', 0.97)]
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.74), (3, 'book', 0.47), (4, 'suitcase', 0.54), (5, 'book', 0.42), (6, 'suitcase', 0.39), (7, 'book', 0.33), (9, 'book', 0.2), (10, 'book', 0.38), (11, 'person', 0.97), (12, 'refrigerator', 0.23)]
{'class': 'person', 'coasting': False, 'id': 11} [(2, 'suitcase', 0.65), (3, 'book', 0.51), (4, 'suitcase', 0.43), (5, 'book', 0.38), (6, 'suitcase', 0.32), (7, 'book', 0.47), (9, 'book', 0.22), (10, 'book', 0.3), (11, 'person', 0.97), (12, 'refrigerator', 0.3)]
```

The yolo26m HEF has no baked NMS, but HailoRT accepted the node's existing
`set_nms_score_threshold` call unchanged — no error mentioning nms/score
threshold ever appeared in the log — so no new config key was needed. Only
the call's comment (`src/node_main.cpp`) was updated to note it has no
effect on this HEF.


### Rollback verification, both ways (fix round 1, 2026-09-03)

With the real two-top-level-config fix (see "Rollback command" above) in
place. Three rollback deploys were made this round: the first two caught an
empty room (no owner at the bench — confirmed visually via a captured MJPEG
frame, not just inferred from empty `tracks[]`); the third caught the owner
returning, and is the one with the requested stock `person`/`face`
detections.

**Rollback attempt 1** — deploy, config, and log confirmed correct and
clean; `/api/state` empty across 21 polls, `13:07:36`-`13:10:10`:

```
$ GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json hosts/hailo15l/deploy.sh
Thu Sep  3 07:36:57 UTC 2026
garuda-perception stopped
yolo26m HEF already on board and md5-verified, skipping copy
garuda-perception stopped
garuda-perception: starting in background (log: /var/log/garuda-perception.log)
/var/run/garuda-perception.pid running (pid 6446)
/var/run/garuda-mono-shim.pid running (pid 6505)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```

```
$ ssh root@10.0.0.1 'cat /opt/garuda/perception.json | python3 -c "..."'
/opt/garuda/medialib/garuda_medialib_config_yolov8n.json GarudaYolov8n /home/root/apps/shared/resources/hailo_yolov8n_384_640.hef
```

Log tail — clean, stock frame rate, **zero HailoRT errors** (checked with
`awk`/`grep -c` from this run's own `starter begin (pid 6442)` line onward,
result `0`):

```
Thu Sep  3 07:37:07 UTC 2026 starter begin (pid 6442)
garuda-perception running (feed 8971, cmd 8972)
Thu Sep  3 07:37:09 UTC 2026 starter done: node 6446, shim 6505
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=278 fps=27.8
```

`/api/state`, timestamped, all empty (nobody in frame):

```
13:07:36 {'class': 'person', 'coasting': False, 'id': None} []
13:07:48 {'class': 'person', 'coasting': False, 'id': None} []
13:07:53 {'class': 'person', 'coasting': False, 'id': None} []
13:07:58 {'class': 'person', 'coasting': False, 'id': None} []
13:08:03 {'class': 'person', 'coasting': False, 'id': None} []
13:08:08 {'class': 'person', 'coasting': False, 'id': None} []
13:08:34 {'class': 'person', 'coasting': False, 'id': None} []
13:08:39 {'class': 'person', 'coasting': False, 'id': None} []
13:08:44 {'class': 'person', 'coasting': False, 'id': None} []
13:08:49 {'class': 'person', 'coasting': False, 'id': None} []
13:08:54 {'class': 'person', 'coasting': False, 'id': None} []
13:08:59 {'class': 'person', 'coasting': False, 'id': None} []
13:09:30 {'class': 'person', 'coasting': False, 'id': None} []
13:09:35 {'class': 'person', 'coasting': False, 'id': None} []
13:09:40 {'class': 'person', 'coasting': False, 'id': None} []
13:09:45 {'class': 'person', 'coasting': False, 'id': None} []
13:09:50 {'class': 'person', 'coasting': False, 'id': None} []
13:09:55 {'class': 'person', 'coasting': False, 'id': None} []
13:10:00 {'class': 'person', 'coasting': False, 'id': None} []
13:10:05 {'class': 'person', 'coasting': False, 'id': None} []
13:10:10 {'class': 'person', 'coasting': False, 'id': None} []
```

(30.0/30.1 fps seen across this run's fuller log matches the stock
detector's known rate from the M1 section above — noticeably faster than
yolo26m's ~23-26 fps, corroborating that the lighter stock model is really
the one running, not a cached yolo26m pipeline that merely didn't error.) A
frame grabbed from the live MJPEG feed shortly after
(`curl http://10.0.0.1:8098/stream`, first JPEG extracted from the
multipart stream) confirmed the room really was empty at the time: the
bench scene (bookshelf, pink cabinet, ring light, three suitcases, an office
chair, a curtained window) with no person in view.

**Rollback attempt 2** (redeployed the same rollback config to retry) —
again clean, again empty, 10 polls `13:14:21`-`13:15:06`:

```
$ GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json hosts/hailo15l/deploy.sh 2>&1 | tail -3
/var/run/garuda-mono-shim.pid running (pid 7050)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```

Log tail — clean, zero HailoRT errors (checked from `starter begin
(pid 6987)` onward, result `0`):

```
07:45:25
frames=257 fps=25.7
Thu Sep  3 07:44:12 UTC 2026 starter begin (pid 6987)
garuda-perception running (feed 8971, cmd 8972)
Thu Sep  3 07:44:14 UTC 2026 starter done: node 6991, shim 7050
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=277 fps=27.7
frames=299 fps=29.9
frames=300 fps=30.0
frames=301 fps=30.1
frames=301 fps=30.1
frames=300 fps=30.0
frames=300 fps=30.0
```

```
13:14:21 {'class': 'person', 'coasting': False, 'id': None} []
13:14:26 {'class': 'person', 'coasting': False, 'id': None} []
13:14:31 {'class': 'person', 'coasting': False, 'id': None} []
13:14:36 {'class': 'person', 'coasting': False, 'id': None} []
13:14:41 {'class': 'person', 'coasting': False, 'id': None} []
13:14:46 {'class': 'person', 'coasting': False, 'id': None} []
13:14:51 {'class': 'person', 'coasting': False, 'id': None} []
13:14:56 {'class': 'person', 'coasting': False, 'id': None} []
13:15:01 {'class': 'person', 'coasting': False, 'id': None} []
13:15:06 {'class': 'person', 'coasting': False, 'id': None} []
```

A second MJPEG frame grabbed at `13:15:42` confirmed the room was still
empty. Attempts 1+2 together: 31 polls, roughly 8 minutes wall-clock,
consistently "camera sees an empty room" — the pipeline itself verified
correct and healthy throughout (matching stock fps, zero HailoRT errors,
correct config/profile selection) even though no detection could fire.

**Rollback attempt 3** (redeployed the same rollback config once more,
after also re-confirming yolo26m worked in between) — the owner had
returned:

```
$ GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json hosts/hailo15l/deploy.sh 2>&1 | tail -3
/var/run/garuda-mono-shim.pid running (pid 7572)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```

Config confirmed switched (`medialib_config`/`profile`/`hef`/`postprocess_so`
all the stock quadruple):

```
07:49:29
/opt/garuda/medialib/garuda_medialib_config_yolov8n.json GarudaYolov8n /home/root/apps/shared/resources/hailo_yolov8n_384_640.hef /usr/lib/hailo-post-processes/libyolo_hailortpp_post.so
```

Log tail — clean, stock frame rate:

```
frames=257 fps=25.7
frames=257 fps=25.7
frames=258 fps=25.8
frames=258 fps=25.8
frames=257 fps=25.7
Thu Sep  3 07:48:51 UTC 2026 starter begin (pid 7509)
garuda-perception running (feed 8971, cmd 8972)
Thu Sep  3 07:48:54 UTC 2026 starter done: node 7513, shim 7572
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=278 fps=27.8
frames=301 fps=30.1
frames=300 fps=30.0
```

`/api/state`, timestamped, 5 polls — **the stock detector live, person/face
labels, exactly as requested:**

```
13:19:02 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.93), (2, 'face', 0.84)]
13:19:06 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.94), (2, 'face', 0.83)]
13:19:10 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.88), (2, 'face', 0.81)]
13:19:14 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.89), (2, 'face', 0.78)]
13:19:18 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.88), (2, 'face', 0.65)]
```

This confirms the fix end to end: the real `deploy.sh` rollback command,
with no manual board edits, produces a working stock detector — sink0 at
640x384, `hailo_yolov8n_384_640` accepting its input cleanly, `person`/`face`
labels flowing through the same tracker/lock path as yolo26m. (An earlier,
purely diagnostic data point pointed the same way before the real fix was
even written: manually flipping `default_profile` on the board's — then
still single, since superseded — shared medialib config also produced
`person 0.94`/`face 0.92` at `13:04:15`, which is what confirmed the root
cause in the first place; that one predates this task's committed files and
is not part of the delivered fix's own evidence trail, included here only
for completeness.)

**Returning to yolo26m** (final restore, full deploy transcript):

```
$ hosts/hailo15l/deploy.sh
Thu Sep  3 07:49:37 UTC 2026
garuda-perception stopped
yolo26m HEF already on board and md5-verified, skipping copy
garuda-perception stopped
garuda-perception: starting in background (log: /var/log/garuda-perception.log)
/var/run/garuda-perception.pid running (pid 7770)
/var/run/garuda-mono-shim.pid running (pid 7834)
/var/run/garuda-perception-starter.pid finished
deployed to root@10.0.0.1
```

Config confirmed back to yolo26m, log tail clean with the plugin init line:

```
07:50:04
/opt/garuda/medialib/garuda_medialib_config.json Garuda /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef
---LOG---
frames=300 fps=30.0
frames=301 fps=30.1
Thu Sep  3 07:49:47 UTC 2026 starter begin (pid 7766)
yolo26_post: conf=0.150 iou=0.50 net=640x640 frame=1280x720 mode=letterbox prefix=yolo26m/ dump=/0
garuda-perception running (feed 8971, cmd 8972)
Thu Sep  3 07:49:50 UTC 2026 starter done: node 7770, shim 7834
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=233 fps=23.3
```

`/api/state`, timestamped, 3 polls — owner still present, person locked at
0.97 alongside the COCO-80 furniture labels (unlike the stock path, which
only ever emits `person`/`face`):

```
13:20:05 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.97), (2, 'chair', 0.67), (3, 'suitcase', 0.57), (4, 'book', 0.49), (5, 'book', 0.45), (6, 'book', 0.3), (7, 'suitcase', 0.39), (8, 'book', 0.29)]
13:20:09 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.97), (2, 'chair', 0.56), (3, 'suitcase', 0.62), (4, 'book', 0.46), (5, 'book', 0.36), (6, 'book', 0.3), (7, 'suitcase', 0.39), (8, 'book', 0.23)]
13:20:13 {'class': 'person', 'coasting': False, 'id': 1} [(1, 'person', 0.97), (2, 'chair', 0.53), (3, 'suitcase', 0.56), (4, 'book', 0.5), (5, 'book', 0.43), (6, 'book', 0.28), (7, 'suitcase', 0.34), (8, 'book', 0.26)]
```

Board left on this state: committed yolo26m config, healthy, detecting.

## 9. Tracker engines (M3 — SDK Kalman tracker)

`config/perception*.json`'s new `tracker` block selects which engine produces the per-frame,
per-track `TrackRecord`s that `LockResolver::step()` (`include/garuda/lock.hpp`) consumes; both
engines feed the same resolver, so click/target/coast/re-acquire behaviour and the `/api/state`
schema are identical either way — only the id/box source changes.

```json
"tracker": { "engine": "mono" }
```
```json
"tracker": {
  "engine": "hailo",
  "hailo": {
    "classification_id": 1,
    "kalman_distance": 0.7, "iou_threshold": 0.8, "init_iou_threshold": 0.9,
    "keep_tracked_frames": 5, "keep_new_frames": 5, "keep_lost_frames": 75, "min_hits": 1
  }
}
```

- **`"mono"`** (default; the field is optional and absent → `"mono"`) — the existing ported
  ByteTrack (`include/garuda/bytetrack.hpp`) running inside `det_sink`, unchanged by this feature.
  `config/perception.json` uses it.
- **`"hailo"`** — inserts the SDK's Kalman `TrackerStage` (`hailo_analytics/pipeline/ai/tracker_stage.hpp`)
  into the pipeline between `"post"` and `"det_sink"` (`post → tracker → det_sink`, `queue_size 1`,
  leaky). The stage assigns and holds each track's id internally (Kalman-filtered box + IoU/embedding
  association, `hailo_postprocess_tools/tracking/hailo_tracker.hpp`); `det_sink` reads that id off each
  detection's `HailoUniqueID` (`hailo_common::get_hailo_track_id()`, `TRACKING_ID` mode — a detection
  can also carry a `GLOBAL_ID`-mode one, which this node ignores) and adapts the id+box stream to
  `TrackRecord`s via `HailoTrackAdapter` (`include/garuda/hailo_track_adapter.hpp`), then calls the
  same `resolver.step(records)` the mono path calls. `set_block_non_tracked_classification_id(false)`
  means a detection of a class the stage isn't tracking (or one it simply hasn't assigned an id to
  yet, e.g. still warming up) still reaches `det_sink` rather than disappearing upstream — it carries
  no tracking id there, so it is dropped by the existing missing-id path (a warn-once line, `hailo
  tracker: N detection(s) with no tracking id this frame, dropped`) rather than becoming a track or a
  snapshot entry. The three detector configs use this engine — `config/perception-yolov11s.json` (the
  follow profile since 2026-09-04), `config/perception-yolov11m.json` and
  `config/perception-yolov8m.json` (the A/B alternatives) — with identical `tracker`/`lock` blocks,
  differing only in `hef`.
- **`classification_id`** (in the `hailo` block, default `-1`) is the class id
  `TrackerStageBuild::Builder::set_classification_id()` passes to the stage — which class(es) the
  SDK's Kalman tracker runs its association on. `-1` (the field's default here; the Builder's own
  internal default is `1`, always overridden by this node) tracks every class. **Field finding,
  2026-09-03, corrected 2026-09-04 (the mechanism below replaces an earlier, wrong "associates
  ACROSS classes" claim — see the final-fix-wave brief's I2):** the JDE tracker
  (`hailo_postprocess_tools/tracking/hailo_tracker.hpp`, `src/tracking/jde_tracker/`) is
  **class-agnostic** — it has no class anywhere in its association at all. Every detection in a
  frame, of any label, competes in the SAME single one-to-one LAPJV (Linear Assignment Problem,
  Jonker-Volgenant) assignment against the same pool of existing tracks. So with `-1` (every class
  fed to the tracker), an overlapping detection of a DIFFERENT class on the same physical object (a
  person momentarily scored higher as `chair`/`suitcase`/`scissors` than `person`, for instance)
  competes for that object's track slot in the same assignment problem as the correct detection, and
  can win it (the id sticks to the wrong-class box) or split it (the real detection goes unmatched
  and mints a brand-new id) — which is a different failure from the one the majority-vote label fix
  (`18af174`) addresses: that fix stops a stray frame from relabelling `cls` on an id that survives,
  but does nothing if the tracker's own assignment loses the id to a competing class's box entirely.
  Setting `classification_id` to one specific class id does not turn on per-class association inside
  the tracker — there is no such mode — it is the demo-style fix the stock TAPPAS examples use:
  only that class's detections are ever handed to the tracker at all, so nothing else can ever
  compete for a track slot; every other class's detections are still seen by the detector and still
  reach `det_sink` (`block_non_tracked_classification_id(false)`), but never get a tracking id and so
  never appear as a track. All three detector configs (`perception-yolov11s.json`,
  `perception-yolov11m.json`, `perception-yolov8m.json`) set `classification_id: 1`. Evidence of
  the churn this causes under `-1`: 22 distinct person-labelled ids appear within just the first 61 s
  of `person_kalman.txt`'s 150 s span (`bench/benchlog.md` 2026-09-03 section, Findings). Note: the
  SDK also ships `LightweightTrackerStage` (genuine per-class matching, configurable smoothing) and
  `DetectionTrackerStage` as alternative tracker stages — neither evaluated on this bench.
  - **The class-id numbering is per post-process plugin, not universal** — pick the right number for
    whichever `postprocess_so`/`postprocess_config` the surrounding `perception*.json` selects:
    - **Stock post-process** (`libyolo_hailortpp_post.so`, used by all three detector configs —
      `perception-yolov11s.json`, `perception-yolov11m.json`, `perception-yolov8m.json`): 1-based,
      with `0` reserved for `"unlabeled"` (`hailo_postprocess_tools/labels/*.hpp` — `yolo_personface`,
      `coco_eighty`, `coco_ninety` all start `{0, "unlabeled"}, {1, "person"}, ...`). `1` = person.
    - **Our `libyolo26_post.so` plugin** (`config/perception.json`'s default engine): 0-based COCO
      (`garuda::yolo26::COCO[80]`, `postprocess/yolo26_post.cpp`) — no `"unlabeled"` slot, so `0` =
      person. `classification_id` is not currently used with this plugin (`config/perception.json`
      runs `tracker.engine: "mono"`), but a future `hailo`-engine config built on yolo26m would need
      `0`, not `1`, for person.
- **The `hailo` block's fields** map straight to `HailoTracker::GetInstance().set_*()` calls
  (`kalman_distance`/`iou_threshold`/`init_iou_threshold`/`keep_tracked_frames`/`keep_new_frames`/`keep_lost_frames`)
  plus `min_hits`, which is `HailoTrackAdapter`'s own field (no SDK equivalent — a record is
  `confirmed` once its id has been seen `min_hits` times, exactly like mono's `track.min_hits`).
  Defaults are the SDK's own `DEFAULT_*` constants (`hailo_tracker.hpp`) for every field except
  `keep_lost_frames` (75, not the SDK's 5) and `min_hits` (1): 75 frames matches the mono engine's own
  `track.max_lost` (75, ≈2.5 s at the board's ~25-30 fps) — the coast window tuned and measured for
  this bench in §6's "ADDENDUM 2026-09-03 — coast window"; `min_hits=1` because the Kalman tracker's
  own association logic (not this adapter) is what filters spurious detections, and requiring a second
  hit here as well would just double-delay every real one.
- **`birth_conf`** (on-board fix round 7, Ruling 24; default: `track.high_thr`, i.e. `0.4` in the
  shipped configs) — the confidence a detection must reach **once**, live, before its id is published
  at all. The SDK's Kalman tracker births a track from *any* detection handed to it — it has no
  confidence floor of its own, unlike mono's ByteTrack, which only ever births at `track.high_thr` —
  so before this gate the node published (and the GUI drew) a box for every 0.17–0.19 junk detection
  in a cluttered room (field finding, 2026-09-04: `handbag` 0.19, `backpack` 0.19, `handbag` 0.17
  tracks in `/api/state`; the owner's "all over the place" — `bench/benchlog.md` F1, "Round 7"). The
  born flag is sticky for that id's `Entry`, so a later low-confidence or coasting frame of a born id
  still publishes, and it dies with the `Entry`: an id dropped after `keep_lost_frames` and later
  reused has to earn its birth again. The gate runs **before** the dedupe pass below, so an unborn
  record can neither be published nor suppress a born one. `0` disables it. Defaulting to
  `track.high_thr` is what makes the two engines admit the same detections; it is a parity choice, not
  a measured optimum.
- **`classes`** (on-board fix round 8, Ruling 25; default: `[]`, empty — every class) is a class
  allow-list applied inside `HailoTrackAdapter::update()`, independent of `classification_id` above.
  `classification_id` allows exactly **one** class id to reach the tracker at all — there is no way to
  hand it a set. A demo that must show more than one class (person + phone, say) therefore has to run
  `classification_id -1` (every class) and accept the SDK tracker's class-agnostic churn on every other
  object in view: a 120 s all-classes capture on real room objects emitted 15274 track entries over
  3063 rows — `chair` 3885, `handbag` 3137, `toilet` (a ring light) 2298, `laptop` 1905, `suitcase`
  1379, `person` 989 — and every one of those labels legitimately clears the round-7 birth gate at
  least once, so the GUI is cluttered whenever more than one class is tracked this way
  (`bench/benchlog.md` F1, "Round 8"). `classes` is the fix: a detection whose label is not in the list
  is dropped from `seen` before it can create or update an `Entry`, so it never contributes to that
  id's label majority, never sets `born`, and is never a dedupe candidate or comparator — filtering
  runs first, ahead of both the birth gate and the round-6 dedupe pass, so a disallowed high-conf box
  can neither be born itself nor suppress an allowed one. `config/perception-yolov11s-phone.json` is
  the first config to use it — see "phone-demo config" below.
- **Frozen coasting**: unlike ByteTrack's own `predict()` (which re-projects a coasting track's box
  forward each frame), `HailoTrackAdapter::update()` never touches a coasting entry's box — it stays
  exactly at its last-seen value until the id is seen again or dropped after `keep_lost_frames`. Verified
  on the board (fast poll, ~0.23 s apart, `/api/state`, id 15 "backpack"; box identical to the byte
  across every sample while `coasting: true`):

  ```
  16:27:48.674 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:48.905 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:49.136 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:49.367 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:49.596 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:49.827 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:50.059 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:50.291 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:50.519 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:50.749 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  16:27:50.980 (15, 'backpack', True, 883.03, 647.32, 92.6, 72.56)
  ```

  11 consecutive polls (~2.3 s) with a bit-for-bit identical `(x, y, w, h)` while `coasting: true` —
  the box only ever changes on the frame the id is re-seen (`coasting` flips back to `false`).

### Where the SDK tracker's parameters get applied, and why

`node_main.cpp` calls `HailoTracker::GetInstance().set_kalman_distance(...)` etc. right after
`pb.build("garuda-perception")` returns, **before** `pipeline->start()` — not deferred into
`det_sink`'s first frame. Read from the SDK's own source
(`hailo-postprocess-tools/1.12.0-r0/git/.../tracking/hailo_tracker.cpp`, under the SDK's
`usr/src/debug`, not the installed headers) before deciding this:

- Every `HailoTracker` setter reaches the singleton's `std::map<std::string, JDETracker> trackers`
  through `trackers[name]` — `std::map::operator[]`, which **default-constructs** a `JDETracker` under
  that key if it doesn't exist yet (never throws, never no-ops).
- `JDETracker`'s default constructor's default arguments (`jde_tracker.hpp`) are the exact same
  `DEFAULT_KALMAN_DISTANCE` / `DEFAULT_IOU_THRESHOLD` / `DEFAULT_INIT_IOU_THRESHOLD` /
  `DEFAULT_KEEP_FRAMES` constants this node falls back to above — so an auto-vivified entry (created by
  our setters running first) starts from the identical baseline a stage-registered one would.
- `TrackerStage::init()` registers its own tracker via `add_jde_tracker(name, params)`, which is a
  `std::map::emplace` — a no-op if the key already exists. So whichever runs first (our setters, via
  auto-vivify, or the stage's own `init()`), the six fields this node sets end up correct either way,
  and applying them before `start()` also means `init()`'s own params (built from a `HailoTrackerParams`
  member this file cannot inspect) can never be the one to overwrite ours.

Verified empirically on the board, not just from source: the log after every `hailo`-engine deploy
carries the line

```
tracker.engine=hailo kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=5 keep_new_frames=5 keep_lost_frames=75 min_hits=1
```

immediately after `starter begin` and before `garuda-perception running`, with **no error or
exception anywhere in the log** (checked with `awk`/`grep -ic 'error|exception|terminate|abort'` from
that run's `starter begin` line onward — result `0`), and every subsequent `/api/state` poll (below)
shows tracks with persistent, monotonically-assigned ids and plausible boxes — i.e. the six values
above are the ones actually governing the tracker's behaviour, not silently-ignored no-ops.

### Live verification (2026-09-03, no person at the bench — furniture-only scene)

Deploy the yolov8m + hailo config:

```
$ GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8m.json hosts/hailo15l/deploy.sh
...
garuda-perception: starting in background (log: /var/log/garuda-perception.log)
/var/run/garuda-perception.pid running (pid 10337)
/var/run/garuda-mono-shim.pid running (pid 10387)
deployed to root@10.0.0.1
```

Log tail — tracker stage in the pipeline (its own log line, the params line) plus a clean frame rate,
zero HailoRT/tracker errors:

```
Thu Sep  3 10:55:57 UTC 2026 starter begin (pid 10333)
tracker.engine=hailo kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=5 keep_new_frames=5 keep_lost_frames=75 min_hits=1
Thu Sep  3 10:55:59 UTC 2026 starter done: node 10337, shim 10387
garuda-perception running (feed 8971, cmd 8972)
garuda-mono-shim on :8098 (feed 127.0.0.1:8971, cmd 127.0.0.1:8972)
frames=275 fps=27.5
```

`/api/state` polled 10 times over roughly a minute (`16:26:28`–`16:27:22`) — ids persist across
polls (e.g. id 2 "suitcase" present at every single poll, same box within normal jitter; id 11
"backpack" seen live then coasting then dropped then re-minted as id 15, exactly the mono engine's
own re-acquire-mints-a-new-id behaviour under an IoU-only matcher):

```
16:26:28 tracks: ids [1..12], id 11 coasting=true (backpack)
16:26:34 tracks: ids [1..12,14], id 9/10/11 coasting=true
16:26:40 tracks: ids [1..12,14], id 7/11/14 coasting=true
16:26:46 tracks: ids [1..12,14], id 10/11/14 coasting=true
16:26:52 tracks: ids [1..12,14], id 14 coasting=true
16:26:58 tracks: ids [1..12,14], id 10/11/14 coasting=true
16:27:04 tracks: ids [1..12,14], id 10/11/12/14 coasting=true
16:27:10 tracks: ids [1,2,3,4,5,6,7,8,9,10,12,14,15], id 10/14 coasting=true (11 dropped, 15 new)
16:27:16 tracks: ids [1,2,3,4,5,6,7,8,9,10,12,14,15], id 9/10/14 coasting=true
16:27:22 tracks: ids [1,2,3,4,5,6,7,8,9,10,12,14,15], id 14 coasting=true
```

(Raw JSON for all 10 polls captured during this session; ids/labels/coasting flags summarised above
for readability — every poll returns full `x/y/w/h/conf` per track, unchanged in shape from the mono
path's own `/api/state` schema.) `lock.id` stayed `null` throughout — `default_class` is `"person"`
and no person was in frame this run (bench had only suitcases/handbags/a chair/a tv/a backpack in
view), so the lock never acquired; this is the resolver behaving identically to the mono engine under
the same "no matching class present" condition, not a hailo-engine-specific gap.

### Mono path still works (unchanged output)

Rolled back to the default config (`hosts/hailo15l/deploy.sh`, no env var → `perception.json`,
`tracker.engine: "mono"`, yolo26m detector) to confirm the feature didn't regress the pre-existing
path:

```
$ hosts/hailo15l/deploy.sh
...
deployed to root@10.0.0.1
```

Log tail — no `tracker.engine=...` line (expected: that line only ever prints for the hailo engine),
clean start:

```
Thu Sep  3 10:58:22 UTC 2026 starter begin (pid 10625)
Thu Sep  3 10:58:24 UTC 2026 starter done: node 10629, shim 10679
yolo26_post: conf=0.150 iou=0.50 net=640x640 frame=1280x720 mode=letterbox prefix=yolo26m/ dump=/0
garuda-perception running (feed 8971, cmd 8972)
```

`/api/state`:

```json
{"lock":{"class":"person","coasting":false,"id":null},"tracks":[
  {"id":1,"label":"suitcase","conf":0.789,...},
  {"id":2,"label":"suitcase","conf":0.631,...},
  {"id":3,"label":"suitcase","conf":0.510,...},
  {"id":4,"label":"chair","conf":0.690,...}
]}
```

Same schema, same field names, same behaviour as every prior mono-engine capture in this file (§6,
§8) — the `tracker` config block and the `det_sink` engine branch add nothing observable to the mono
path's own output.

### Rollback

Redeployed the yolov8m + hailo config afterward (`GARUDA_PERCEPTION_CONFIG=...perception-yolov8m.json
hosts/hailo15l/deploy.sh`) and confirmed the tracker-params log line and a clean `/api/state` poll one
more time — **board left on this state**: yolov8m detector, `tracker.engine: "hailo"`, healthy. To go
back to mono on either detector config, just deploy a `perception*.json` whose `tracker.engine` is
`"mono"` (or omit the `tracker` block entirely — the field is optional).

### Live verification — `classification_id: 1` (person-only), 2026-09-03

Follow-up field finding (same day, corrected 2026-09-04 — see §9's corrected bullet above): with
`classification_id: -1` every detection in a frame, of any label, competed in the tracker's single
class-agnostic one-to-one LAPJV assignment, so a real person's track could fragment into a new id
whenever a competing class's box won that assignment for a single frame — a different bug from the
one `18af174`'s majority-vote label fix addresses (that fix stops the *label* from flickering on a
surviving id; this is the tracker's own assignment losing the id to a competing box entirely). Set
`config/perception-yolov8m.json`'s `tracker.hailo.classification_id` to `1` (person, in the stock
post-process's 1-based labelmap — see the bullet above) and redeployed.

Log line (the applied params, `classification_id` now included) plus the warn-once path actually
firing for the first time — non-person detections (chair/suitcase/tv/etc., all still produced by the
stock detector) reach `det_sink` with no tracking id and are dropped, exactly as designed:

```
tracker.engine=hailo classification_id=1 kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=5 keep_new_frames=5 keep_lost_frames=75 min_hits=1
hailo tracker: 6 detection(s) with no tracking id this frame, dropped
```

(2026-09-04, M2 fix: this warn-once line is captured here as it behaved on 2026-09-03, before the
fix. Under a single tracked class, missing ids on every OTHER class's detections are expected, not a
fault, so the line no longer prints when `classification_id != -1` — `missing_id` is still counted,
just silently. It fires only when `classification_id == -1`, where a missing id is genuinely
unexpected. See `node_main.cpp`'s `det_sink` callback and this fix round's report.)

`/api/state` polled 10 times over ~45 s (`17:34:21`–`17:35:06`, owner in view) — every single poll
returns **exactly one track**, the person, with a stable id and a moving box (real live tracking, not
a stuck/frozen snapshot); `lock.id` stays `1` and `lock.coasting` stays `false` throughout:

```
17:34:21 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.877,...}]
17:34:26 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.881,...}]
17:34:31 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.873,...}]
17:34:36 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.892,...}]
17:34:41 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.896,...}]
17:34:46 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.896,...}]
17:34:51 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.908,...}]
17:34:56 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.904,...}]
17:35:01 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.900,...}]
17:35:06 lock={class:person,id:1,coasting:false} tracks=[{id:1,label:person,conf:0.904,...}]
```

(Raw JSON per poll is in this session's transcript; summarised here for readability — every field the
mono/hailo paths always publish, `x`/`y`/`w`/`h` included, is present in every raw poll, and the box
moves frame to frame, confirming it's a live person track, not a stuck coasting one.)

**Non-person detections do NOT appear in `tracks[]`** — verbatim, across all 10 polls above, `tracks`
never contains more than the one `"person"` entry; the furniture/objects that populated 10-13
simultaneous tracks in §9's earlier `classification_id: -1` capture (suitcases, handbags, a chair, a
tv, a backpack) are completely absent now — they are still detected (the `dropped` log line above
proves the detector still emits them) but never become tracks once `classification_id` restricts the
SDK tracker to person only.

Board left on this state: yolov8m detector, `tracker.engine: "hailo"`, `classification_id: 1`,
healthy, actively tracking a person.

### 2026-09-04 fix — stale frames were published as fresh (`keep_tracked_frames`)

Whole-branch review finding (`.superpowers/sdd/2026-09-03-hailo15l-kalman-tracker/final-fix-brief.md`,
I1), mechanism read from the SDK source: `jde_tracker_update.hpp:130-143` re-adds an unmatched
Tracked strack to the ACTIVATED list (not Lost) as long as `frame_id - end_frame() <
keep_tracked_frames`; Step 7 of the same file (`:302-313`) emits every activated strack; `strack.hpp`'s
`multi_predict` (`:327-337`) never writes a re-projected box back onto the strack it predicts for. Net
effect: for up to `keep_tracked_frames` frames after a real miss, the stage re-emits the track's LAST
MATCHED box as if it were a fresh detection that frame — `HailoTrackAdapter` sees what looks like an
ordinary sighting (`tsu` resets to `0`) and the snapshot reports `coasting: false`, even though the
box is stale and the object may no longer be there at all.

Fix: `config/perception-yolov8m.json`'s `tracker.hailo.keep_tracked_frames` is now `0` (was `5`) — an
unmatched strack drops straight to Lost on the very next miss, instead of being re-activated silently
for up to 5 frames first. Re-association across a real gap still works exactly as before: a Lost
strack stays in the tracker's own `strack_pool` for `keep_lost_frames` (`75` here, unchanged,
`jde_tracker_update.hpp:222-224`), so a track that returns within that window keeps its id. Only the
"re-emit the last box as if it were fresh" window is removed — `HailoTrackAdapter`'s `coasting` flag
(`time_since_update > 0`) now goes true on the very next frame after a miss, because the stage no
longer hides that frame's miss behind a re-activated, unmatched strack.

Deploy + board verification: **PENDING — board unreachable.** Link lost 2026-09-03 09:17:52 per the
owner; checked again in this fix round at 2026-09-04 09:55 IST with two `ping -c 2 -W 2 10.0.0.1`
retries, both 100% packet loss. The config change is committed and cross-built clean (zero
`warning:` lines, `services/garuda-perception/build-h15l`); deploying it and capturing a ≥60 s
timestamped SSE run through an out-of-frame gap — to confirm `coasting` flips to `true` on the first
snapshot after the last detection, within one frame interval plus the SSE capture's 100 ms cap — is
owed once the board answers again.

### 2026-09-04 minors

- **Unknown `tracker.engine` refuses to start.** `node_main.cpp` now checks `tracker.engine` against
  `{"mono", "hailo"}` right after reading it and exits with `return 1` plus a
  `tracker.engine: unknown value "..." ... refusing to start` line on `stderr` for anything else —
  previously an unrecognised value (a typo, e.g. `"Hailo"`) silently fell back to `"mono"` with no
  diagnostic anywhere in the log.
- **Missing-id warn-once now respects `classification_id`.** Under a single tracked class
  (`classification_id != -1`), every other class's detections are *expected* to arrive at `det_sink`
  with no tracking id (`block_non_tracked_classification_id(false)`) — that used to still print the
  `hailo tracker: N detection(s) with no tracking id this frame, dropped` warn-once line (see the
  captured example above, from before this fix). It now only fires when `classification_id == -1`
  (every class tracked), where a missing id is genuinely unexpected; the count is still taken either
  way, just silently under a single class.
- **Startup now logs `keep_lost_frames` vs `max_lost`, and warns if they differ.** These are two
  independent config knobs (mono's `track.max_lost`, the hailo engine's own
  `tracker.hailo.keep_lost_frames`) that are designed to match so switching engines doesn't silently
  change the coast window (see the "hailo" block fields note above) — `node_main.cpp` now prints
  `tracker: keep_lost_frames=<N> max_lost=<M>` at startup and a `stderr` warning if they've drifted
  apart.

### SSE rate: `SSE_MAX_HZ` 10 → 30 (2026-09-04, on-board fix round 5)

`shim/garuda_mono_shim.py`'s `SSE_MAX_HZ` is now **30.0** (was 10.0). Every PC-side capture the F1
work is judged on comes through that cap, and at 10 Hz a capture samples roughly every third frame of
a ~25–30 fps pipeline: a state that flickers within 100 ms is invisible, and the two earlier replay
fixtures are correspondingly coarser than the pipeline they came from (`lock_replay_common.hpp` says
so at the top). Run 10e was taken at 30 Hz and lands ~29 rows/s — near enough to per-frame that a
replay is now roughly as strong a gate as the live run instead of weaker.

`MJPEG_MAX_FPS` is unchanged at 15.0 — the display path, not the measurement path.

**Cost, measured on the board.** `top -bn1` sample taken **2026-09-04 13:02:35 board time**, with
`jpeg_fps 30` and SSE 30 Hz and **one** SSE client connected:

```
garuda-perception 100.0 %CPU (one core)
isp_media_server   29.4 %CPU
%Cpu(s):  33.3 us,  8.7 sy, 56.5 id
load average 2.13
thermal_zone0 83197 m°C
```

**There is no before-sample at 10 Hz / 15 fps to compare against** (rule 1 — it was never taken, and
none is invented here), so this sample says nothing about how much of that core the rate change
itself costs. What it does say is that **the node saturates one of the four A53s** under this
configuration, which is an **open item: profile it** (detector, post-process, JPEG encode and SSE fan-
out are all in that number and none has been attributed). 83 °C is hot but the board has no measured
throttle point recorded here either way.

The **committed configs keep their own `jpeg_fps`** — run 10e used a *scratch* copy with `jpeg_fps 30`
and `classification_id -1` (all COCO classes), stated in the benchlog's conditions for that run. Only
the shim constant is committed.

### On-board fix round 6 — duplicate same-class tracks (`dedupe_containment` / `dedupe_iou`)

Field finding, owner present, seen live: on one person, ids alternated (38/39) with boxes ~819 px and
~655 px wide (run 8's own capture,
`bench/evidence/2026-09-04-lock-core/run8_routine4_lateral.txt.gz`, rel. ~110 s — id 38's box
(193,124,819,595) and id 39's box (195,125,655,594) at the exact same instant, the smaller wholly
inside the larger) — the same `id churn 41` already logged for run 8 above. Mechanism: the yolo26m
HEF's baked NMS does not suppress a box mostly contained inside another box of the same class, so a
single person can produce two simultaneous `person` detections (a full-body box and a torso box); the
SDK tracker's one-to-one LAPJV assignment (§9's `classification_id` note) has no notion of "these two
boxes are the same object" and births a second track. `keep_lost_frames 75` then keeps BOTH ids alive
for up to 2.5 s, and whichever box a given frame's single real detection resembles wins that frame's
assignment for that id — so the id the node reports for that person alternates, and the F1 harness
counts it as `id churn`.

Fix: `HailoTrackAdapter::update()` (`include/garuda/hailo_track_adapter.hpp`,
`src/hailo_track_adapter.cpp`) now dedupes its own output before returning it, restricted to LIVE
records (`time_since_update == 0`) of the SAME class — coasting records are never a comparator and
never dropped, since a frozen last-seen box that happens to now overlap a live box is stale geometry,
not a duplicate detection. Two new `tracker.hailo` config fields, checked in that order:

- **`dedupe_containment`** (default `0.8`) — if the smaller live box's own area is at least this
  fraction covered by the larger live box, the smaller record is dropped (the full-body/torso case
  above: the torso box is essentially 100 % inside the full-body box).
- **`dedupe_iou`** (default `0.6`) — else, if the pair's IoU is at least this fraction (neither box is
  "mostly inside" the other, but they overlap heavily), the LOWER-CONFIDENCE record is dropped.

A dropped record is simply not emitted to `LockResolver`/the snapshot's `tracks[]` this frame — its
Entry inside the adapter is untouched, so the same id can still win a later frame if the duplicate
detection doesn't recur. Processing order is deterministic (larger-area box first; a record dropped
once is never reconsidered), so which of two same-size, tied-confidence boxes survives does not depend
on detection order. Either field set to `0` disables that rule. All three committed configs that run
the `hailo` engine (`perception-yolov11s.json`, `perception-yolov11m.json`, `perception-yolov8m.json`)
set both to their code defaults, `0.8`/`0.6`; `config/perception.json` and
`config/perception-yolov8n.json` run the `mono` engine and carry no `tracker.hailo` block at all, so
nothing to add there.

**Accepted cost:** if the full-body and torso boxes alternate which one the detector emits from frame
to frame, the id assigned by the SDK tracker (and therefore the id this dedupe pass forwards) can
itself alternate once before settling — `dedupe_containment`/`dedupe_iou` only ever remove a
same-frame duplicate, they cannot prevent the underlying tracker from having birthed two ids for one
person in the first place. The existing `lock.size_ratio_max 1.6` gate (Ruling 22) is what keeps
`LockCore` from treating that occasional id hand-off as a genuine relock, the same way it already
covers the 819/655 px pair measured above.

Startup logs both values on the existing `tracker.engine=hailo ...` line
(`dedupe_containment=%.2f dedupe_iou=%.2f`, appended after `min_hits`). Deployed and confirmed live
on the board (2026-09-04, `/var/log/garuda-perception.log`):

```
tracker.engine=hailo classification_id=1 kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=0 keep_new_frames=5 keep_lost_frames=75 min_hits=1 dedupe_containment=0.80 dedupe_iou=0.60
```

**A fresh capture confirming `id churn` no longer reproduces on the same full-body/torso duplicate
that run 8 caught (rel. ~110 s, ids 38/39) is TBD-bench** — see `bench/benchlog.md`'s F1 section,
"Round 6 — duplicate same-class tracks".

### Phone-demo config (on-board fix round 8, Ruling 25)

`config/perception-yolov11s-phone.json` is for demoing a phone-follow use case without the
all-classes clutter described in the `classes` bullet above: it is `perception-yolov11s.json` with
`classification_id -1` (every class reaches the tracker, since `classification_id` cannot itself
restrict to two classes), `tracker.hailo.classes ["person", "cell phone"]` (the allow-list that
throws away everything else — chairs, handbags, the ring light, etc.), and `jpeg_fps 30` (the higher
rate a hand-held-phone demo benefits from; `perception-yolov11s.json` stays at `15`). Deploy it the
same way as any other detector config:

```bash
env GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov11s-phone.json \
    hosts/hailo15l/deploy.sh
```

`track.default_class` is untouched (`"person"`), so `LockResolver`'s existing auto-acquire gate
(§9's engine-neutral behaviour, unchanged by this config) still auto-acquires a person the moment one
clears its streak/confidence gate — a phone never auto-acquires, since it is not the default class.
The only way to lock a phone with this config is a click on it (`lock_point`/`target "cell phone"`);
once locked, coast/re-acquire behave exactly as for any other locked target. Rollback to
`perception-yolov11s.json` (or any other detector config) is the same one-command swap as §4.

### `dedupe_protect_age` (on-board fix round 9, Ruling 27)

`tracker.hailo.dedupe_protect_age` (default `10`, in frames) bounds the duplicate suppression above.
The containment/IoU rules cannot distinguish *one person detected twice* (a full-body box and a torso
box, which is what round 6 exists to collapse) from *one person standing behind another*, and in the
second case they silently deleted the farther person — possibly the locked target (outside review,
2026-09-05). A record may now be suppressed only if it is **neither** the protected id **nor** older
than `dedupe_protect_age` frames since its first emission. The protected id is set by the node every
frame to the resolver's current lock id (`HailoTrackAdapter::set_protected_id`, or `-1` for nothing
locked), so the locked track is exempt at any age. A duplicate *birth* is young by construction and
is still suppressed; `0` disables the age half and restores the pre-round-9 behaviour for everything
except the protected id.

### The core's input vs the published list (on-board fix round 9, Ruling 26)

`HailoTrackAdapter` now returns two things per frame. `update()` is the **published** list — class
allow-list, then birth gate, then dedupe — and it drives `tracks[]` in the snapshot, `LockResolver`'s
`step()`, and both paths that can create a NEW lock (an operator click, and the resolver's class
auto-acquire). `live_raw()` is this frame's **live records after the class allow-list only**, and it
is what `LockCore::update()` receives. The birth gate and the dedupe are display gates: they decide
what is drawn and what may be picked as a new target, not what an existing lock may keep tracking —
a locked phone dropping to conf 0.3 for a second is exactly when the core needs the measurement most.
Net effect: **a new lock always needs a track the operator can see; maintaining or recovering one may
use any live detection.** The mono (ByteTrack) engine is unaffected — there the two lists are the same.

### `diag`: per-frame stage counters (on-board fix round 9)

Every snapshot now carries a `diag` object so a capture alone answers "where did the boxes go":

| field | meaning |
|---|---|
| `raw_dets` | detections the post-process handed the tracker this frame |
| `sdk_tracks` | detections arriving with an SDK tracking id |
| `live_raw` | live records after the class allow-list only (`live_raw()` above) |
| `published` | tracks in this snapshot's `tracks[]` |
| `core_candidates` | observations handed to `LockCore::update()` |

`-1` means *this engine cannot see that stage* — never a substituted zero. **`raw_dets` is always
`-1` under the hailo engine**: the SDK's `TrackerStage` sits between `post` and our `det_sink` and
rewrites the ROI, so the pre-tracker detection list never reaches the node and cannot be counted
there. It is a real count on the mono path, where `post` feeds `det_sink` directly.
`bench/evidence/2026-09-04-lock-core/lock_metrics.py` prints a one-line means summary of these when
a capture carries them (a counter that is `-1` on every row reports `n/a` rather than being averaged).

### The board-truth view: `http://<board>:8098/` (on-board fix round 9, Ruling 31)

The shim's index page is the **only** place that shows what the board's own lock core publishes: an
overlay canvas on the MJPEG stream drawing every published track (thin, dashed while coasting, with
`label id conf`) and `LockCore`'s own `lock.box` thick and coloured by state — green CONFIRMED, amber
+ `FROZEN` for OCCLUDED/REACQUIRING, and *nothing at all* for LOST/NONE, which is the contract, not
an omission — plus a status line
`state · class · id · epoch · q · age · control_valid` and the `diag` counters. Clicking the image
posts `/api/mono_click` at frame coordinates; there are person / clear-target buttons; redraw is
driven by the SSE stream at 30 Hz, and the page loads no external resource so it works over an SSH
tunnel. **The PC portal on `:8080` currently re-tracks the board's `tracks[]` with its own ByteTrack
and keeps its own target, so it must not be used to judge the lock** — what it shows is its own
tracker's opinion, not the board's. Fixing that belongs to the portal branch; until the portal
consumes the board's `lock` object, use `:8098`.

## 10. Lock core (F1 — time-based locked-target tracker)

Before this feature, "the lock" was just whichever multi-object-tracker id `LockResolver` (§6/§9) was
currently pointing at — its coast/re-acquire windows were **frame counts** (`track.max_lost`,
`track.reacq`), which drift with frame rate, and a click/re-acquire could hand the lock to a
completely different-looking box the instant the tracker's own id churned (a known failure mode, see
the classification_id note above). `LockCore` (`include/garuda/lock_core.hpp` /
`src/lock_core.cpp`, `garuda::lock::{State, Obs, Params, Box, Output, LockCore}`) replaces that:
a dedicated, engine-neutral, **time-based** (milliseconds off the frame's ISP clock, not frame counts)
tracker of one locked identity, with its own small Kalman filter (constant-velocity position,
random-walk size) so it can keep publishing a sensible box through a short gap and reject an
implausible "reacquisition" the way a frame-count window never could. It sits downstream of both
tracker engines and `LockResolver` in `det_sink` — see "Node integration" below.

### States

```
NONE → (lock) → CONFIRMED ⇄ OCCLUDED ⇄ REACQUIRING → LOST
                    ↑______________________|
        (a winning candidate returns from either state)
```

| State | Meaning | `identity_locked` | `observation_valid` | `lock.box` (published) |
|---|---|---|---|---|
| `none` | Never locked, or explicitly `unlock()`d | false | false | `null` |
| `confirmed` | A live detection won this frame's gate/score test | true | true | the filtered box |
| `occluded` | No winning detection yet, `obs_age_ms <= occlusion_ms` | true | false | frozen — the last confirmed box, bit-exact |
| `reacquiring` | Still no winner, `occlusion_ms < obs_age_ms <= expire_ms` | true | false | frozen — same as `occluded` |
| `lost` | `obs_age_ms > expire_ms` — terminal; only an explicit `lock()` (never an automatic reacquisition) exits it | false | false | `null` |

The bench harness's **off-screen published boxes** column counts rows whose `lock.box` **centre**
(`x + w/2`, `y + h/2`) is outside the frame — not rows whose box merely overhangs an edge, which is
normal and legitimate for a target at the edge of frame (run 1 produced 109 such rows for a person who
had genuinely walked out to the right; under the centre rule the same capture reads 0).

The "published box" column is `lock.box` in the snapshot (see below) — `LockCore`'s own box, and the
only box in the snapshot that follows this table. The `tracks[]` entry that happens to share
`lock.id` is a *different* box: the multi-object tracker engine's, which under the mono engine is
ByteTrack's **extrapolated** coasting box (`src/bytetrack.cpp`, `bbox += vel`) and under the hailo
engine the adapter's frozen last box. So "the prediction never reaches the screen" is a statement
about `lock.box`, not about everything a viewer might draw.

`obs_age_ms` is wall-clock milliseconds since the last winning correction (0 while `confirmed`);
`uncertainty_px` is `sqrt(max(var_cx, var_cy))` off the position filter's own (uncapped) covariance —
it grows through `occluded`/`reacquiring` and is a genuine "how far could the target actually be by
now" diagnostic, not clamped to whatever gate radius is currently in effect. `quality` is the winning
candidate's score while `confirmed` (0–~1); otherwise `max(0, 1 - obs_age_ms/expire_ms) * 0.5` — it
can never read above 0.5 without a real observation backing it.

### Config: the `lock` block

Every `config/perception*.json` carries a `lock` block (all fields optional — a config that omits the
whole block, or any field in it, gets `include/garuda/lock_core.hpp`'s own default for that field).
All six currently hold the header's defaults verbatim:

```json
"lock": {
  "occlusion_ms": 500, "reacquire_ms": 9500, "expire_ms": 10000, "control_valid_ms": 150,
  "gate_sigma": 3.0, "min_score": 0.5, "min_score_widened": 0.40,
  "widened_new_id": true, "widened_new_id_min_conf": 0.5, "widened_new_id_max_age_ms": 7000,
  "ambiguity_ratio": 1.3,
  "size_tol": 0.5, "gate_max_px": 300,
  "q_acc_std": 600, "p0_vel_std": 400, "r_pos": 25, "q_size": 50, "r_size": 100,
  "r_pos_frac": 0.10, "gate_min_frac": 0.15, "r_size_frac": 0.15, "q_size_frac": 0.5,
  "same_id_gate_mult": 2.0, "size_ratio_max": 1.6,
  "w_conf": 0.25, "w_motion": 0.35, "w_size": 0.15, "w_class": 0.15, "w_id": 0.10,
  "auto_min_conf": 0.5, "auto_edge_margin_frac": 0.02, "auto_min_streak": 5,
  "auto_streak_window": 15
}
```

**`include/garuda/lock_core.hpp`'s `Params` defaults are the source of truth for these numbers; the
JSON block above and the six shipped configs mirror them, and the two must be changed together.**
Nothing enforces that (the config only ever *overrides*), so a header default changed on its own will
silently diverge from what is deployed — the configs are what the board actually runs.

- **Windows (ms):** `occlusion_ms` (confirmed→occluded boundary), `reacquire_ms` (length of the
  widened, out-of-gate search once `occlusion_ms` has passed — the widened search runs while
  `obs_age_ms` is in `occlusion_ms .. occlusion_ms + reacquire_ms`, while the reacquiring→lost
  boundary itself is `expire_ms` measured from the same `obs_age_ms` origin — see the state table),
  `expire_ms` (reacquiring→lost boundary; terminal). **`reacquire_ms` is 9500 since on-board fix
  round 4 (Ruling 20c)**, so `occlusion_ms + reacquire_ms == expire_ms` and the two boundaries
  coincide: the widened search now stays open for the whole reacquiring band. Under the previous 3000
  there was a 6.5 s dead band in which the lock was still alive but only in-gate candidates were
  considered — run 7's owner re-emerged from a 6-second hide inside it and the lock expired with her
  in plain view (`bench/benchlog.md`, "Run 7"). They remain independent parameters; a config may still
  close the window early.
- **`control_valid_ms`** is consumed **since on-board fix round 9 (Ruling 30)** — by the snapshot, not
  by `LockCore` itself. The node publishes `lock.control_valid` =
  `observation_valid && (obs_age_ms + age_ms) <= control_valid_ms`, where `age_ms` is that snapshot's
  own capture-to-publish age, so both halves of the staleness a consumer really experiences are
  counted: how long ago the core last saw the target, and how long ago the frame it saw it in was
  captured. It answers "is the currently published box fresh enough to *steer a vehicle on right
  now*", which is a stricter question than "is it fresh enough to keep *displaying*" — 150 ms against
  `occlusion_ms`'s 500 ms display window. **A follow controller must gate on `control_valid`, never on
  `observation_valid` alone**, and fall back to a safer behaviour (hold last heading, hover, degrade
  to open-loop) when it is false, even though the lock stays visually `occluded`/`reacquiring` with a
  frozen box for much longer. `observation_valid` keeps its own meaning exactly — the core associated
  something on its last update — and makes no statement about age.
- **`widened_new_id`** / **`widened_new_id_min_conf`** / **`widened_new_id_max_age_ms`** (on-board
  fix round 10, Ruling 32; defaults `true` / `0.5` / `7000` — the ceiling was 5000 as first ruled and
  moved to 7000 by round 10b, Ruling 33, see below). These govern whether the widened
  (out-of-gate, full-frame) stage may take a candidate carrying a **different** tracker id. Out of
  gate the motion term is ~0, so the score reduces to confidence + size + class — none of which is
  *identity* evidence — and the ambiguity margin cannot help when there is exactly one wrong
  candidate (the outside review's probe: a lone new-id person 900 px away at conf 0.41 took the lock).
  Round 9 (Ruling 28) refused all of them outright and cost two committed captures their recovery;
  round 10 asks instead for the evidence that exists without an appearance model. A different-id
  candidate is accepted only when **all** of these hold:
  1. it is the **same class** as the lock (unchanged from earlier rounds);
  2. its tracker id was **born after the last confirmed observation** — `Obs::first_seen_ms >` the
     last confirmation, with `-1` ("the engine cannot tell us") treated as pre-existing and refused.
     **This is the load-bearing one**: an id that was already alive while the target was confirmed is,
     by construction, a *different physical object* (the tracker was holding both at once), so the
     classic swap — the other person who was in the room the whole time — is impossible, with no
     appearance model at all;
  3. it is the **only** eligible out-of-gate candidate this frame (the ambiguity margin still governs
     the in-gate pool; out of gate the bar is exclusivity, because the danger is one plausible
     stranger rather than two similar ones);
  4. `conf >= widened_new_id_min_conf`;
  5. `obs_age_ms <= widened_new_id_max_age_ms` — note this closes the different-id half of the widened
     window **earlier than `reacquire_ms` does**: beyond it only tracker-id continuity recovers a lock.

  A **same-id** out-of-gate candidate is exempt from 2–5: it carries the multi-object tracker's own
  assertion that it followed the same object across the frame. `widened_new_id` is the master switch;
  `false` restores round 9's blanket refusal and is kept as the "strict" reference the replay tests
  still pin, not as a recommendation.

  **The accepted residual, stated rather than buried:** a same-class object that genuinely appears for
  the first time after the target is lost, alone in frame, at good confidence, inside the age ceiling,
  *is* taken. Telling it from the real target needs appearance (F3, not built). What condition 2 buys
  is that the object which was there all along can never be it.

  **`widened_new_id_max_age_ms` is the one number to look at first if re-acquisition seems weak, and
  it is why round 10b exists.** On the committed phone capture, 24 of the 26 different-id
  re-acquisitions land at `obs_age <= 3969 ms` but one lands at **6392 ms**, so the originally-ruled
  5000 ms missed it — which in the replay harness (no `LockResolver`, so LOST is terminal) collapsed
  that capture from 0.8150 to 0.1945. The ceiling sweep is a step, not a gradient: 2000/3000/5000/6000
  all give 0.1945; 7000/8000/9000/9500/10000 all give 0.8150. **Round 10b (Ruling 33) therefore ships
  7000** — above what the capture asks for, and still 3 s inside the unchanged 10 s `expire_ms`, so
  the different-id window closes well before the lock itself dies. Note the harness is *harsher* than
  the board: on the node a miss here costs an extra **visible** re-lock (a new epoch via class
  auto-acquire), not a target that is never seen again. Full sweep and reasoning:
  `bench/benchlog.md`, "Round 10 — Ruling 32".

  `first_seen_ms` is supplied by the hailo adapter (stamped on the frame an id is first seen, at any
  confidence, after the class allow-list) and by a node-side map on the mono path —
  `bytetrack.{hpp,cpp}` is a line-for-line port pinned by `tests/golden/bytetrack_ref.py` and is
  deliberately not given a field for this.

- **Stall expiry** (on-board fix round 9, Ruling 29) — `expire_ms` is elapsed wall-clock time since
  the last confirmation, **not** a count of `update()` calls. If `obs_age_ms` exceeds it, the frame
  associates nothing and the lock goes `lost` before association is attempted, so a pipeline that
  stopped calling `update()` (a stalled camera, a blocked sink) comes back to a dead lock rather than
  to one that treats the first frame back as though no time had passed. The ticked path is unchanged.
- **Gating/scoring:** `gate_sigma` (in-gate test is `d² <= gate_sigma²` against the **innovation**
  covariance `S = min(P, gate_max_px²/gate_sigma²) + R`, see the box-relative block below),
  `min_score`/`ambiguity_ratio` (a candidate wins only if its score clears
  `min_score` and beats the runner-up **in its own stage's pool** by at least this ratio — see
  "Association is two-stage" below and `lock_core.hpp`'s scoring formula), `min_score_widened` (the
  widened stage's own floor; **0.40 since on-board fix round 3**, an explicit default rather than the
  earlier "same as `min_score`" — an explicit JSON `null` restores that behaviour), `size_tol`
  (fractional w/h tolerance floor), `gate_max_px`
  (caps the *state* term of the gating variance at
  `(gate_max_px/gate_sigma)²` regardless of how long an uncorrected coast has grown the raw variance —
  see the `Params`/`gate_max_px` comment in `lock_core.hpp` for the full "why", and never affects
  `uncertainty_px`, the Kalman correction gain, or the filter's own state, only which candidates are
  considered in/out of gate. Since round 3 the measurement noise `R` is added *after* this cap, so a
  large box's gate legitimately exceeds `gate_max_px`).
- **Box-relative gates (`r_pos_frac`, `gate_min_frac`, `r_size_frac`, `q_size_frac`,
  `same_id_gate_mult`)** — on-board fix round 3 (Ruling 19, `bench/benchlog.md` "Run 5"). Every
  tolerance the core applies now scales with the target's own box, with the absolute constants above
  kept as floors, because a 650 px person box and a 60 px phone box do not jitter or grow by the same
  number of pixels:
  - `r_pos_frac` (0.10) — per-axis **position measurement std** is `max(sqrt(r_pos), r_pos_frac·ref)`:
    `ref` is the width reference for x, the height reference for y. Note `r_pos` is a variance (px²)
    and this is a std, hence the square root. Used for both gating and the Kalman correction.
  - `gate_min_frac` (0.15) — floor on the **gate radius**, `gate_min_frac · max(w_ref, h_ref)` px,
    applied after `R`. A converged lock on a 655 px person can never gate tighter than ~98 px.
  - `r_size_frac` (0.15) — **size measurement variance** is `max(r_size, (r_size_frac·ref)²)`.
  - `q_size_frac` (0.5 per second) — the size random walk grows by `max(q_size, (q_size_frac·ref)²)`
    px² per second: a relative random walk, "this box may plausibly change by ~half its own size in a
    second". `q_size` stays parsed and honoured as an absolute floor.
  - `same_id_gate_mult` (2.0) — **the same-id rule.** A candidate whose tracker id equals the core's
    current `lock.id` has *both* its position gate radius and its size tolerance multiplied by this,
    and its motion and size score terms are computed against those relaxed scales (so its score
    reflects the relaxation, it is not merely admitted). Rationale: the node only ever passes the core
    **live** records (`node_main.cpp`'s `live_obs`, `time_since_update == 0`), so an id match is
    frame-to-frame continuity the multi-object tracker has already established and verified — the core
    must not override it with a size/position reference that may be stale. It is a relaxation, never a
    bypass: class matching, the score floor and the ambiguity margin all still apply, and a same-id
    candidate whose deviation exceeds the *doubled* tolerance is still rejected (`test_lock_core.cpp`
    case 19(c) pins both sides of that).
  - `size_ratio_max` (1.6) — **the hard size-ratio cap**, on-board fix round 5 (Ruling 22.2). A
    candidate whose id is **not** the core's own `lock.id` is eligible only if `w / ref_w` *and*
    `h / ref_h` both lie in `[1/1.6, 1.6]` — applied **on top of**, never instead of, the
    variance-aware tolerance above. Same-id candidates are exempt, because run 5's owner tripling her
    box size walking toward the camera was same-id and the relative model exists to follow exactly
    that. The reason a hard cap is needed alongside a variance-aware one: the variance-aware
    tolerance *grows with `obs_age`* by design, and after a few seconds of `reacquiring` that growth
    was enough to call a 229×270 static box "size-consistent" with a 135×285 phone reference (run
    10e). 1.6 is derived from the geometry a fast approach or retreat needs within the ~10 s a lock
    lives — not a bench measurement. A non-positive value disables the cap.
- **Auto-acquire gate (`auto_min_conf`, `auto_edge_margin_frac`, `auto_min_streak`,
  `auto_streak_window`)** — these four are consumed by `LockResolver`, not by `LockCore` (they live in
  this block because it is the one place the lock's defaults are written down). The resolver may pick
  up a target *on its own* only if all three tests hold:
  1. **confidence** at least `auto_min_conf` (0.5);
  2. **edges** — the box clear of the **left and right** frame edges by `auto_edge_margin_frac *
     frame_w` (0.02 × 1280 = 25.6 px). Top and bottom are deliberately not gated: a person close to the
     camera legitimately spans the full frame height;
  3. **streak** — 1 and 2 satisfied on `auto_min_streak` (5) **live frames within the last
     `auto_streak_window` (15) frames** in which that id appeared — ~0.5 s at 30 fps. Only live frames
     ever count, so a streak requirement of 1 or more still makes auto-acquire live-only; a coasting
     frame is not a reset, it simply contributes nothing. Either field at `0` disables the streak test
     outright.

  Round 2 required the five frames to be **consecutive**; on-board fix round 7 (Ruling 24) made it a
  sliding window, because five consecutive gate-passing frames are unreachable for an intermittently
  detected target — the phone in the round-7 capture was a live box in only 30.2 % of frames, so after
  the clicked lock expired auto-acquire never re-locked it (`lost` for 68 % of rows,
  `bench/benchlog.md` F1, "Round 7 — clutter and re-acquire"). 5 of 15 still refuses run 2's flicker
  below: one gate-passing frame ages out of the window with nothing to join it.

  The **re-acquire jump** — a coasting lock moving to the best live same-class track after `track.reacq`
  frames — is gated by the same three tests, so it cannot hand the lock to a flicker either.
  `LockCore`'s own re-acquisition is a separate mechanism and is not affected. **An explicit click is
  never gated**; all of this only stops the resolver from volunteering a target.

  Rules 1–2 were added after run 1 (`bench/benchlog.md` 2026-09-04, "Run 1 … edge-entry failure"), where
  the resolver auto-acquired a 29×194 px, conf 0.17 sliver of a person still entering at the right edge
  and handed `LockCore` a size reference no later frame of that person could match. Rule 3 was added
  after run 2 ("Run 2 … junk-track lock"), where a persistent low-confidence "person" track on a static
  room object flickered over 0.5 for a **single** frame, cleared rules 1–2 on it, and held the lock for
  the rest of the capture.
- **Filter noise:** `q_acc_std`/`p0_vel_std` (position filter's process/initial-velocity noise —
  `p0_vel_std` is why a target already moving when `lock()` fires is covered by the very first
  post-lock gate rather than assumed stationary), `r_pos` (position measurement noise), `q_size`/
  `r_size` (size filter's process/measurement noise).
- **Score weights:** `w_conf`/`w_motion`/`w_size`/`w_class`/`w_id`, summing to 1.0 in the shipped
  defaults (not enforced by the code — a config that changes them is free to use any positive weights).
- **`frame_w`/`frame_h`** are **not** part of the `lock` block — `LockCore`'s `Params.frame_w/h` are
  always set from this node's own top-level `frame_w`/`frame_h` (there is only one frame size in this
  process); a `lock.frame_w`/`lock.frame_h` key would be silently ignored.

### Association is two-stage (local first, full-frame only after local fails)

Per spec §8.2 — "search near the prediction first, expand with uncertainty, full-frame only after
local search fails … if two candidates are ambiguous, report OCCLUDED/UNCERTAIN":

1. **Stage 1, in-gate.** Candidates inside the gate (and passing the size check) are scored and
   judged among *themselves*: the best must clear `min_score` and beat the runner-up **in this pool**
   by `ambiguity_ratio`. If it does, that is the frame's association and stage 2 never runs.
2. **Stage 2, widened (full-frame).** Runs only while the widened window is open (`obs_age_ms` in
   `occlusion_ms .. occlusion_ms + reacquire_ms`) **and** stage 1 found nothing plausible at all —
   an empty in-gate pool, or an in-gate pool whose best does not even clear `min_score`. Out-of-gate
   candidates must match the locked class and pass the size check; they are scored against
   `min_score_widened` with the margin rule applied within that pool only.
3. **An ambiguous stage 1 ends the frame.** Two plausible candidates near the prediction means the
   state stays `occluded`/`reacquiring` — the widened search is *not* consulted as a tie-break.
   Widening the search because the local picture is confusing is exactly how a lock jumps to a
   stranger across the room.
4. **The score floor depends on the BAND, not the stage** (on-board fix round 4, Ruling 20b). While
   `reacquiring` (`obs_age_ms` in `occlusion_ms .. expire_ms`) **every** candidate is judged against
   `min_score_widened` — the in-gate pool included. `confirmed` and `occluded` keep `min_score`. The
   two bands ask different questions: a mediocre local match moments after a sighting is more likely
   to be the wrong object than the right one, whereas after seconds of absence it is the best evidence
   available and refusing it only runs the clock down to `lost`. Derived floors for an IN-GATE, new-id,
   same-class, exactly-size-matched candidate (so its score is `0.25·conf + 0.35·exp(-d²/2) + 0.30`;
   arithmetic on config constants, **not** a bench number):

   | `d²` | motion term | conf needed while `reacquiring` (floor 0.40) | conf needed while `occluded` (floor 0.5) |
   |---|---|---|---|
   | 2.23 (≈1.5σ) | 0.115 | **any** (the weights alone clear 0.40) | **0.34** |
   | 4 (2σ) | 0.047 | **0.21** | **0.61** |
   | 9 (3σ, the gate edge) | 0.004 | **0.38** | **0.78** |

   Run 7's owner re-emerged from a 6-second hide at conf 0.27–0.35, in gate, and was refused by the
   right-hand column for 9 s until the lock expired. Note the top-right cell: near the prediction and
   size-matched, the reacquiring floor is met on the weights alone — the same thinness already flagged
   for the widened stage above, now reachable in-gate too. What still refuses a wrong candidate there
   is the ambiguity margin, not the floor.

**The class gate: different class *and* a different id is never associated** (on-board fix round 5,
Ruling 22.1). Before every gate, score and stage above, a candidate is admitted at all only if its
class equals the **locked** class — the class fixed at `lock()`, which never changes — *or* it carries
the core's own current `lock.id`. There is no config knob: "a different class under a different id is
a different object" is not a tuning parameter. Two things follow:

- **A same-id class flicker is still followed.** The detector re-labelling the box it is already
  tracking (`cell phone` → `remote` → `cell phone` on one id, which run 10e does constantly) is
  exactly the case the multi-object tracker's own frame-to-frame continuity vouches for, and the
  class score term (`w_class`) is unchanged for it — it just contributes 0 on those frames.
- **A re-label under a NEW id is not taken, and that is a real cost.** If the phone leaves the frame
  and comes back as `remote` with a fresh id, the core will *not* re-acquire it until a `cell phone`
  detection appears again; it will sit in `reacquiring` and may expire. Telling that case apart from
  "a different object that happens to be nearby" needs appearance matching (F3), which is not built.
  Round 5 chose the false-negative over the false-positive, because the false-positive is a lock that
  silently claims to hold something it does not.

Before round 5, class was a soft 0.15 score term only, so a high-confidence box of *any* class could
win on `w_conf·conf + w_motion·exp(-d²/2)` alone. That is the first of run 10e's three mechanisms:
with the phone gone, the core walked across `knife`/`remote`/`hair drier` boxes at quality 0.40–0.56
and settled on a static `chair`/`suitcase`, holding it `confirmed` for twelve minutes
(`bench/benchlog.md`, "Run 10e").

**Follow, but do not learn** (on-board fix round 4, Ruling 20a). A candidate admitted **only** by the
same-id relaxation — one that fails the *strict* (×1) position gate or the *strict* size tolerance —
corrects the position filter but **not** the size filter, whose variance simply keeps growing. A
candidate that clears the strict gates corrects both, and so does any new-id candidate (it never used
the relaxation), including one taken by the widened stage — so the core can still learn a target's
size after a genuine re-acquisition. The reason: partial occlusion and edge clipping shrink a box
transiently, and the tracker's id continuity is good evidence about *where* the target is while being
no evidence at all about *what size* it is. In run 7 the engine kept the locked id alive on the
owner's head above a chair back (155×625 → 276×159 → 152×129 in half a second); the core followed it
and learned it, and then could not recognise her full body when she stood up. `Output.ref_w`/`ref_h`
expose the size reference for tests and diagnostics — the failure is invisible from `lock.box`, which
while `confirmed` is built *from* that reference.

**The widened path's effective floor is arithmetic on the shipped weights, not a bench number**
(derived from config constants): out of gate the motion term `exp(-d²/2)` is ~0, so a same-class,
size-matched candidate scores `w_conf·conf + w_size + w_class (+ w_id)`. With
`w_conf 0.25, w_size 0.15, w_class 0.15, w_id 0.10`:

| `min_score_widened` | new tracker id | id preserved by the tracker |
|---|---|---|
| 0.5 (before round 3) | conf ≥ **0.80** | conf ≥ **0.40** |
| **0.40** (shipped) | conf ≥ **0.40** | conf ≥ **0** (the weights alone meet it) |

Run 5's M-C is the reason: a lone, same-class, size-consistent candidate at conf 0.82 with a new id
scored ≈0.45 and was refused for 9 s under the 0.5 floor. **Red-team note, stated because the bottom
right cell is uncomfortable:** at 0.40 an out-of-gate candidate that carries the locked id *and*
matches its size exactly clears the floor on `w_size + w_class + w_id` with zero confidence
contribution. It must still match the locked class, pass the (relative) size gate, fall inside the
widened window, and beat the ambiguity margin against anything else in that pool — and a same-id
candidate is rarely out of gate at all now, since `same_id_gate_mult` doubles its gate radius. But
this is the thinnest floor in the core and routine 5 (all classes) is where it would show.

**The gate is a Mahalanobis test against `S = min(P, cap) + R`, floored at `gate_min_px`** (round 3).
Two derived consequences worth having written down: before round 3 the gate omitted `R` altogether, so
a converged filter reporting `uncertainty_px` 3.2 had a gate radius of `3 × 3.2 = 9.6` px — which is
how run 5's 40–60 px per-frame box-centre jitter fell out of gate on a target standing still; and
`gate_max_px` now caps only the state term, so a 650 px box's gate radius after a long coast is
`3·sqrt(10000 + 65²) = 358` px rather than exactly 300. Under both sits the floor
`gate_min_frac · max(w_ref, h_ref)` — 98 px for a 655 px person, 30 px for a 100×200 box.
`uncertainty_px` still reports the raw, uncapped `sqrt(P)`: it is a diagnostic of the filter, and
since round 3 it is deliberately *not* a readout of the gate.

**The size gate is variance-aware** (on-board fix round 1) **and relative to the reference** (round 3).
A candidate is admitted in a dimension when its deviation from the filter's size reference is within

```
tol = max(size_tol · ref, gate_sigma · sqrt(size_var + R_size))        (× same_id_gate_mult for a same-id candidate)
R_size = max(r_size,  (r_size_frac · ref)²)                            = max(100,  (0.15·ref)²) px²
size_var grows at max(q_size, (q_size_frac · ref)²) px² per second     = max(50,   (0.5·ref)²) px²/s
```

Both noise terms were absolute before round 3, which pinned every reference to a ~42–56 px window no
matter its size: run 5's owner walked from a 169 px-wide reference to 594 px in 1.4 s and could not be
re-associated at all (mechanism M-B). The numbers below are **derived from config constants,
arithmetic on the shipped values — not bench measurements**, computed for a **169 px reference** (run
5's own, so the table can be read against that capture), with `size_var` taken as `r_size + rate·t`:

| `obs_age` | `size_var` | tolerance | tolerance, same-id (×2) |
|---|---|---|---|
| 0 s | 100 px² | **84.5 px** (the `size_tol · ref` floor wins) | **169.0 px** |
| 0.5 s | 3670 px² | **197.0 px** | **394.0 px** |
| 1.4 s | 10096 px² | **310.9 px** | **621.8 px** |
| 3 s | 21521 px² | **446.6 px** | **893.2 px** |

Against run 5's actual widths for the same live id 1309, at 0.1 s sampling steps from that 169 px
reference (`rate = max(50, (0.5·169)²) = 7140.25` px²/s, `R_size = max(100, (0.15·169)²) = 642.6` px²):

| t | width | deviation | tolerance | admitted? | same-id (×2) | admitted? |
|---|---|---|---|---|---|---|
| 0.1 s | 231 | 62 | 114.5 | yes | 229.0 | yes |
| 0.2 s | 279 | 110 | 139.8 | yes | 279.5 | yes |
| 0.3 s | 327 | 158 | 161.1 | yes | 322.3 | yes |
| 0.4 s | 428 | 259 | 180.0 | **no** | 359.9 | yes |
| 0.5 s | 515 | 346 | 197.0 | **no** | 394.0 | yes |
| 0.6 s | 594 | 425 | 212.7 | **no** | 425.4 | yes |

In practice the sequence never reaches the later rows: the first row is admitted, the reference is
corrected up, and each subsequent step is a small deviation from a reference that has already moved.
The table is the worst case — a reference that stayed frozen at 169 px throughout — and it shows the
same-id relaxation is what covers that worst case end to end. Under round 1's absolute model the same
column read ~43 px at 0 s and ~79 px at 10 s against these 62–425 px deviations, i.e. nothing after
the first row could ever be admitted.

A 29 px reference (run 1's sliver, for comparison) now gets `rate = max(50, 210.25) = 210.25` px²/s
and `R_size = max(100, 18.9) = 100` px², so its tolerance is 46.7 px at 200 ms (93.3 px same-id) —
where round 1 granted 42.4–56.1 px and the original fixed gate only `0.5 × 29 = 14.5` px. That is why
`tests/test_lock_core.cpp` case 19b, which replays run 1's own rows and used to pin "this sequence
does **not** recover", now pins that it recovers on its first row. It does not make run 1 a good
outcome — locking a conf-0.17 edge sliver is still wrong and is still prevented upstream by the
auto-acquire gate — but a lock that somehow started on a bad reference now recovers from it instead of
decaying to LOST.

**The coasting prediction is clamped to the frame.** While no candidate wins, the predicted centre is
bounded to `[0, frame_w] × [0, frame_h]` (velocity, covariance and the published frozen box are
untouched). Unclamped, `pos += vel·dt` puts a 300 px/s walk-out ~600 px past the edge within 2 s, so
the local gate no longer covers the edge the target must re-enter through and re-acquisition falls
back on that steep widened floor. Clamped, a target returning at the edge it left by is picked up by
stage 1 on its own geometry. (`Params.frame_w/frame_h` exist for this; the node always sets them from
its own top-level `frame_w`/`frame_h`.) The final-fix wave's Ruling 14 originally specified a
`[-gate_max_px, frame_w + gate_max_px]` region; with the shipped constants that margin equals the
whole capped gate radius, which leaves an edge re-entry ≥ 350 px from the clamped centre
(`d² ≥ 12.25 > gate_sigma² = 9`) — outside the gate it was meant to bring it into — so the clamp
region is the frame itself. Recorded in `lock_core.hpp`'s `Params` comment and in the fix report.

### Snapshot: the `lock` object

`/api/state`'s `lock` object gained nine fields (additive — `id`/`class`/`coasting` are unchanged in
shape and meaning) next to the existing three:

```json
"lock": {
  "id": 7, "class": "person", "coasting": false,
  "state": "confirmed", "identity_locked": true, "observation_valid": true,
  "control_valid": true,
  "quality": 0.91, "obs_age_ms": 0.0, "uncertainty_px": 5.2,
  "epoch": 2, "box": {"x": 612.0, "y": 303.0, "w": 40.0, "h": 60.0}
}
```

*(Illustrative values — a plausible shape, not a measurement. Every measured number lives in
`bench/benchlog.md`.)*

`state` is exactly `garuda::lock::state_name()`'s string ("none"/"confirmed"/"occluded"/
"reacquiring"/"lost"). **All twelve fields now come from `LockCore`'s `Output`** (except
`control_valid`, computed by the node from the `Output` plus the snapshot's own `age_ms`), **not from
`LockResolver`**:

- `control_valid` (on-board fix round 9, Ruling 30) —
  `observation_valid && (obs_age_ms + age_ms) <= lock.control_valid_ms`. **This is the field a follow
  controller must gate on**; `observation_valid` alone says the core associated something on its last
  update and says nothing about how old that update is by the time a consumer reads it, and `age_ms`
  adds the capture-to-publish half of the same staleness. `observation_valid` keeps its existing
  meaning unchanged. A frame with no ISP timestamp publishes `age_ms: null`, and the calculation then
  substitutes 0 for that half — visible in the snapshot, so a consumer can see the transport half was
  unmeasured on that row.

- `id` — the id the lock last associated to, or **`null` whenever `identity_locked` is false**
  (`none` *and* `lost`). **null ⇔ no identity**: a non-null `lock.id` always means something is
  locked right now, which is the pre-`LockCore` contract. `class` is likewise empty then. (While a
  lock is held, `id` follows whichever candidate wins the gate — the id is not sacred, position/size/
  class continuity is — so it *can* change without the lock having moved to another object. That is
  what `epoch` is for.)
- `class` — **the class of the last observation the core associated** (on-board fix round 5,
  Ruling 22.3), not the class fixed at `lock()`; empty until something is locked, unlike the
  pre-`LockCore` `lock` object, which always echoed the resolver's *target* class (defaulting to
  `"person"`) even with nothing locked. It therefore **changes** whenever the core follows a
  re-labelled same-id box, which is the only way a different class can win at all (see the class gate
  above), and it holds the last associated class through `occluded`/`reacquiring`/`lost`. The class
  the gate tests against is the locked one and is deliberately **not** published — the two differ
  exactly while the core is riding a flicker. Before round 5 this field was the locked class and so
  could never change: run 10e published `"cell phone"` for twelve minutes of suitcase, and the bench
  harness's `class_switches` column (`lock_metrics.py`) exists to make that visible, so it reads 0 on
  every capture taken before this round including run 10e's own.
- `coasting` — `identity_locked && !observation_valid` (true during `occluded`/`reacquiring`).
- `epoch` — the lock generation: `0` before the first lock, `+1` on every `lock()`, **never reset**
  (an `unlock()` keeps publishing the epoch of the lock it ended). A change means a genuinely new
  lock — a click, a target change, a post-`lost` hand-over. An `id` change *within* one epoch is the
  tracker underneath renumbering the same object, which `LockCore` is designed to ride through. The
  bench harness (`bench/evidence/2026-09-04-lock-core/lock_metrics.py`) splits its identity column on
  exactly this: `relocks` (epoch changes) vs `id churn` (id changes inside one epoch) vs
  `class switches` (class changes inside one epoch, round 5). **`relocks` alone is not the
  false-lock column** — run 10e's twelve-minute walk onto a suitcase happened entirely inside one
  epoch, so `relocks` read 0; the harness's "false relocks" alias is `relocks + class_switches` since
  round 5.
- `box` — `{x, y, w, h}` in frame pixels, or `null`, following the state table above.

`tracks[]` is unaffected — it still comes from the resolver's alive-record list, independent of what
`LockCore` is doing, and its box for the locked id is the tracker engine's, not `lock.box`.

### Node integration: the resolver hands over the pick

`LockResolver` (§6/§9) keeps running every frame exactly as before — it still owns click/target
handling, its own class-based auto-acquire, and its own re-acquire jump, and its `alive` list still
drives `tracks[]`. What changes is that `LockCore`, not the resolver, now owns the **published**
`lock` object once it holds an identity. Per frame, after whichever tracker engine (`mono` or
`hailo`) has stepped and `resolver.step()` has produced this frame's pick:

1. **A `target` command always drops `LockCore`'s identity** (`unlock()`) — the user chose a different
   class, so whatever was locked no longer applies.
2. **A click always drops what was held** (`unlock()`) unless it names the id the core already holds,
   in which case it is a re-affirmation and nothing changes.
3. **On a frame carrying a click, the ONLY thing that may seed the core is the clicked object's own
   live observation.** This holds on every path — including the first click of a session and any
   click after a `lost`, which until the final-fix wave still went through the resolver's generic
   pick. It matters because `LockResolver::step()` runs its own re-acquire jump *after* `click()` has
   set its lock id, so a click on a box that is coasting past the resolver's `reacq` threshold can
   leave that pick on a **different** live same-class track on the very same frame; locking onto it
   would hand the lock to an object the user did not click. **If the clicked object is not live this
   frame, the core stays `none` for that frame** (it seeds only from a real measurement — Ruling 4)
   and the published `lock.id` is `null`; the generic path does *not* run as a fallback on that
   frame, and no "pending click" is remembered. **Accepted residual until F5 (click–frame sync):** on
   the NEXT frame the generic path (rule 4) may lock the resolver's own, possibly drifted, pick — so
   a click on a coasting box can still end up one frame later on a different object. That is the cost
   of seeding only from live measurements, and F5 is where it gets fixed.
4. **On a frame with no click, whenever `LockCore` is left with no identity** (`none` or `lost`) **and
   the resolver's pick this frame is one of this frame's *live* (not coasting) observations,
   `LockCore` locks onto it** (`lock(obs, ts_ms)`). If the resolver's pick isn't live this frame (e.g.
   it picked a coasting track because nothing better existed), the hand-over waits for a frame where
   it is.
5. **While `LockCore` already holds an identity and none of the above fired**, the resolver's own
   re-acquire jump is **never** applied to the publish — only `LockCore::update()`'s own gated
   Kalman/scoring logic can move the published lock. This is the core behavioural change: a stray
   frame-count-based re-acquire in the resolver can no longer silently hijack the published lock while
   `LockCore` is still confidently tracking (or legitimately coasting through) the real target.

`ts_ms` is the frame's ISP clock (`isp_timestamp_ns / 1e6`). A `0` timestamp (no valid ISP clock for
that frame) is logged once and handled two ways: **while a lock is held** it is filled in as the last
timestamp plus one nominal frame interval — the `sink0` framerate, read once at startup from the
media-library profile chain the node is already pointed at, else the last measured interval — so the
series never leaves the ISP's clock domain (a `steady_clock` reading dropped into it would make
`obs_age_ms` either enormous, i.e. instant `lost`, or negative); **with no lock held and no earlier
timestamp**, it falls back to `steady_clock` as before. State transitions are logged once each
(`lock: confirmed -> occluded (obs_age_ms=...)`), never per frame, and rate-limited to one line per
second per direction — a detector missing every other frame would otherwise print
`confirmed`↔`occluded` at frame rate; the next line printed for that direction carries
`[+N suppressed]`.

### Verification

**On-board fix round 7 (Ruling 24), 2026-09-04 — current state.** Native `ctest` **14/14** (five new
`test_hailo_track_adapter` birth-gate cases; `test_lock`'s streak block rewritten for the sliding
window, with the frame-by-frame arithmetic in its comments); cross-build `build-h15l` clean,
`grep -c "warning:"` = **0**. **Deployed** with `config/perception-yolov11s.json` — the follow profile
from this round on — and **no routine was run**: the live re-measurement of both fixes is
`TBD-bench` (`bench/benchlog.md`, "Round 7 — clutter and re-acquire"). The board's own lines confirm
the round is live:

```
selected config's hef (/opt/garuda/models/yolov11s_hailo15l_v5.3.0.hef) is present on the board (not the pinned yolo26m — no md5 check, no copy)
tracker: keep_lost_frames=75 max_lost=75
lock: auto-acquire gate conf>=0.50, edge margin 0.020*1280 = 25.6 px, streak>=5 frames within a 15-frame window
tracker.engine=hailo classification_id=1 kalman_distance=0.70 iou_threshold=0.80 init_iou_threshold=0.90 keep_tracked_frames=0 keep_new_frames=5 keep_lost_frames=75 min_hits=1 dedupe_containment=0.80 dedupe_iou=0.60 birth_conf=0.40
frames=301 fps=30.1
```

**On-board fix round 5 (Ruling 22), 2026-09-04.** Native `ctest` **14/14** (the new
`lock_replay_phone` suite replays the rel. 97.5–200.0 s window of run 10e's routine-5 capture);
cross-build `build-h15l` `[13/13]`, `grep -c "warning:"` = **0**; harness `pytest` **12/12**.
**Deployed** with `config/perception-yolov8m.json` (person profile) — **no routine was run**. The
board's own startup lines confirm the round is live:

```
lock: auto-acquire gate conf>=0.50, edge margin 0.020*1280 = 25.6 px, streak>=5 frames
lock: core gates r_pos_frac=0.10 gate_min_frac=0.15 r_size_frac=0.15 q_size_frac=0.50 same_id_gate_mult=2.00 min_score=0.50 min_score_widened=0.40 size_ratio_max=1.60
lock: class gate on (a different-class candidate is eligible only on the core's own track id); lock.class publishes the last associated observation's class
lock: nominal frame interval 33.33 ms (from the media-library profile's sink0 framerate)
```

Phone replay, before (`097bfad`) and after — the test's own printed lines:

```
pre-fix:  confirmed-on-phone-live 0.8013 | cross-class CONFIRMED 12 | rows on the false-lock id 163: 958
          final row t=102441 ms state=confirmed last_id=163 winner class 'suitcase'
after:    confirmed-on-phone-live 0.8150 | cross-class CONFIRMED  0 | rows on the false-lock id 163:   0
          final row t=102441 ms state=lost last_id=188 winner class '-'
```

`lock_replay` (routine 1) and `lock_replay2` (routine 2) are unchanged and green. Full numbers, the
capture's own harness rows, the id-change trace and the red team: `bench/benchlog.md`, "Run 10e".

**On-board fix round 4 (Ruling 20), 2026-09-04.** Native `ctest` **13/13** (the new
`lock_replay2` suite replays the rel. 170–205 s window of run 7's routine-2 capture); cross-build
`build-h15l` `[13/13]`, `grep -c "warning:"` = **0**; harness `pytest` **11/11**. **NOT deployed** —
a capture was live on the board when this round landed, and the controller deploys it. Routine-2
replay, before (217fb04) and after:

```
before:  6s hide — CONFIRMED never; LOST rows 139 (first t=21079 ms)
after:   6s hide — CONFIRMED t=14949 ms (delta 0 ms from the owner being detectable again) on id 31;
                   LOST rows 0; size reference entering the re-emergence 324.9x381.4
```

Routine-1 replay is unchanged-good at **0.9802** (was 0.9854 before round 4; the size filter now
learns from fewer frames, and the gate is ≥ 0.95). Full numbers, the ablation showing which of
Ruling 20's three changes carries the result, and the red team: `bench/benchlog.md`, "Run 7".

**On-board fix round 3 (Ruling 19), 2026-09-04.** Native `ctest` **12/12** (the new
`lock_replay` suite replays all 1196 rows of `run5_routine1_walk.txt.gz` through a fresh `LockCore`);
cross-build `build-h15l` `[13/13]`, `grep -c "warning:"` = **0**; harness `pytest` **11/11**. Deployed
with `config/perception-yolov8m.json`; the board's own startup line confirms the round is live and
**no routine was run** (run 6 is the owner's):

```
lock: auto-acquire gate conf>=0.50, edge margin 0.020*1280 = 25.6 px, streak>=5 frames
lock: core gates r_pos_frac=0.10 gate_min_frac=0.15 r_size_frac=0.15 q_size_frac=0.50 same_id_gate_mult=2.00 min_score=0.50 min_score_widened=0.40
lock: nominal frame interval 33.33 ms (from the media-library profile's sink0 framerate)
frames=301 fps=30.1
```

The older verification text below is kept as the record of the earlier rounds.

Native (`ctest --test-dir build-x86`): 11/11 green, including the updated `test_snapshot` (golden
comparison is now a subset check — the Pi's golden predates these fields — plus explicit presence/type
assertions on the eight new keys). Cross-build (`build-h15l`, `-DGARUDA_BUILD_NODE=ON`): `grep -c
"warning:"` over a from-scratch build log is `0` (the only non-empty diagnostic is the pre-existing
GCC `note:` about `std::make_pair<float,float>` ABI — unrelated, pre-existing code, not a `warning:`
line, documented in the Kalman-tracker task's own report). Re-verified after the final-fix wave
(2026-09-04): `ctest` 11/11, cross-build 13/13 targets with 0 `warning:` lines, `shim ok`, and the
harness's own `pytest` 10/10.

Deploy + on-board verification (yolov8m/hailo walk-out/walk-back/stay-out sequence, then a one-poll
mono-engine confirmation): **PENDING — board unreachable.** Link lost per the owner
(2026-09-04 09:17:52); checked twice in this round, both after all code/build work was done and once
more immediately before committing — `ping -c 2 -W 2 10.0.0.1` (100% loss both times) and
`ssh -o ConnectTimeout=5 root@10.0.0.1 uptime` (connection timed out both times), last checked
2026-09-04 10:37:37 IST; the PC's own wired interface (`eno1`) reports `unavailable` (no link),
consistent with the board being powered off rather than a routing-only problem. The config/build/
README/comment changes are all committed and cross-built clean; deploying
`config/perception-yolov8m.json` and capturing timestamped `/api/state` polls through a real
walk-out/walk-back/stay-out sequence (`lock.state` CONFIRMED → OCCLUDED → REACQUIRING → CONFIRMED →
LOST, `obs_age_ms` counting in ms, `uncertainty_px` growing while out, the frozen box unchanged while
OCCLUDED/REACQUIRING) is owed once the board and the owner are both available.
