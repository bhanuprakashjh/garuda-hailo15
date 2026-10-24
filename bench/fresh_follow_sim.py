#!/usr/bin/env python3
"""Closed loop: synthetic camera -> actual C++ fresh tracker -> SDK -> follow -> kinematics.

No detector, board timing, PX4 or vehicle is simulated as measured hardware.
"""
import argparse
import json
import math
import pathlib
import selectors
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/garuda-follow"))
from fresh_follow import FreshFollow
from fresh_target_adapter import from_fresh
from follow_controller import FollowConfig
from sim_kinematics import DroneState, step
from projection import project


class Replay:
    def __init__(self, binary):
        self.process = subprocess.Popen([str(binary), "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def send(self, row):
        self.process.stdin.write(json.dumps(row)+"\n");self.process.stdin.flush()
        if not self.selector.select(5):
            raise RuntimeError("tracker replay response timeout")
        return json.loads(self.process.stdout.readline())

    def close(self):
        self.selector.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.wait()
        self.process.stdout.close()
        if self.process.returncode:
            raise RuntimeError("tracker replay failed")


def run(binary, label="person", framing_translation=True):
    replay = Replay(binary)
    rows = []
    cfg = FollowConfig(desired_height_frac=.4)
    follow = FreshFollow("synthetic.camera", "sim-run-1", 1, config=cfg, framing_translation=framing_translation)
    state = DroneState(0,0,0,0)
    try:
        replay.send({"cmd":"target","class":label,"now_ms":999})
        for tick in range(500):
            source_ms = 1000+tick*50
            local_ns = (9_000_000+tick*50)*1_000_000  # deliberately unrelated clock
            box = project((6,2), (state.x,state.y), state.yaw)
            detections = [] if box is None else [dict(label=label,confidence=.9,box=dict(zip(('x','y','w','h'),box)))]
            phase = "tracking"
            if 100 <= tick < 116:
                phase = "occluded";detections=[]
            elif 160 <= tick < 176:
                phase = "frozen_transport"
            elif 220 <= tick < 226:
                phase = "slow_transport"
            elif 280 <= tick < 290:
                phase = "ambiguous"
                if detections:
                    d = json.loads(json.dumps(detections[0]))
                    detections[0]['box']['x'] -= .04;d['box']['x'] += .04;detections.append(d)
            elif 350 <= tick < 365:
                phase = "changed_selection"
            if tick == 350:
                replay.send({"cmd":"target","class":label,"now_ms":source_ms-1})
            result = replay.send(dict(sequence=tick+1,capture_ms=source_ms,now_ms=source_ms+10,
                                      timestamp_valid=True,detections=detections))
            if tick == 365:
                # Explicit test-harness rebind after a new selection. Not automatic behavior.
                follow = FreshFollow("synthetic.camera","sim-run-1",result['lock']['epoch'],
                                     config=cfg,framing_translation=framing_translation)
            if phase != "frozen_transport":
                result.update(source_id="synthetic.camera",stream_id="sim-run-1",clock_domain="synthetic.boot-1",
                              sample_monotonic_ms=source_ms+10,freshness_budget_ms=200,
                              valid_for_ms=max(0,200-result['lock']['obs_age_ms']))
                rtt = 250_000_000 if phase == "slow_transport" else 5_000_000
                follow.ingest(from_fresh(result),local_ns-rtt,local_ns)
            decision = follow.tick(local_ns)
            state = step(state,decision.command,.05)
            error = abs(box[0]+box[2]/2-.5)+abs(cfg.desired_height_frac-box[3]) if box else None
            rows.append(dict(tick=tick,phase=phase,framing_error=error,source_state=result['lock']['state'],
                             **decision.to_dict(),pose=dict(x=state.x,y=state.y,z=state.z,yaw=state.yaw)))
    finally:
        replay.close()
    faults = {}
    for phase in ("occluded","frozen_transport","slow_transport","ambiguous","changed_selection"):
        selected = [r for r in rows if r['phase']==phase]
        # A frozen transport may retain a still-fresh observation up to its lease.
        required = selected[4:] if phase == 'frozen_transport' else selected
        faults[phase] = dict(ticks=len(selected),valid_ticks=sum(r['command']['valid'] for r in selected),
                             hold_after_deadline=all(not r['command']['valid'] and
                                all(r['command'][k]==0 for k in ('yaw_rate','forward_vel','vertical_vel')) for r in required))
    summary = dict(scope="synthetic camera + actual C++ tracker + SDK + Python follow + kinematics; no hardware/PX4 accuracy claim",
                   label=label,framing_translation=framing_translation,ticks=len(rows),
                   initial_framing_error=rows[0]['framing_error'],final_framing_error=rows[-1]['framing_error'],
                   faults=faults,final_pose=rows[-1]['pose'],range_estimated=False)
    if not all(f['hold_after_deadline'] for f in faults.values()):
        raise AssertionError(json.dumps(summary))
    if framing_translation and not summary['final_framing_error'] < .08:
        raise AssertionError('closed loop did not converge: '+json.dumps(summary))
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-bin',type=pathlib.Path,required=True)
    parser.add_argument('--label',choices=('person','cell phone'),default='person')
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args = parser.parse_args()
    summary,rows = run(args.replay_bin,args.label)
    with args.output.open('x') as file:
        for row in rows:file.write(json.dumps(row,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
