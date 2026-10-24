"""Capture r2 encoded video and metadata without changing camera/tracker settings.

Start only when the user is ready. Hold still for the first five seconds after
the START message (codec pre-roll), then perform the agreed movement sequence.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('stage',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
known='/media/bhanu1234/Development/GARUDASDK/.local/board-backups/20260911-stock-baseline/known_hosts-stock'
opts=['-o','BatchMode=yes','-o','ConnectTimeout=5','-o','UserKnownHostsFile='+known]
ssh=['ssh',*opts,'root@10.0.0.1']
def remote(cmd):
    return subprocess.run(ssh+[cmd],check=True,capture_output=True,text=True,timeout=10).stdout
log=remote('cat /tmp/garuda-experiment-r2.log')
before=[line.split()[-1] for line in log.splitlines() if line.startswith('GARUDA_RECORD_STARTED ')]
if len(before)>=2:raise RuntimeError('Two-capture process budget exhausted; restart verified r2 first.')
remote('test ! -e /tmp/garuda-r2-record.request')
a.output.mkdir(parents=True,exist_ok=False)
capture=pathlib.Path(__file__).resolve().parents[1]/'hailo_metadata_capture.py'
with (a.output/'metadata-capture.log').open('x') as capture_log:
    process=subprocess.Popen([sys.executable,str(capture),str(a.stage),str(a.output/'metadata.jsonl'),
                              '--seconds','45'],stdout=capture_log,stderr=subprocess.STDOUT)
    try:
        time.sleep(1)
        if process.poll() is not None:raise RuntimeError('Metadata capture failed before recording request')
        remote('touch /tmp/garuda-r2-record.request')
        folder=None
        for _ in range(10):
            lines=remote('tail -200 /tmp/garuda-experiment-r2.log').splitlines()
            started=[l.split()[-1] for l in lines if l.startswith('GARUDA_RECORD_STARTED ')]
            fresh=[s for s in started if s not in before]
            if fresh:folder=fresh[-1];break
            time.sleep(1)
        if folder is None:raise RuntimeError('Recorder did not acknowledge the request')
        if not folder.startswith('/tmp/garuda-r2-record.') or not folder.replace('/','').replace('-','').replace('.','').isalnum():
            raise RuntimeError('Unexpected recording directory')
        print('START: hold still for five seconds, then perform the agreed movement sequence.',flush=True)
        process.wait(timeout=55)
        if process.returncode:raise RuntimeError('Metadata capture failed')
        subprocess.run(['scp','-r',*opts,'root@10.0.0.1:'+folder,str(a.output)],check=True,timeout=60)
        report=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('verify_recording.py')),
            str(a.output/pathlib.Path(folder).name),str(a.output/'metadata.jsonl')],check=True,capture_output=True,text=True)
        (a.output/'verification.json').write_text(report.stdout)
        print(report.stdout)
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=5)
