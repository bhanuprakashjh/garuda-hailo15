#!/usr/bin/env python3
"""Temporary 10 ms AE cap, board-side rollback, and concurrent HTTP telemetry.

Run only with the user ready for a supervised phone movement test. No persistent
camera profile is modified. Readback must demonstrate the requested shutter cap.
"""
import argparse
from pathlib import Path
import subprocess
import sys

REMOTE = r'''
import json, subprocess, time
base = ['v4l2-ctl', '-d', '/dev/video0']
def read():
    text = subprocess.check_output(base + ['--get-ctrl=isp_ae_enable,isp_ae_integration_time,isp_ae_gain,isp_ae_integration_time_limits'], text=True, timeout=3)
    values = {}
    for line in text.splitlines():
        key, value = line.split(':', 1)
        values[key.strip()] = [int(x) for x in value.split(',')]
    return values
def limit(value):
    subprocess.run(base + ['--subset=isp_ae_integration_time_limits,1,1', '--set-ctrl=isp_ae_integration_time_limits=' + str(value)], check=True, timeout=3)
before = read()
print(json.dumps({'event':'before','controls':before}), flush=True)
if before['isp_ae_enable'] != [1]:
    raise RuntimeError('Expected auto exposure enabled; nothing changed')
previous_max = before['isp_ae_integration_time_limits'][1]
if before['isp_ae_integration_time_limits'][0] > 10000:
    raise RuntimeError('Exposure minimum exceeds test cap; nothing changed')
started = time.monotonic()
try:
    limit(10000)
    for i in range(60):
        current = read()
        print(json.dumps({'event':'sample','elapsed_s':time.monotonic()-started,'controls':current}), flush=True)
        if i >= 4 and (current['isp_ae_enable'] != [1] or current['isp_ae_integration_time'][0] > 10500):
            raise RuntimeError('10 ms automatic-exposure cap did not take effect; aborting trial')
        time.sleep(.5)
finally:
    limit(previous_max)
    after = read()
    print(json.dumps({'event':'restored','controls':after}), flush=True)
    if after['isp_ae_integration_time_limits'] != before['isp_ae_integration_time_limits']:
        raise RuntimeError('Exposure limit restoration readback mismatch')
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'exposure.jsonl').open('w') as exposure, (args.output / 'exposure.stderr.log').open('w') as errors:
        remote = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'root@10.0.0.1', 'python3 -'], stdin=subprocess.PIPE, stdout=exposure, stderr=errors, text=True)
        remote.stdin.write(REMOTE)
        remote.stdin.close()
        try:
            telemetry = subprocess.run([sys.executable, str(Path(__file__).with_name('fresh_tracking_bench.py')), '--seconds', '35', '--output', str(args.output / 'tracking.jsonl')], timeout=45)
        finally:
            # Let board-side finally restore the cap, even if local telemetry fails.
            status = remote.wait(timeout=60)
    if status:
        print('Exposure trial failed; inspect exposure log and restoration readback.', file=sys.stderr)
    return status or telemetry.returncode

if __name__ == '__main__':
    raise SystemExit(main())
