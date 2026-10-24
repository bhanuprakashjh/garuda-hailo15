"""Version and resource snapshot for the explicitly scoped board ROS bench."""
import hashlib
import gzip
import json
import pathlib
import subprocess


def json_lines(path):
    if path.exists():raw=path.read_bytes()
    else:raw=gzip.decompress(path.with_suffix(path.suffix+'.gz').read_bytes())
    return [json.loads(line) for line in raw.splitlines()]


def snapshot(root):
    files=[]
    for pattern in ('bench/sim/*.py','bench/sim/*.cpp','bench/sim/*.html','bench/sim/*.js','bench/sim/*.sdf',
                    'hosts/hailo15l/ros2/*','services/garuda-follow/*.py',
                    'services/garuda-bridge/*.py','interfaces/garuda_interfaces/*.py'):
        files.extend(p for p in root.glob(pattern) if p.is_file())
    return dict(source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        git_status=subprocess.check_output(['git','status','--short'],cwd=root,text=True),
        board=subprocess.check_output(['ssh','-oBatchMode=yes','-oConnectTimeout=5','root@10.0.0.1',
            'uname -a; free -m; df -h /opt/garuda-ros-jazzy; '
            'cat /sys/class/thermal/thermal_zone*/temp; '
            'sha256sum /opt/garuda-ros-jazzy/opt/garuda/*.py /opt/garuda-ros-jazzy/opt/garuda/*.yaml '
            '/opt/garuda-ros-jazzy/opt/garuda/*.sh /opt/garuda-ros-jazzy/usr/share/keyrings/ros-archive-keyring.gpg; '
            'chroot /opt/garuda-ros-jazzy dpkg-query -W'],text=True,timeout=20))
