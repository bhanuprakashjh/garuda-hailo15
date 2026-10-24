"""Coordinate the existing controlled DFC recipe without installing/deploying anything."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('work',type=Path)
    p.add_argument('--calibration-root',type=Path,required=True)
    a=p.parse_args();work=a.work.resolve()
    parity=json.loads((work/'export-parity.json').read_text())
    if not parity['passed'] or parity['unverified_parameters']:
        raise ValueError('unverified weights/export')
    candidate=next(x for x in parity['exports'] if (x['width'],x['height'])==(1024,576))
    model=Path(candidate['path']);digest=hashlib.sha256(model.read_bytes()).hexdigest()
    if digest!=candidate['sha256']:raise ValueError('candidate changed')
    inputs=work/'dsp-inputs'
    run=json.loads((inputs/'run.json').read_text())
    if not run['live_unchanged'] or run['restore_returncode'] or run['crop_returncode']:
        raise ValueError('DSP inputs/restoration failed')
    raw=inputs/'network.nv12'
    if raw.stat().st_size!=31*1024*576*3//2 or hashlib.sha256(raw.read_bytes()).hexdigest()!=run['network_sha256']:
        raise ValueError('wrong held-out DSP pixels')
    if (work/'manifest.json').exists():raise ValueError('refusing to overwrite a prepared trial')
    shutil.copyfile(raw,inputs/'network-inputs.nv12')
    builder=Path(__file__).with_name('build_controlled_yolo11.py').resolve()
    stages=[]
    env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2')
    # Use the already installed nvcc support if present (same existing DFC env).
    for stage in ('prepare','parse','quantize','compile'):
        cmd=[sys.executable,str(builder),stage,str(work),'--input-size','1024','576','--model-sha',digest]
        if stage=='prepare':
            cmd+=['--model',str(model),'--test-replay',str(inputs),'--calibration-root',str(a.calibration_root.resolve())]
        start=time.time()
        print(json.dumps(dict(stage=stage,status='starting')),flush=True)
        with (work/(stage+'.log')).open('x') as log:
            try:
                result=subprocess.run(cmd,env=env,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=5400)
                entry=dict(stage=stage,returncode=result.returncode,elapsed_seconds=time.time()-start,command=cmd)
            except subprocess.TimeoutExpired:
                entry=dict(stage=stage,returncode=None,timeout=True,elapsed_seconds=time.time()-start,command=cmd)
        stages.append(entry)
        (work/'build-stages.json').write_text(json.dumps(stages,indent=2)+'\n')
        print(json.dumps(entry),flush=True)
        if entry['returncode']!=0:raise RuntimeError('stage failed: '+stage)


if __name__=='__main__':main()
