import json, os, signal, time, urllib.request
def state():
    with urllib.request.urlopen("http://127.0.0.1:8099/api/state",timeout=2) as r:
        return json.load(r)
pid=int(open("/tmp/garuda-fresh.pid").read())
before=state()
assert before["lock"]["control_valid"], "test requires a live valid target"
started=time.monotonic()
os.kill(pid,signal.SIGSTOP)
try:
    time.sleep(.35)
    stopped=state()
    assert not stopped["lock"]["control_valid"]
    assert not stopped["image_target"]["valid"]
    time.sleep(1.05)
finally:
    os.kill(pid,signal.SIGCONT)
time.sleep(.8)
resumed=state()
assert not resumed["lock"]["control_valid"]
assert resumed["lock"]["state"]=="lost", resumed["lock"]
print(json.dumps({"before":before,"paused":stopped,"resumed":resumed,"elapsed_s":time.monotonic()-started},indent=2))
