#!/usr/bin/env python3
"""Read-only platform sampling over SSH; all samples are written on the PC."""
import argparse
from datetime import datetime, timezone
import json
import pathlib
import subprocess
import time

REMOTE = r'''
import json,pathlib,os
def fields(path):
    return {line.split(':')[0]:line.split(':',1)[1].strip() for line in pathlib.Path(path).read_text().splitlines() if ':' in line}
mem=fields('/proc/meminfo')
pid=int(pathlib.Path('/tmp/garuda-fresh.pid').read_text())
status=fields('/proc/%d/status'%pid)
stat=pathlib.Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()
disk=os.statvfs('/tmp')
print(json.dumps(dict(pid=pid,uptime_s=float(pathlib.Path('/proc/uptime').read_text().split()[0]),
    memory_kib={k:int(mem[k].split()[0]) for k in ('MemAvailable','CmaFree','Shmem','Dirty','Writeback')},
    process_kib={k:int(status[k].split()[0]) for k in ('VmRSS','VmSize')},
    process_cpu_s=(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK'),
    thermal_millidegrees={p.parent.name:int(p.read_text()) for p in pathlib.Path('/sys/class/thermal').glob('thermal_zone*/temp')},
    frequency_khz={p.parent.parent.name:int(p.read_text()) for p in pathlib.Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_cur_freq')},
    tmp_available_bytes=disk.f_bavail*disk.f_frsize)))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='root@10.0.0.1')
    parser.add_argument('--seconds',type=float,default=600)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:parser.error('seconds must be in (0,3600]')
    start = time.monotonic()
    with args.output.open('x') as output:
        while time.monotonic()-start < args.seconds:
            tick = time.monotonic()
            row = dict(elapsed_s=tick-start,utc=datetime.now(timezone.utc).isoformat())
            try:
                result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=3',args.host,'python3','-'],
                                        input=REMOTE,text=True,capture_output=True,timeout=5,check=True)
                row['sample']=json.loads(result.stdout)
            except (OSError,ValueError,subprocess.SubprocessError) as error:
                row['error']=str(error)
            output.write(json.dumps(row)+'\n');output.flush()
            time.sleep(max(0,min(5-(time.monotonic()-tick),args.seconds-(time.monotonic()-start))))


if __name__ == '__main__':main()
