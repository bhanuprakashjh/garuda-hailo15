import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/'bench'))
from run_local_capture_trial import validate_remote, validate_snapshot


class LocalCaptureTrialTests(unittest.TestCase):
    def state(self):
        return dict(native_running=True,replay_running=False,mavros_running=False,
                    capture_stream_port=8983,capture_source=True,free_bytes=3*1024**3)

    def test_requires_running_paired_camera_and_no_other_work(self):
        validate_snapshot(self.state(),24)
        for key,value in [('native_running',False),('replay_running',True),('mavros_running',True),
                          ('capture_source',False),('capture_stream_port',None),('free_bytes',1024)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_snapshot({**self.state(),key:value},24)

    def test_short_emmc_limit_and_owned_path(self):
        for frames in [0,25,120,True,1.5]:
            with self.assertRaises(ValueError):validate_snapshot(self.state(),frames)
        self.assertEqual(validate_remote('/opt/garuda-fresh/local-record.aB123Z'),'/opt/garuda-fresh/local-record.aB123Z')
        for path in ['/opt/garuda-fresh','/tmp/local-record.aB123Z','/opt/garuda-fresh/local-record.../../']:
            with self.assertRaises(ValueError):validate_remote(path)


if __name__ == '__main__':unittest.main()
