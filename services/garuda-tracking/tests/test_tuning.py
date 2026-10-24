import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fresh_tuning import Tuning, LIMITS, validate


class TuningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.t = Tuning(SimpleNamespace(_raw_snap=b'{}'), root)
        self.cfg = {"medialib_config": str(root/'media.json'), "profile": "test",
                    "ai_stream": "sink0", "jpeg_stream": "sink1", "jpeg_fps": 10,
                    "tracking": {"birth_confidence": .5, "control_confidence": .4,
                                 "confirm_ms": 120, "coast_ms": 1200}}
        self.t.write(self.t.config_path, self.cfg)
        self.t.write(root/'media.json', {"profiles": [{"name": "test", "config_file": str(root/'profile.json')}]})
        self.t.write(root/'profile.json', {"application_settings": str(root/'app.json')})
        self.app = {"application_input_streams": {"resolutions": [
            {"stream_id": "sink0", "framerate": 20}, {"stream_id": "sink1", "framerate": 20}]}}
        self.t.write(root/'app.json', self.app)
        self.cam = {"auto": True, "exposure_ms": 32.991, "gain": 7.4}
        self.t.camera = Mock(return_value=self.cam)
        self.t.set_camera = Mock()
        self.t.restart = Mock()
        self.values = self.t.state()['settings']

    def test_validation(self):
        for k, value in [('detector_fps', 100), ('preview_fps', 1.5), ('coast_ms', True),
                         ('control_confidence', float('nan')), ('birth_confidence', .15)]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                validate(dict(self.values, **{k:value}), LIMITS)
        with self.assertRaises(ValueError):
            validate(dict(self.values, arbitrary=1), LIMITS)

    def test_pipeline_and_restore(self):
        self.t.apply({'action':'pipeline', 'values':dict(self.values, detector_fps=30, preview_fps=15)})
        self.assertEqual(self.t.state()['settings']['detector_fps'], 30)
        self.assertEqual(self.t.state()['settings']['preview_fps'], 15)
        self.t.apply({'action':'restore'})
        self.assertEqual(self.t.read(self.t.config_path), self.cfg)
        self.assertEqual(self.t.read(self.t.root/'app.json'), self.app)

    def test_failed_restart_rolls_back(self):
        self.t.restart.side_effect = [RuntimeError('bad FPS'), None]
        with self.assertRaisesRegex(RuntimeError, 'previous settings recovered'):
            self.t.apply({'action':'pipeline', 'values':dict(self.values, detector_fps=30)})
        self.assertEqual(self.t.read(self.t.config_path), self.cfg)
        self.assertEqual(self.t.read(self.t.root/'app.json'), self.app)

    def test_camera_is_live(self):
        c = {'auto':False, 'exposure_ms':10, 'gain':24}
        self.t.apply({'action':'camera','values':c})
        self.t.set_camera.assert_called_once_with(c)
        self.t.restart.assert_not_called()

    def test_camera_error_restores(self):
        self.t.set_camera.side_effect = [RuntimeError('driver'), None]
        with self.assertRaises(RuntimeError):
            self.t.apply({'action':'camera','values':{'auto':False,'exposure_ms':10,'gain':24}})
        self.assertEqual(self.t.set_camera.call_args.args[0], self.cam)

    def test_invalid_camera(self):
        with self.assertRaises(ValueError):
            self.t.apply({'action':'camera','values':{'auto':'false','exposure_ms':10,'gain':24}})
        self.t.set_camera.assert_not_called()

    def test_confidence_order(self):
        with self.assertRaises(ValueError):
            self.t.apply({'action':'pipeline','values':dict(self.values, control_confidence=.9)})
        self.t.restart.assert_not_called()

    def test_concurrent_apply_rejected(self):
        with self.t.mutex, self.assertRaises(ValueError):
            self.t.apply({'action':'restore'})

    def test_paths_confined(self):
        with self.assertRaises(ValueError):
            self.t.local_path('/etc/settings.json')

    def test_javascript_syntax(self):
        html = (Path(__file__).resolve().parents[1]/'fresh_tuning.html').read_text()
        script = html.split('<script>')[1].split('</script>')[0]
        subprocess.run(['node','--check'], input=script, text=True, check=True)


if __name__ == '__main__':
    unittest.main()
