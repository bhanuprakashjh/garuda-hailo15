"""Assert recorded PX4 SIL outcomes; no vehicle I/O and no inferred camera accuracy."""
import argparse
import json
import math
import pathlib

SCENARIOS=('nominal','target_loss','video_stall','abort','publish_failure','link_loss')


def verify_board(folder):
    data=json.loads((folder/'nominal.json').read_text())
    s=data['summary'];rows=[r for r in data['rows'] if r['phase']=='follow']
    assert s['perception']=='board' and s['execution']=='live'
    assert s['offboard_seen'] and s['armed_seen'] and s['landing']['armed_end'] is False
    assert s['states'].get('ACTIVE',0)>0 and rows
    assert all(r['vn']==r['ve']==0 and abs(r['yaw_rate'])<=.8 for r in rows)
    assert all(r['hover'] and r['yaw_rate']==0 for r in rows if not r['eligible'])
    return dict(pass_=True,active=s['states']['ACTIVE'],ticks=len(rows),zero_translation=True,
        expired_ticks_hover=True,disarmed=True,
        scope='real camera envelopes to yaw-only PX4 SIH; not rendered visual feedback')


def verify(folder):
    checks={}
    for name in SCENARIOS:
        data=json.loads((folder/f'{name}.json').read_text())
        s,rows=data['summary'],data['rows']
        assert s['execution']=='live' and s['perception']=='tracker',name
        assert s['offboard_seen'] and s['armed_seen'],name
        assert s['landing']['armed_end'] is False,(name,'not disarmed')
        follow=[r for r in rows if r['phase']=='follow']
        assert follow and s['states'].get('ACTIVE',0)>0,(name,'never active')
        for r in follow:
            assert all(math.isfinite(r[k]) for k in ('vn','ve','yaw_rate','d'))
            assert math.hypot(r['vn'],r['ve'])<=2.002 and abs(r['yaw_rate'])<=.8
            if not r['eligible']:
                assert r['hover'] and r['vn']==r['ve']==r['yaw_rate']==0,(name,'stale motion',r)
        def window(start,end):
            found=[r for r in follow if start<=r['t']-follow[0]['t']<end]
            assert found,(name,'missing fault window')
            return found
        if name in ('target_loss','video_stall'):
            # Fault starts at 15 s; allow the documented 200 ms observation TTL
            # plus one 50 ms publisher tick before requiring zero commands.
            end=18 if name=='target_loss' else 17
            assert all(not r['eligible'] and r['hover'] for r in window(15.3,end)),name
            assert any(r['eligible'] for r in window(21,30)),(name,'no recovery')
        if name=='abort':
            assert all(not r['eligible'] for r in window(15.05,19.95))
            assert any(r['eligible'] for r in window(20.1,30))
        if name=='publish_failure':
            assert 15<=s['breaker_tripped_at_s']<=15.35
            assert s['landing']['mode_auto_seen']
        if name=='link_loss':
            assert s['offboard_loss_without_land'] is True
            assert any(r['mode']!=6 for r in window(17,25))
        checks[name]=dict(pass_=True,active_ticks=s['states'].get('ACTIVE',0),disarmed=True)
    return dict(scope='PX4 SIH + actual C++ tracker with synthetic detections; not YOLO or real-flight validation',checks=checks)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=pathlib.Path)
    p.add_argument('--board',action='store_true',help='verify a yaw-only live-camera nominal run')
    a=p.parse_args()
    report=verify_board(a.folder) if a.board else verify(a.folder)
    (a.folder/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
