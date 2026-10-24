#!/usr/bin/env python3
"""Generate the node's media-library config from the stock hailo15l/imx678 detection profile.
Only application_input_streams is ours; ISP/sensor/stabilizer files stay Hailo's, referenced in place.
Run on the PC (writes into hosts/hailo15l/medialib/), then deploy.sh copies to /opt/garuda/medialib/.

Two profiles are generated (into TWO top-level medialib configs -- see below):
  - "Garuda" (M2 default): sink0 640x640, LETTERBOX_MIDDLE — required by yolo26m's square input.
  - "GarudaYolov8n" (rollback): sink0 640x384, no scaling_mode (M0/M1 geometry) — required by the
    stock hailo_yolov8n_384_640 HEF's fixed input shape.
sink1 (JPEG feed) is identical in both — only sink0, the detector input, differs.

Two top-level medialib configs, not one, because of a verified MediaLibraryInterface behaviour
(hosts/hailo15l/README.md §4/§8 has the evidence): initialize() commits sink0's ACTUAL physical
geometry from the config's own default_profile; the node's later media->set_profile(cfg["profile"])
call (node_main.cpp) does not re-negotiate that geometry — confirmed by restarting isp_media_server
fresh (no effect) versus flipping default_profile (fixed it). So which profile is *live* for a given
deploy is decided by default_profile, and each perception*.json's own "medialib_config" field
(already a per-config key) is what selects between them:
  - garuda_medialib_config.json         — default_profile "Garuda"        (yolo26m, config/perception.json)
  - garuda_medialib_config_yolov8n.json — default_profile "GarudaYolov8n" (rollback, config/perception-yolov8n.json)
Both files list both profiles (harmless, keeps them interchangeable); "profile" in perception*.json
still must name one that's listed, and the node's set_profile() call re-affirms whichever is already
the file's default_profile — a no-op in the cases that matter, kept because the API still requires it.
"""
import json, pathlib, sys
STOCK = "/etc/imaging/cfg/hailo15l/imx678/theia_sl410m/4k/profiles/daylight/detection_daylight"
BOARD = "/opt/garuda/medialib"
here = pathlib.Path(__file__).resolve().parent
prof_dir = here / "profile"; prof_dir.mkdir(exist_ok=True)

def application_settings(description, sink0):
  return {
    "version": "3.0.0",
    "metadata": {"architecture": "hailo15l", "content_hash": "", "description": description, "generation_timestamp": ""},
    "application_input_streams": {
      # BILINEAR, not AREA: AREA is listed in libmedialib's schema (AREA/BICUBIC/BILINEAR/
      # NEAREST_NEIGHBOR) but this board's deployed DSP resize path rejects it at runtime --
      # "[hailodsp] [error] [resize.cpp:980] [dsp_telescopic_multi_crop_and_resize_perf] Error:
      # Interpolation type (2) not supported" -- and the pipeline never produces a frame while it's
      # selected (verified 2026-09-03: no frames= line, /api/state stuck at "no snapshot yet").
      # Reverted per the fallback the change was gated on; BILINEAR is what every prior profile used.
      "format": "IMAGE_FORMAT_NV12", "method": "INTERPOLATION_TYPE_BILINEAR",
      "resolutions": [
        sink0,
        {"stream_id": "sink1", "width": 1280, "height": 720, "framerate": 30, "pool_max_buffers": 12},
      ]},
    "digital_zoom": {"enabled": False, "magnification": 1.0, "mode": "DIGITAL_ZOOM_MODE_MAGNIFICATION", "roi": {"x": 0, "y": 0, "width": 3840, "height": 2160}},
    "flip": {"enabled": False, "direction": "FLIP_DIRECTION_NONE"},
    "gmv": {"frequency": 0.0, "source": "isp"},
    "hailort": {"device-id": "device0"},
    "motion_detection": {"enabled": False, "buffer_pool_size": 8, "resolution": {"width": 640, "height": 480, "framerate": 30},
                         "roi": {"x": 0, "y": 0, "width": 640, "height": 480}, "sensitivity_level": "MEDIUM", "threshold": 0.5},
    "optical_zoom": {"enabled": False, "magnification": 1.0, "max_dewarping_magnification": 3.0},
    "rotation": {"enabled": False, "angle": "ROTATION_ANGLE_0"},
  }

def garuda_profile(description, app_settings_filename):
  return {
    "version": "1.0.0",
    "metadata": {"architecture": "hailo15l", "content_hash": "", "description": description, "generation_timestamp": ""},
    "application_settings": f"{BOARD}/profile/{app_settings_filename}",
    "encoded_output_streams": [],
    "iq_settings": f"{STOCK}/iq_settings.json",
    "sensor_config": f"{STOCK}/sensor_config.json",
    "stabilizer_settings": f"{STOCK}/stabilizer_settings.json",
  }

def medialib_top(description, default_profile):
  return {
    "version": "2.0.0",
    "metadata": {"architecture": "hailo15l", "content_hash": "", "description": description, "generation_timestamp": ""},
    "backup_folder_path": f"{BOARD}/backups",
    "default_profile": default_profile,
    "profiles": [
      {"name": "Garuda", "config_file": f"{BOARD}/profile/garuda_profile.json"},
      {"name": "GarudaYolov8n", "config_file": f"{BOARD}/profile/garuda_profile_yolov8n.json"},
      {"name": "GarudaYolov8m", "config_file": f"{BOARD}/profile/garuda_profile_yolov8m.json"},
    ],
  }

# "Garuda" — M2 default: sink0 letterboxed 640x640, required by yolo26m's square input.
# framerate 25 (not 30) and pool_max_buffers 6 (not 20): the yolo26m HEF's own multi-context
# compile bounds the detect stage at ~25.74 fps (hailortcli benchmark, bench/benchlog.md
# 2026-09-03 "yolo26m from the Hailo model zoo"), below the camera's native 30 fps. At 30 fps
# every non-leaky queue upstream of det_sink (detect input 4 + 4 in-flight jobs + post input 5 +
# det_sink 1, see node_main.cpp's queue-depth comment) plus this pool fills and stays full,
# producing a standing backlog (measured age_ms 836-892 ms, ADDENDUM 2026-09-03 in
# bench/benchlog.md). Feeding sink0 at the detector's own steady-state rate keeps the pool from
# perpetually backing up; 6 is enough headroom for the frontend/detect handoff without
# re-introducing a multi-second buffer (pool_max_buffers is a DEPTH bound, not a rate — the actual
# throttle is the framerate field). GarudaYolov8n (below) is untouched: the stock yolov8n HEF
# matches the camera's 30 fps, so it never builds this backlog.
app = application_settings("garuda-perception M2",
      {"stream_id": "sink0", "width": 640, "height": 640, "framerate": 25, "pool_max_buffers": 6, "scaling_mode": "LETTERBOX_MIDDLE"})
(prof_dir / "application_settings.json").write_text(json.dumps(app, indent=2) + "\n")
profile = garuda_profile("garuda-perception M2", "application_settings.json")
(prof_dir / "garuda_profile.json").write_text(json.dumps(profile, indent=2) + "\n")

# "GarudaYolov8n" — rollback: sink0 stretched 640x384 (M0/M1 geometry), required by the stock
# hailo_yolov8n_384_640 HEF's fixed input shape.
app_y8n = application_settings("garuda-perception M2 rollback (M0 sink0 geometry, stock yolov8n HEF)",
      {"stream_id": "sink0", "width": 640, "height": 384, "framerate": 30, "pool_max_buffers": 20})
(prof_dir / "application_settings_yolov8n.json").write_text(json.dumps(app_y8n, indent=2) + "\n")
profile_y8n = garuda_profile("garuda-perception M2 rollback profile", "application_settings_yolov8n.json")
(prof_dir / "garuda_profile_yolov8n.json").write_text(json.dumps(profile_y8n, indent=2) + "\n")

# Two top-level configs (see module docstring for why) — same profiles list, different default.
top = medialib_top("garuda-perception", "Garuda")
(here / "garuda_medialib_config.json").write_text(json.dumps(top, indent=2) + "\n")
top_y8n = medialib_top("garuda-perception rollback (default profile GarudaYolov8n)", "GarudaYolov8n")
(here / "garuda_medialib_config_yolov8n.json").write_text(json.dumps(top_y8n, indent=2) + "\n")

# "GarudaYolov8m" — A/B detector (2026-09-03, owner's request): the zoo yolov8m for hailo15l takes a
# 640x640 NV12 input and carries its own baked NMS, so the STOCK post-process reads it and the
# node's xmin*frame_w mapping needs a plain STRETCH (no letterbox): sink0 640x640 stretched from the
# full FOV, framerate 30 (the model benchmarks well above 30 fps on this board — bench/benchlog.md
# 2026-09-03 yolov8m section — so nothing queues), pool 6 as for the M2 profile.
app_y8m = application_settings("garuda-perception yolov8m A/B (sink0 640x640 stretched, zoo yolov8m HEF)",
      {"stream_id": "sink0", "width": 640, "height": 640, "framerate": 30, "pool_max_buffers": 6})
(prof_dir / "application_settings_yolov8m.json").write_text(json.dumps(app_y8m, indent=2) + "\n")
profile_y8m = garuda_profile("garuda-perception yolov8m A/B profile", "application_settings_yolov8m.json")
(prof_dir / "garuda_profile_yolov8m.json").write_text(json.dumps(profile_y8m, indent=2) + "\n")
top_y8m = medialib_top("garuda-perception yolov8m A/B (default profile GarudaYolov8m)", "GarudaYolov8m")
(here / "garuda_medialib_config_yolov8m.json").write_text(json.dumps(top_y8m, indent=2) + "\n")
print("wrote", here / "garuda_medialib_config.json", here / "garuda_medialib_config_yolov8n.json",
      here / "garuda_medialib_config_yolov8m.json", prof_dir)
