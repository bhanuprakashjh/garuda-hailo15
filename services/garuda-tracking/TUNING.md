# Local bench tuning

Open http://10.0.0.1:8099 and use **Live tuning** below the video.
This is the existing board-only viewer, not a public hosted service. Keep it on
the trusted bench network; it is not an authenticated Internet-facing control API.

- Camera Apply changes automatic/manual exposure and gain without a restart.
- **10 ms test** requests 10 ms and estimates gain from the current exposure ×
  gain product, capped at 30×. This is approximate brightness compensation.
- Detector FPS changes the AI input stream; preview FPS changes the preview
  stream and JPEG emission limit. Processing FPS is measured from frame sequence
  and capture-time deltas, not the requested setting. Sensor mode remains 30 FPS.
- FPS/tracking Apply restarts only the tracker, checks for newly captured frames,
  and restores the previous configuration if startup fails. Selection clears.
- Baseline is saved before the first change in `/opt/garuda-fresh/tuning-baseline.json`.
  Restore reinstates that configuration and camera mode, not arbitrary factory defaults.
- Lower confidence thresholds can increase false positives. Coast retention does
  not extend observation freshness or enable automatic identity reacquisition.

Settings persist in the current bench configuration. A lifecycle command such as
`start-phone` copies its named profile over `current.json`; ISP manual settings
can also reset when another process reinitializes the camera or on reboot.
Only local profile files are modified; vendor IQ and sensor files are untouched.

Observed interactively on 2026-09-11 (NOT a recorded harness run — no output is
committed and `bench/benchlog.md` carries no entry, so per rule 1 these are
`TBD-bench` until re-measured and recorded): manual 10 ms read back ~9.999 ms;
requested 30 FPS detector and 20 FPS preview showed ~29.9999 processing FPS.
Restore returned to 20 FPS detector, 10 FPS preview, automatic exposure. The
detector executable was not replaced. Even once recorded, these checks verify
controls and throughput, not tracking accuracy. Note the 2026-09-12 review also
found `exposure_ms` rejects fractional values and that Apply rewrites the sink1
rate from `jpeg_fps` (10) rather than the stream's actual 20 FPS — both open.
