"""Read-only installed-camera audit; run with the board's Python, no extra deps.

Configuration is not runtime proof. Only V4L control readbacks and API samples
are labelled runtime. No profiles, sensor controls or processes are modified.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import urllib.request


class Audit:
    def __init__(self, root=Path('/')):
        self.root = root.resolve()
        self.files = {}

    def path(self, name):
        path = (self.root / str(name).lstrip('/')).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('path escapes audit root')
        return path

    def digest(self, name):
        path = self.path(name)
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(block)
        self.files[str(name)] = dict(sha256=sha.hexdigest(), bytes=path.stat().st_size)
        return sha.hexdigest()

    def read(self, name):
        self.digest(name)
        return json.loads(self.path(name).read_text())

    def profile(self, name):
        profile = self.read(name)
        app = self.read(profile['application_settings'])
        iq = self.read(profile['iq_settings'])
        sensor = self.read(profile['sensor_config'])
        denoise = iq.get('denoise', {})
        network = denoise.get('network', {}).get('network_path')
        model = dict(path=network, present=bool(network and self.path(network).is_file()))
        if model['present']:
            model['sha256'] = self.digest(network)
        ae = iq.get('automatic_algorithms', {}).get('AdaptiveAe', {})
        return dict(path=name, configured_only=True,
                    input_video=sensor.get('input_video'),
                    sensor=sensor.get('sensor_configuration'),
                    streams=app.get('application_input_streams'),
                    digital_zoom=app.get('digital_zoom'), optical_zoom=app.get('optical_zoom'),
                    ai_denoise={k: denoise.get(k) for k in ('enabled', 'bayer', 'method', 'loopback-count', 'sensor')},
                    denoise_model=model, hdr=iq.get('hdr'), dewarp=iq.get('dewarp'),
                    auto_exposure={k: ae.get(k) for k in ('enable', 'priority', 'priorityHdr')})

    def collect(self):
        cfg = self.read('/opt/garuda-fresh/current.json')
        media = self.read(cfg['medialib_config'])
        selected = [p for p in media['profiles'] if p['name'] == cfg['profile']]
        if len(selected) != 1:
            raise ValueError('active profile must resolve exactly once')
        active = self.profile(selected[0]['config_file'])
        catalog = '/etc/imaging/cfg/hailo15l/imx678/theia_sl410m/4k/medialib_configs/frontend_api_example_config.json'
        candidates = {}
        for p in self.read(catalog)['profiles']:
            try:
                candidates[p['name']] = self.profile(p['config_file'])
            except (OSError, ValueError, KeyError) as error:
                candidates[p['name']] = dict(error=str(error))
        return dict(schema='garuda.camera_audit.v1', active_profile_name=cfg['profile'],
                    active=active, installed_candidates=candidates, files=self.files,
                    tracker_config={k: cfg.get(k) for k in ('hef', 'input_geometry', 'frame_w', 'frame_h',
                        'managed_detection', 'target_roi', 'detection_tiles', 'person_embedding_max_per_frame')},
                    caution='Configured capabilities are not proof of enabled hardware features or throughput.')


def parse_controls(raw):
    values = dict(re.findall(r'(isp_ae_\w+):\s*(\d+)', raw))
    return dict(auto=bool(int(values['isp_ae_enable'])),
                exposure_ms=int(values['isp_ae_integration_time']) / 1000,
                gain=int(values['isp_ae_gain']) / 1024)


def zoom_geometry(width, height, magnification, hfov_rad=None):
    """Ideal centred even NV12 ROI, NOT a hardware-supported zoom range claim."""
    if any(type(v) is not int or v < 2 or v % 2 for v in (width, height)):
        raise ValueError('even sensor dimensions required')
    if type(magnification) not in (int, float) or not math.isfinite(magnification) or magnification < 1:
        raise ValueError('finite magnification >= 1 required')
    w, h = int(width / magnification) // 2 * 2, int(height / magnification) // 2 * 2
    if min(w, h) < 2:
        raise ValueError('empty ROI')
    out = dict(x=(width-w)//4*2, y=(height-h)//4*2, width=w, height=h,
               scale_x=width/w, scale_y=height/h)
    if hfov_rad is not None:
        if not math.isfinite(hfov_rad) or not 0 < hfov_rad < math.pi:
            raise ValueError('pinhole HFOV required')
        out['hfov_rad'] = 2 * math.atan(math.tan(hfov_rad/2) * w/width)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--sample-seconds', type=float, default=0)
    args = parser.parse_args()
    if not math.isfinite(args.sample_seconds) or not 0 <= args.sample_seconds <= 60:
        parser.error('sample duration must be 0..60 seconds')
    report = Audit(args.root).collect()
    if args.root.resolve() == Path('/'):
        report['board'] = dict(uname=list(__import__('os').uname()),
                              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        try:
            result = subprocess.run(['v4l2-ctl', '-d', '/dev/video0',
                '--get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain'],
                capture_output=True, text=True, check=True, timeout=4)
            report['runtime_controls'] = parse_controls(result.stdout)
        except (OSError, subprocess.SubprocessError, KeyError, ValueError) as error:
            report['runtime_controls'] = dict(error=str(error))
        samples = []
        end = time.monotonic() + args.sample_seconds
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8099/api/state', timeout=.5) as response:
                    raw = response.read(512*1024+1)
                if len(raw) > 512*1024:
                    raise ValueError('oversize state')
                snap = json.loads(raw)
                now = time.monotonic()*1000
                samples.append(dict(sequence=snap['sequence'], stream_id=snap['stream_id'],
                    age_ms=now-snap['capture_monotonic_ms'], source_id=snap['source_id'],
                    clock_domain=snap['clock_domain'], frame=snap['frame'],
                    lock_state=snap['lock']['state'], control_valid=snap['lock']['control_valid']))
            except (OSError, ValueError, KeyError) as error:
                samples.append(dict(error=str(error)))
            time.sleep(.1)
        report['runtime_samples'] = samples
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
