"""Stream long bench logs; retain scalar timing samples, not repeated snapshots."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def distribution(values):
    values=sorted(v for v in values if isinstance(v,(int,float)) and math.isfinite(v))
    return dict(n=len(values),median=statistics.median(values) if values else None,
                p95=values[round(.95*(len(values)-1))] if values else None)


def summarize(directory):
    requests={};reasons=Counter();board=[];roundtrip=[];first_report=[];queue=[];age=[]
    forwarded=expired=follow=holds=outside=0;final=None;states=Counter();last_source=None
    measured_deltas=[]
    with (directory/'mavros-events.jsonl').open() as stream:
        for line in stream:
            e=json.loads(line);now=e['host_ns'];kind=e.get('kind')
            if kind=='request':
                requests={k:v for k,v in requests.items() if now-v['host_ns']<1_000_000_000}
                requests[e['sequence']]=e
            elif kind=='setpoint':
                request=requests.get(e.get('request_sequence'))
                if request:
                    elapsed=(e['host_received_ns']-request['host_ns'])/1e6
                    roundtrip.append(elapsed)
                    if not request.get('reported'):first_report.append(elapsed);request['reported']=True
                if 'request_to_publish_ms' in e:board.append(e['request_to_publish_ms'])
            elif kind=='wire':
                if 'relay_queue_ms' in e:queue.append(e['relay_queue_ms'])
                if e['moving']:
                    reasons[e.get('reason','legacy_forwarded' if e['allowed'] else 'legacy_unspecified_rejection')]+=1
                    if e['allowed']:
                        forwarded+=1
                        expired+=not (now<e['deadline_ns'] and type(e.get('origin_deadline_ns')) is int and now<e['origin_deadline_ns'])
    with (directory/'ticks.jsonl').open() as stream:
        for line in stream:
            t=json.loads(line);final=t
            if not t.get('following') or t['flight']!='Hover / offboard':continue
            follow+=1;holds+=t['setpoint']['hover']
            s=t.get('source')
            if not s:continue
            out=s['output'];lock=out['lock'];states[lock['state']]+=1
            if s.get('live_camera'):age.append(s['age_ms']+(t['t_ns']-s['received_ns'])/1e6)
            b=lock.get('box')
            if b:outside+=b['x']<0 or b['y']<0 or b['x']+b['w']>1280.00001 or b['y']+b['h']>720.00001
            key=(out['stream_id'],out['sequence'])
            if key!=last_source:
                last_source=key
                for tr in out['tracks']:
                    filtered=tr.get('filtered_box')
                    if filtered and not tr['coasting']:
                        measured_deltas.append(max(abs(tr[k]-filtered[k]) for k in ('x','y','w','h')))
    return dict(scope='Observed bench log; unpaired runs do not establish a causal performance improvement',
                directory=str(directory),follow_ticks=follow,pc_hold_ticks=holds,lock_states=states,
                follow_box_outside_ticks=outside,follow_capture_age_ms=distribution(age),
                motion_forwarded=forwarded,expired_motion_forwarded=expired,motion_reasons=reasons,
                board_request_to_evaluation_ms=distribution(board),request_to_publication_report_ms=distribution(roundtrip),
                first_request_to_publication_report_ms=distribution(first_report),
                relay_queue_ms=distribution(queue),measured_filtered_max_coordinate_delta_px=distribution(measured_deltas),
                final_disarmed=bool(final) and not final['armed'],robust_following_qualified=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=summarize(args.directory)
    encoded=json.dumps(report,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:stream.write(encoded)
    print(encoded)
