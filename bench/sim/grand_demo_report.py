"""Report actual demo evidence without equating transport with visual following."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
from mavros_evidence import json_lines


def summarize(directory):
    ticks=json_lines(directory/'ticks.jsonl')
    events=json_lines(directory/'mavros-events.jsonl')
    wire=[e for e in events if e.get('kind')=='wire' and e['allowed']]
    moving=[e for e in wire if e['moving']]
    native=[e for e in events if e.get('kind')=='native_camera']
    sources={}
    for t in ticks:
        s=t.get('source')
        if s:
            out=s['output'];sources[(out['source_id'],out['stream_id'],out['sequence'])]=s
    def distribution(values):
        values=sorted(values)
        return dict(median=statistics.median(values) if values else None,
                    p95=values[round((len(values)-1)*.95)] if values else None)
    checks=dict(source_frames=bool(sources),actual_mavros_wire=bool(wire),
        hover_observed=any(t['flight']=='Hover / offboard' and t['armed'] for t in ticks),
        final_disarmed=bool(ticks) and not ticks[-1]['armed'],
        no_expired_forwarded_motion=all(e['host_ns']<e['deadline_ns'] and
            type(e.get('origin_deadline_ns')) is int and e['host_ns']<e['origin_deadline_ns'] for e in moving),
        no_emergency_direct_land=not any(e.get('kind')=='emergency_direct_land' for e in events))
    physical=any(s.get('live_camera') for s in sources.values())
    followed=[t for t in ticks if t.get('following') and t['flight']=='Hover / offboard']
    headings=[]
    for t in followed:
        if not headings:headings.append(t['yaw'])
        else:headings.append(headings[-1]+math.atan2(math.sin(t['yaw']-headings[-1]),math.cos(t['yaw']-headings[-1])))
    heading_span=math.degrees(max(headings)-min(headings)) if headings else 0.
    displacement=max((math.hypot(t['position_ned'][0]-followed[0]['position_ned'][0],
                                  t['position_ned'][1]-followed[0]['position_ned'][1]) for t in followed),default=0.)
    if physical:
        checks['actual_native_ros_input']=any(e.get('ros_received',0)>0 for e in native)
        checks['no_physical_camera_translation']=all(abs(e['vn'])<1e-6 and abs(e['ve'])<1e-6 for e in wire)
    return dict(scope='Bench simulator transport and visible response; NOT flight qualification',
        physical_camera=physical,checks=checks,transport_demo_pass=all(checks.values()),
        report_version=2, motion_forwarded=bool(moving),
        visual_response_observed=bool(moving) and (heading_span>.5 or displacement>.1),
        response_diagnostic_thresholds=dict(heading_span_deg=.5,displacement_m=.1),
        actual_follow_heading_span_deg=heading_span,actual_follow_displacement_m=displacement,
        robust_following_qualified=False,
        ticks=len(ticks),unique_inference_frames=len(sources),forwarded_packets=len(wire),
        forwarded_motion_packets=len(moving),rejected_motion_packets=sum(e.get('kind')=='wire' and e['moving'] and not e['allowed'] for e in events),
        native_ros_messages=max((e.get('ros_received',0) for e in native),default=0),
        source_age_field_ms=distribution(s['age_ms'] for s in sources.values()),
        source_age_scope='native capture age plus HTTP roundtrip' if physical else 'board processing only; not ingress age',
        ingress_roundtrip_ms=distribution(s['roundtrip_ms'] for s in sources.values() if 'roundtrip_ms' in s),
        limits=['No independent wrong-person ground truth in live camera test',
                'No target motion means visual following is untested, not passed',
                'Display zoom is not native-4K detector zoom; relative size is not safe metric range'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    report=summarize(args.directory)
    with (args.directory/'grand-demo-report.json').open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    if args.archive:
        args.archive.mkdir(parents=True,exist_ok=False)
        manifest={}
        for source in sorted(args.directory.iterdir()):
            if not source.is_file() or source.suffix not in ('.json','.jsonl','.log'):
                continue
            raw=source.read_bytes()
            target=args.archive/(source.name+'.gz' if source.suffix in ('.jsonl','.log') else source.name)
            encoded=gzip.compress(raw,mtime=0) if target.suffix=='.gz' else raw
            with target.open('xb') as stream:stream.write(encoded)
            manifest[target.name]=dict(sha256=hashlib.sha256(encoded).hexdigest(),
                                       uncompressed_sha256=hashlib.sha256(raw).hexdigest())
        (args.archive/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
