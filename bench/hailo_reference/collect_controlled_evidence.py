"""Archive compact build evidence; retain large weights, calibration and private inputs locally."""
import argparse
import gzip
import hashlib
import json
import pathlib
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('work',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
artifacts=[]
for path in sorted(a.work.iterdir()):
    if not path.is_file():
        continue
    if path.suffix not in ('.json','.log','.alls','.npy','.hef','.har','.onnx','.nv12'):
        continue
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    local_only=path.suffix in ('.hef','.har','.onnx','.nv12') or path.name=='calibration.npy'
    entry=dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=h.hexdigest(),local_only=local_only)
    if not local_only:
        if path.suffix=='.npy':
            dest=a.output/(path.name+'.gz')
            with path.open('rb') as source, gzip.open(dest,'wb') as target:
                shutil.copyfileobj(source,target)
        else:
            dest=a.output/path.name
            shutil.copyfile(path,dest)
        entry['archived_as']=dest.name
    artifacts.append(entry)
(a.output/'artifacts.json').write_text(json.dumps(artifacts,indent=2))
print(f'Archived evidence for {len(artifacts)} artifacts')
