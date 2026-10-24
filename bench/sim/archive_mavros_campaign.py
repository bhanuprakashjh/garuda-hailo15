"""Archive bounded text evidence, excluding pixels, rootfs, models and PX4 binaries."""
import argparse
import gzip
import hashlib
import json
import pathlib


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=pathlib.Path);p.add_argument('out',type=pathlib.Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    manifest=[]
    directories=['axis-normal','axis-request-loss','axis-ros-loss','ros-visual-first',
        'ros-visual-second','ros-visual-third','ros-visual-final','ros-visual-fullview',
        'ros-visual-qualified-repeat','ros-replay-car','ros-replay-car-fullview','exact-parity','schedules','validation']
    for name in directories:
        directory=a.source/name
        if not directory.exists():continue
        paths=directory.rglob('*') if name=='schedules' else directory.iterdir()
        for src in sorted(paths):
            if not src.is_file() or src.suffix not in ('.json','.jsonl','.log'):continue
            relative=src.relative_to(a.source);dest=a.out/relative;raw=src.read_bytes()
            dest.parent.mkdir(parents=True,exist_ok=True)
            if src.suffix in ('.jsonl','.log'):
                dest=dest.with_suffix(dest.suffix+'.gz');dest.write_bytes(gzip.compress(raw,mtime=0))
            else:dest.write_bytes(raw)
            manifest.append(dict(source=str(relative),stored=str(dest.relative_to(a.out)),
                raw_sha256=hashlib.sha256(raw).hexdigest(),stored_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    (a.out/'manifest.json').write_text(json.dumps(dict(scope=__doc__,files=manifest),indent=2)+'\n')
    print(f'Archived {len(manifest)} text artifacts')


if __name__=='__main__':main()
