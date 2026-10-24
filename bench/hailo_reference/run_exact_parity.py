"""Fresh physical-15L run on the retained exact DSP tensors and pinned model."""
import argparse
import json
import pathlib
import shutil
import subprocess
from run_causal_replay import ROOT, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('work',type=pathlib.Path)
    p.add_argument('--probe',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((a.work/'manifest.json').read_text())
    assert sha(a.work/'source.onnx')==manifest['onnx_sha256']
    assert sha(a.work/'test-inputs.nv12')==manifest['test_sha256']
    ssh=['ssh','-oBatchMode=yes','-oConnectTimeout=5','root@10.0.0.1']
    ctl=['bash',str(ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh')]
    if subprocess.run(ssh+['pgrep -f "^/opt/garuda-sim/garuda-causal-stream"'],stdout=subprocess.DEVNULL).returncode==0:
        raise RuntimeError('visual stream still owns NPU')
    running=subprocess.run(ssh+['pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking "'],stdout=subprocess.DEVNULL).returncode==0
    remote=subprocess.check_output(ssh+['mktemp -d /tmp/garuda-parity.XXXXXX'],text=True).strip()
    if not remote.startswith('/tmp/garuda-parity.') or any(c.isspace() for c in remote):
        raise ValueError('invalid remote directory')
    subprocess.run(['scp',str(a.probe),str(a.work/'test-inputs.nv12'),'root@10.0.0.1:'+remote+'/'],check=True)
    board_model=subprocess.check_output(ssh+['sha256sum /opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef'],text=True).split()[0]
    if board_model!=sha(a.work/'controlled.hef'):
        raise ValueError('board HEF is not the retained compiled model')
    evidence=dict(hef_sha256=board_model,onnx_sha256=manifest['onnx_sha256'],inputs_sha256=manifest['test_sha256'],
                  probe_sha256=sha(a.probe),remote=remote,was_running=running)
    try:
        if running: subprocess.run(ctl+['stop'],check=True)
        with (a.out/'letterbox.jsonl').open('xb') as out, (a.out/'board.log').open('xb') as err:
            subprocess.run(ssh+['LD_LIBRARY_PATH=/opt/garuda-fresh/lib '+remote+'/'+a.probe.name+
                ' /opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef '+remote+'/test-inputs.nv12 .05'],
                stdout=out,stderr=err,check=True,timeout=90)
    finally:
        if running: subprocess.run(ctl+['start-current'],check=True,timeout=40)
        (a.out/'run.json').write_text(json.dumps(evidence,indent=2))
    shutil.copyfile(a.work/'test-inputs.nv12',a.out/'network-inputs.nv12')
    shutil.copyfile(a.work/'regions.json',a.out/'regions.json')
    subprocess.run([str(pathlib.Path(__import__('sys').executable)),str(ROOT/'bench/hailo_reference/score_controlled_yolo11.py'),
                    str(a.work),str(a.out/'comparison.json'),'--device-replay',str(a.out)],check=True)


if __name__=='__main__': main()
