#!/usr/bin/env python3
"""Read-only board snapshot. Archives deployed bytes, not a reproducible-build claim."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
from datetime import datetime, timezone


def digest(data):
    return hashlib.sha256(data).hexdigest()


def remote(host, command):
    return subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                                    host, command], timeout=120)


def allowed(path):
    p = PurePosixPath(path)
    if '..' in p.parts or not (path.startswith('/opt/garuda-fresh/') or
                              path.startswith('/usr/lib/hailo-post-processes/')):
        raise ValueError('unexpected artifact path: ' + path)
    return path


def verify(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest.get('schema') != 'garuda.deployed-baseline.v1' or not manifest.get('files'):
        raise ValueError('invalid baseline manifest')
    for entry in manifest['files']:
        path = (root/entry['local']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('missing or escaping artifact')
        if path.stat().st_size != entry['bytes'] or digest(path.read_bytes()) != entry['sha256']:
            raise ValueError('baseline artifact mismatch: ' + entry['local'])
    return manifest


def freeze(host, output, expected):
    output.mkdir(parents=True, exist_ok=False)
    base = '/opt/garuda-fresh/'
    config_bytes = remote(host, 'cat ' + base + 'current.json')
    config = json.loads(config_bytes)
    paths = {base + name for name in ('garuda-fresh-tracking', 'current.json',
              'perception-follow.json', 'fresh_shim.py', 'lib/libturbojpeg.so.0')}
    for key in ('medialib_config', 'postprocess_config', 'postprocess_so', 'hef',
                'target_roi_hef', 'person_reid_hef'):
        if config.get(key):
            paths.add(allowed(config[key]))
    files = []
    for path in sorted(paths):
        quoted = shlex.quote(allowed(path))
        before = remote(host, 'sha256sum ' + quoted).decode().split()[0]
        data = remote(host, 'cat ' + quoted)
        after = remote(host, 'sha256sum ' + quoted).decode().split()[0]
        sha = digest(data)
        if before != sha or after != sha:
            raise ValueError('artifact changed during snapshot: ' + path)
        if path == base+'garuda-fresh-tracking' and sha != expected:
            raise ValueError('deployed binary is not the accepted baseline')
        local = 'files/' + path.lstrip('/')
        destination = output/local
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        files.append(dict(remote=path, local=local, bytes=len(data), sha256=sha))
    if remote(host, 'cat ' + base+'current.json') != config_bytes:
        raise ValueError('active profile changed during snapshot')
    if (output/'files/opt/garuda-fresh/current.json').read_bytes() != config_bytes:
        raise ValueError('active profile was not captured consistently')
    readbacks = remote(host, 'uname -a; cat /proc/sys/kernel/random/boot_id; '
                       'v4l2-ctl -d /dev/video0 --get-ctrl=isp_ae_enable,isp_3dnr_enable,isp_3dnr_mode,isp_3dnr_strength')
    (output/'readbacks.txt').write_bytes(readbacks)
    files.append(dict(local='readbacks.txt', bytes=len(readbacks), sha256=digest(readbacks)))
    manifest = dict(schema='garuda.deployed-baseline.v1', host=host,
                    utc=datetime.now(timezone.utc).isoformat(), files=files,
                    scope='deployed application artifacts; system BSP/runtime not archived',
                    source_build_provenance='not established; working tree contains later experiments',
                    isp='observed dynamic readbacks, not a restorable ISP calibration')
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    verify(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    capture = sub.add_parser('freeze')
    capture.add_argument('--host', default='root@10.0.0.1')
    capture.add_argument('--output', type=Path, required=True)
    capture.add_argument('--expected-binary', required=True)
    check = sub.add_parser('verify')
    check.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = (freeze(args.host, args.output, args.expected_binary) if args.action == 'freeze'
              else verify(args.directory))
    print(json.dumps(dict(verified=True, files=len(result['files']), scope=result['scope'])))


if __name__ == '__main__':
    main()
