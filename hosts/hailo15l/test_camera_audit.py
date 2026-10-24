import importlib.util
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('camera_audit', Path(__file__).with_name('camera_audit.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CameraAuditTests(unittest.TestCase):
    def test_controls_units(self):
        self.assertEqual(audit.parse_controls('isp_ae_enable: 1\nisp_ae_integration_time: 10000\nisp_ae_gain: 2048'),
                         dict(auto=True, exposure_ms=10, gain=2))

    def test_missing_control_fails(self):
        with self.assertRaises(KeyError):
            audit.parse_controls('isp_ae_enable: 1')

    def test_zoom_keeps_sensor_coordinates(self):
        roi = audit.zoom_geometry(3840, 2160, 2, 1.2)
        self.assertEqual([roi[k] for k in ('x', 'y', 'width', 'height')], [960, 540, 1920, 1080])
        self.assertAlmostEqual(roi['hfov_rad'], 2*math.atan(math.tan(.6)/2))
        self.assertNotAlmostEqual(roi['hfov_rad'], .6)

    def test_invalid_zoom(self):
        for z in (0, -1, float('nan'), float('inf'), True, 10000):
            with self.assertRaises(ValueError):
                audit.zoom_geometry(3840, 2160, z)

    def test_no_path_escape(self):
        with self.assertRaises(ValueError):
            audit.Audit(Path('/tmp')).path('../../etc/passwd')

    def test_resolves_selected_profile_not_first_entry(self):
        reader = audit.Audit()
        values = {
            '/opt/garuda-fresh/current.json': dict(medialib_config='/media.json', profile='Letterbox'),
            '/media.json': dict(profiles=[dict(name='Default', config_file='/first.json'),
                                         dict(name='Letterbox', config_file='/selected.json')]),
            '/etc/imaging/cfg/hailo15l/imx678/theia_sl410m/4k/medialib_configs/frontend_api_example_config.json': dict(profiles=[]),
        }
        reader.read = values.__getitem__
        reader.profile = lambda path: dict(path=path)
        self.assertEqual(reader.collect()['active']['path'], '/selected.json')


if __name__ == '__main__':
    unittest.main()
