"""Readiness means advancing native snapshots, not merely a launched PID/shim."""
import argparse
import json
import math
import time
import urllib.request


def sample_key(row):
    if not isinstance(row,dict):return None
    age=row.get('age_ms')
    if (row.get('source_id')!='hailo15l.imx678' or not row.get('stream_id')
            or row.get('frame')!=dict(width=1280,height=720)
            or row.get('timestamp_valid') is not True
            or type(row.get('sequence')) is not int
            or row['sequence'] < 0
            or type(age) not in (int,float) or not math.isfinite(age) or not 0 <= age < 1000):
        return None
    return row['stream_id'],row['sequence']


def wait_ready(fetch,timeout=20,clock=time.monotonic,sleep=time.sleep):
    deadline=clock()+timeout
    previous=None
    while clock()<deadline:
        try:
            row=fetch();key=sample_key(row)
            if key and previous and key[0]==previous[0] and key[1]>previous[1]:return row
            previous=key
        except (OSError,ValueError,TypeError):previous=None
        sleep(.2)
    raise TimeoutError('camera did not produce advancing native snapshots; inspect /tmp/garuda-fresh.log')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='10.0.0.1')
    a=p.parse_args()
    if not a.host or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in a.host):
        raise ValueError('plain camera hostname/IP required')
    def fetch():
        with urllib.request.urlopen('http://'+a.host+':8099/api/state',timeout=.5) as response:
            raw=response.read(512*1024+1)
        if len(raw)>512*1024:raise ValueError('oversize camera snapshot')
        return json.loads(raw)
    row=wait_ready(fetch)
    print(json.dumps(dict(camera_ready=True,stream_id=row['stream_id'],sequence=row['sequence'],age_ms=row['age_ms'])))


if __name__=='__main__':main()
