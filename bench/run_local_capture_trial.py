"""Bounded on-board raw recording smoke test; never changes the camera profile.

Requires a running native camera with exact-source capture already enabled. Starts
a local receiver with nohup; SSH is only orchestration, not the pixel data path.
Preserves the new owned recording directory on eMMC, including failed prefixes.
No vehicle commands, model deployment, deletion, or boot/service installation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parent


def ssh(host, command, timeout=15):
    return subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                           host, command], text=True, capture_output=True, timeout=timeout, check=True).stdout.strip()


def remote_python(host, code, timeout=15):
    return ssh(host, 'python3 -c ' + shlex.quote(code), timeout)


def snapshot(host):
    return json.loads(remote_python(host, '''import hashlib,json,subprocess,shutil
from pathlib import Path
p=Path('/opt/garuda-fresh/current.json');cfg=json.loads(p.read_text())
def live(pattern):return subprocess.run(['pgrep','-f',pattern],capture_output=True).returncode==0
print(json.dumps(dict(node_sha256=hashlib.sha256(Path('/opt/garuda-fresh/garuda-fresh-tracking').read_bytes()).hexdigest(),
 config_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
 capture_stream_port=cfg.get('capture_stream_port'),capture_source=cfg.get('capture_source'),
 free_bytes=shutil.disk_usage(p.parent).free,
 native_running=live('^/opt/garuda-fresh/garuda-fresh-tracking '),
 replay_running=live('^/opt/garuda-sim/garuda-causal.'),
 mavros_running=live('(^|/)mavros_node( |$)'))))'''))


def validate_snapshot(state, frames):
    port = state['capture_stream_port']
    if not state['native_running'] or state['replay_running'] or state['mavros_running']:
        raise ValueError('requires live native camera, no replay and no MAVROS')
    if type(port) is not int or not 1024 <= port <= 65535 or state['capture_source'] is not True:
        raise ValueError('paired capture must already be enabled; profile not changed')
    if type(frames) is not int or not 1 <= frames <= 24:
        raise ValueError('short eMMC smoke test limited to 1..24 processed samples')
    if state['free_bytes'] < frames*(2*1024*1024+2*128*1024+65536)+512*1024*1024:
        raise ValueError('insufficient eMMC reserve')


def validate_remote(path):
    if not re.fullmatch(r'/opt/garuda-fresh/local-record\.[A-Za-z0-9]{6}', path):
        raise ValueError('unexpected owned staging directory')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@10.0.0.1')
    parser.add_argument('--frames', type=int, default=16)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = snapshot(args.host)
    validate_snapshot(before, args.frames)
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(before=before, scope='local raw recording integrity only; NOT tracking or flight qualification',
                  profile_modified=False, raw_data_deleted=False, requested_frames=args.frames)
    try:
        remote = validate_remote(ssh(args.host, 'mktemp -d /opt/garuda-fresh/local-record.XXXXXX'))
        result['remote_directory'] = remote
        scripts = [ROOT/'fresh_stream_capture.py', ROOT/'qualify_capture.py']
        result['script_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts}
        subprocess.run(['scp', '-q', *map(str, scripts), args.host+':'+remote+'/'], check=True, timeout=15)
        for name, expected in result['script_sha256'].items():
            actual = ssh(args.host, 'sha256sum '+shlex.quote(remote+'/'+name)).split()[0]
            if actual != expected:
                raise ValueError('staged script checksum mismatch')
        capture = remote+'/capture'
        command = (f'nohup python3 {remote}/fresh_stream_capture.py --local '
                   f'--port {before["capture_stream_port"]} --frames {args.frames} --deadline-ms 60000 '
                   f'--output {capture} >{remote}/capture.log 2>&1 </dev/null &')
        ssh(args.host, command)
        result['launch_ssh_returned_before_polling'] = True
        deadline = time.monotonic()+75
        while time.monotonic() < deadline:
            try:
                status = json.loads(remote_python(args.host, f'''import json
from pathlib import Path
p=Path({capture!r})
status={{}}
for name in ('summary.json','error.json'):
 try:status[name]=json.loads((p/name).read_text())
 except (FileNotFoundError,json.JSONDecodeError):pass
print(json.dumps(status))'''))
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
                # The recording is local and survives a temporary SSH loss.
                # Preserve the observation failure and retry only within the bound.
                result.setdefault('poll_errors',[]).append(str(error))
                time.sleep(2)
                continue
            if status.get('error.json'):
                raise ValueError('recorder failed: '+json.dumps(status['error.json']))
            if status.get('summary.json'):
                result['summary'] = status['summary.json']
                break
            time.sleep(2)
        else:
            raise TimeoutError('local recorder did not complete within bounded observation window; inspect retained directory')
        result['qualification'] = json.loads(ssh(args.host, f'python3 {remote}/qualify_capture.py {capture}', timeout=30))
        result['capture_log'] = remote_python(args.host, f'from pathlib import Path;print(Path({(remote+"/capture.log")!r}).read_text())')
        result['passed'] = result['qualification']['integrity_pass']
    except Exception as error:
        result['passed'] = False
        result['error'] = str(error)
        raise
    finally:
        try:
            result['after'] = snapshot(args.host)
            result['live_unchanged'] = all(before[k] == result['after'][k] for k in ('node_sha256', 'config_sha256'))
            if not result['live_unchanged'] or not result['after']['native_running']:
                result['passed'] = False
        except Exception as error:
            result['passed'] = False
            result['final_check_error'] = str(error)
        with (args.output/'run.json').open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
