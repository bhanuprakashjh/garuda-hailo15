"""CPU-only replay on the board, streamed pixels, no camera/service changes.

Stages one executable/config in a unique directory; no recordings on eMMC.
The existing live binary/config are hash-guarded before and after the probe.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import urllib.request

EXPECTED_NODE='0ad699771eb5e1c7fa4b73d373f1be0cc9f5685019ae86724d7f5142c5855124'
EXPECTED_CONFIG='26d38d7c7681aaaf67303af08b9e1f636a6e3e8c8940cc14019478f253716175'


def ssh(command):
    return subprocess.check_output(['ssh','-o','ConnectTimeout=5','root@10.0.0.1',command],text=True,timeout=15).strip()


def snapshot():
    with urllib.request.urlopen('http://10.0.0.1:8099/api/state',timeout=5) as f:state=json.load(f)
    hashes=ssh('sha256sum /opt/garuda-fresh/garuda-fresh-tracking /opt/garuda-fresh/current.json').splitlines()
    return dict(node_sha256=hashes[0].split()[0],config_sha256=hashes[1].split()[0],
        sequence=state['sequence'],stream_id=state['stream_id'],capture=state['diag']['capture_stream'],
        memory=ssh('head -3 /proc/meminfo'),disk=ssh('df -k /opt/garuda-fresh'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    before=snapshot()
    if before['node_sha256']!=EXPECTED_NODE or before['config_sha256']!=EXPECTED_CONFIG or before['capture']['active']:
        raise ValueError('live baseline/recording guard')
    memory=int(re.search(r'MemAvailable:\s+(\d+)',before['memory']).group(1))
    if memory<256*1024:raise ValueError('insufficient memory')
    if int(before['disk'].splitlines()[-1].split()[3])<128*1024:raise ValueError('insufficient disk')
    a.out.mkdir(parents=True,exist_ok=False)
    stage=ssh('mktemp -d /opt/garuda-fresh/visual-cpu-probe.XXXXXX')
    if not re.fullmatch('/opt/garuda-fresh/visual-cpu-probe.[A-Za-z0-9]{6}',stage):raise ValueError('unexpected stage')
    files=[a.binary,a.campaign/'tracking.json']
    subprocess.run(['scp','-q',*map(str,files),'root@10.0.0.1:'+stage+'/'],check=True,timeout=30)
    hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for name,digest in hashes.items():
        if ssh('sha256sum '+stage+'/'+name).split()[0]!=digest:raise ValueError('staging hash failure')
    report=dict(before=before,stage=stage,staged_sha256=hashes,scope='CPU-only recorded replay alongside unchanged live pipeline; not live-camera integration timing')
    outputs=[]
    try:
        with (a.out/'stderr.log').open('wb') as err:
            proc=subprocess.Popen(['ssh','root@10.0.0.1','timeout 60 nice -n 19 '+stage+'/'+a.binary.name+' '+stage+'/tracking.json candidate'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
            def drain():
                for line in proc.stdout:outputs.append(line)
            reader=threading.Thread(target=drain,daemon=True);reader.start()
            try:
                for line in (a.campaign/'inputs.jsonl').read_text().splitlines():
                    row=json.loads(line)
                    if 'pixels' in row:
                        raw=Path(row['pixels']).read_bytes()
                        if len(raw)!=1382400:raise ValueError('unexpected frame size')
                        row['pixels']='-'
                    else:raw=b''
                    proc.stdin.write(json.dumps(row).encode()+b'\n');proc.stdin.write(raw)
                proc.stdin.close();rc=proc.wait(timeout=70);reader.join(timeout=5)
                if rc:raise RuntimeError('probe failed: '+str(rc))
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
    finally:
        (a.out/'candidate.jsonl').write_bytes(b''.join(outputs))
        report['after']=snapshot();after=report['after']
        report['live_unchanged']=all(after[k]==before[k] for k in ('node_sha256','config_sha256','stream_id')) and after['sequence']>before['sequence']
        (a.out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['live_unchanged']:raise RuntimeError('live continuity check failed')
    rows=[json.loads(x) for x in outputs]
    if len(rows)!=181 or rows.pop(16)!={'ok':True}:raise ValueError('incomplete/failed selection')
    times=sorted(r['visual']['elapsed_ms']+r['visual']['seed_ms'] for r in rows[16:])
    result=dict(valid=sum(r['lock']['control_valid'] for r in rows[16:]),frames=len(times),
        visual_total_median_ms=times[len(times)//2],visual_total_p95_ms=times[int(.95*(len(times)-1))],
        live_unchanged=report['live_unchanged'])
    (a.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
