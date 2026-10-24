"""The committed fresh-node profiles and the control script agree with each other."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
FRESH = ROOT / 'hosts' / 'hailo15l' / 'fresh'
CTL = (ROOT / 'hosts' / 'hailo15l' / 'fresh_tracking_ctl.sh').read_text()
AERIAL_HEF = '/opt/garuda-fresh/models/yolov11s_aerial_hailo15l_v5.3.0.hef'
AERIAL_REID_HEF = '/opt/garuda-fresh/models/osnet_aerial_hailo15l_v5.3.0.hef'


class FreshProfiles(unittest.TestCase):
    def profiles(self):
        return {p.name: json.loads(p.read_text()) for p in FRESH.glob('perception*.json')}

    def test_car_embedding_deferral_is_not_promoted(self):
        for name, profile in self.profiles().items():
            self.assertFalse(profile.get('defer_person_embeddings_on_car', False), name)

    def test_every_profile_parses_with_the_shared_keys(self):
        for name, p in self.profiles().items():
            for key in ('hef', 'frame_w', 'frame_h', 'input_w', 'input_h', 'input_geometry', 'tracking'):
                self.assertIn(key, p, name)
            self.assertIn(p.get('target_roi', 'off'), ('off', 'assist', 'shadow'), name)
            if p['tracking'].get('learned_person_identity'):
                self.assertIn('person_reid_hef', p, name)
                self.assertIn('person_reid_model_id', p, name)
            if p.get('target_roi', 'off') != 'off':
                self.assertIn('target_roi_hef', p, name)

    def test_follow_profile_is_single_tile_roi_plus_embedding(self):
        p = self.profiles()['perception-follow.json']
        # tiles only while searching; once locked the single tile + ROI path runs
        self.assertTrue(p.get('detection_tiles') and p.get('tiles_when_unlocked'))
        self.assertGreaterEqual(p['tracking']['freshness_ms'], 500)   # tiled frames reach the tracker ~200 ms old
        self.assertEqual(p['target_roi'], 'assist')
        self.assertEqual(p['tracking']['reacquire_gap_ms'], 500)
        self.assertFalse(p.get('phone_predictive_roi', False))
        self.assertEqual(p.get('phone_short_miss_ms', 0), 0)
        self.assertEqual(p['target_roi_hef'], p['hef'])   # one validated model for both detectors
        self.assertTrue(p['tracking']['learned_person_identity'])
        self.assertEqual(p['input_geometry'], 'letterbox')
        self.assertGreaterEqual(p['person_embedding_max_per_frame'], 4)   # one or two bystanders never trip the incomplete-evidence refusal
        self.assertLessEqual(p['person_embedding_max_per_frame'], 16)
        # A descriptor must be computed for every frame the tracker will still accept: while searching
        # the five tiles deliver frames ~300 ms old, and a tighter embedding age guard than the
        # freshness window leaves every person undescribed, so the click is refused (2026-09-13).
        self.assertGreaterEqual(p['person_embedding_max_age_ms'], p['tracking']['freshness_ms'])

    def test_aerial_profile_is_the_follow_profile_with_the_aerial_detector(self):
        """The aerial profile differs from the desk profile only in the detector, the caps its
        denser output needs, the follow schedule measured for the ~250 ms aerial cadence, and
        the drone-view identity: the fine-tuned descriptor with its own gate and the evidence
        reach that lets a crowd re-bind (bench/results/2026-09-18-reid-visdrone)."""
        profiles = self.profiles()
        aerial, follow = profiles['perception-aerial.json'], profiles['perception-follow.json']
        self.assertEqual(aerial['hef'], AERIAL_HEF)
        self.assertEqual(aerial['target_roi_hef'], aerial['hef'])
        top = {'hef', 'target_roi_hef', 'follow_local_gap_ms', 'follow_global_period_ms', 'tracking',
               'person_reid_hef', 'person_reid_model_id', 'phone_predictive_roi', 'phone_short_miss_ms'}
        self.assertEqual({k: v for k, v in aerial.items() if k not in top},
                         {k: v for k, v in follow.items() if k not in top})
        # Desk geometric recovery tolerates one missed observation at its measured cadence.
        self.assertNotIn('reacquire_gap_ms', aerial['tracking'])
        self.assertNotIn('phone_predictive_roi', aerial)
        self.assertNotIn('phone_short_miss_ms', aerial)
        caps = {'max_tracks', 'max_detections', 'low_confidence', 'reacquire_gap_ms',
                'identity_max_distance', 'identity_evidence_radius', 'identity_evidence_radius_growth'}
        self.assertEqual({k: v for k, v in aerial['tracking'].items() if k not in caps},
                         {k: v for k, v in follow['tracking'].items() if k not in caps})
        # The descriptor is the staged aerial slot, named by the hash the model id carries.
        self.assertEqual(aerial['person_reid_hef'], AERIAL_REID_HEF)
        self.assertRegex(aerial['person_reid_model_id'], r'^osnet_x1_0_visdrone_v1_[a-z]+-hailo15l-5\.3\.0-sha256:[0-9a-f]{64}$')
        self.assertNotEqual(aerial['person_reid_model_id'], follow['person_reid_model_id'])
        # Fine-tuning pushed same-identity distances outwards (holdout median 0.13 -> 0.19), so the
        # gate is wider than the desk's 0.25 but still leaves the 0.04 margin room below it.
        self.assertGreater(aerial['tracking']['identity_max_distance'], follow['tracking'].get('identity_max_distance', .25))
        self.assertLessEqual(aerial['tracking']['identity_max_distance'], .35)
        # Evidence reach on (the desk keeps the unbounded rule): a radius with growth per second.
        self.assertGreater(aerial['tracking']['identity_evidence_radius'], 0)
        self.assertLessEqual(aerial['tracking']['identity_evidence_radius'], 2)
        self.assertGreater(aerial['tracking']['identity_evidence_radius_growth'], 0)
        self.assertNotIn('identity_evidence_radius', follow['tracking'])
        # The fine-tuned detector hit the 128-detection cap on three of the eleven clips.
        self.assertGreater(aerial['tracking']['max_detections'], follow['tracking']['max_detections'])
        self.assertLessEqual(aerial['tracking']['max_detections'], 512)   # the tracker's and the ROI merge's bound
        # Two verified ROI passes must fit inside the handover window at the aerial cadence.
        self.assertGreaterEqual(aerial['follow_local_gap_ms'], 1000)
        self.assertGreaterEqual(aerial['follow_global_period_ms'], aerial['follow_local_gap_ms'])

    def test_native_profile_adds_only_the_sensor_stream_to_the_follow_profile(self):
        """Native-pixel crops: the follow profile plus a third frontend stream at the sensor size,
        wired through its own media profile; the compare variant adds only the A/B key."""
        profiles = self.profiles()
        follow, native, compare = (profiles[n] for n in
                                   ('perception-follow.json', 'perception-follow-native.json', 'perception-follow-native-compare.json'))
        extra = {'profile', 'native_stream', 'native_w', 'native_h', 'native_max_window_px', 'target_roi_native_context'}
        self.assertEqual({k: v for k, v in native.items() if k not in extra}, {k: v for k, v in follow.items() if k not in extra})
        self.assertEqual((native['native_w'], native['native_h']), (3840, 2160))     # IMX678 full frame
        # Native pixels only where they magnify: at most a 2x shrink into the 640 input.
        self.assertGreaterEqual(native['native_max_window_px'], 640)
        self.assertLessEqual(native['native_max_window_px'], 1280)
        # At sensor scale the crop must keep the target small in the input (desk phone A/B 2026-09-15:
        # a 2.5x window showed the phone at 40 % of the crop and scored 0.36 vs 0.55 for the copy).
        self.assertGreaterEqual(native['target_roi_native_context'], 5)
        self.assertLessEqual(native['target_roi_native_context'], 8)
        self.assertNotIn(native['native_stream'], (native['ai_stream'], native['jpeg_stream']))
        self.assertEqual({k: v for k, v in compare.items() if k != 'target_roi_compare_paired'}, native)
        self.assertTrue(compare['target_roi_compare_paired'])
        media = json.loads((FRESH / 'medialib.json').read_text())
        entry = next(p for p in media['profiles'] if p['name'] == native['profile'])
        profile = json.loads((FRESH / pathlib.Path(entry['config_file']).name).read_text())
        settings = json.loads((FRESH / pathlib.Path(profile['application_settings']).name).read_text())
        streams = {s['stream_id']: s for s in settings['application_input_streams']['resolutions']}
        self.assertEqual((streams[native['native_stream']]['width'], streams[native['native_stream']]['height']), (3840, 2160))
        self.assertEqual((streams[native['jpeg_stream']]['width'], streams[native['jpeg_stream']]['height']),
                         (native['frame_w'], native['frame_h']))
        self.assertEqual((streams[native['ai_stream']]['width'], streams[native['ai_stream']]['height']),
                         (native['input_w'], native['input_h']))

    def test_demo_sim_profiles_mirror_the_node_profiles(self):
        """The grand demo's board stream runs staged copies under /opt/garuda-sim: the aerial one is
        the aerial node profile in adaptive stream mode; the fullview one is the desk follow
        profile in single-view stream mode. Both are staged by stage_sim_stream.sh."""
        sim = ROOT / 'hosts' / 'hailo15l' / 'sim'
        aerial = json.loads((sim / 'profile-aerial.json').read_text())
        node_aerial = self.profiles()['perception-aerial.json']
        self.assertEqual({k: v for k, v in aerial.items() if k != 'bench_schedule'}, node_aerial)
        self.assertEqual(aerial['bench_schedule'], 'adaptive')
        fullview = json.loads((sim / 'profile-fullview.json').read_text())
        follow = self.profiles()['perception-follow.json']
        self.assertEqual({k: v for k, v in fullview.items() if k != 'bench_schedule'}, follow)
        self.assertEqual(fullview['bench_schedule'], 'fullview')
        launcher = (ROOT / 'hosts' / 'hailo15l' / 'run_grand_demo.sh').read_text()
        self.assertIn('--aerial', launcher)
        self.assertIn('/opt/garuda-sim/profile-aerial.json', launcher)
        stage = (ROOT / 'hosts' / 'hailo15l' / 'stage_sim_stream.sh').read_text()
        self.assertIn('profile-aerial.json', stage)
        self.assertIn(AERIAL_HEF, stage)          # the aerial profile is refused unless the slot's
        self.assertRegex(stage, r'\.sha256')      # recorded hash still matches

    def test_aerial_model_is_staged_and_started_by_hash(self):
        stage = (ROOT / 'hosts' / 'hailo15l' / 'stage_fresh_tracking.sh').read_text()
        sim = (ROOT / 'hosts' / 'hailo15l' / 'stage_sim_stream.sh').read_text()
        self.assertIn('GARUDA_FRESH_AERIAL_HEF_SHA', stage)        # no candidate deploys by filename alone
        self.assertIn('GARUDA_FRESH_AERIAL_REID_HEF_SHA', stage)   # the descriptor slot likewise
        for script in (stage, CTL, sim):                            # the recorded hash travels with the file,
            self.assertIn(AERIAL_HEF, script)                       # and start-aerial / the demo stream check it
            self.assertIn(AERIAL_REID_HEF, script)
            self.assertRegex(script, r'\.sha256')
        # start-aerial must not demand the desk's zoo OSNet: the aerial profile carries its own.
        zoo_check = re.search(r'case "\$1" in ([^)]*)\)\n\s*ACTUAL=\$\(sha256sum /opt/garuda-fresh/models/osnet_x1_0_hailo15l', CTL)
        self.assertIsNotNone(zoo_check)
        self.assertNotIn('perception-aerial.json', zoo_check.group(1))

    def test_ctl_knows_every_profile(self):
        actions = re.search(r'^\s*(start\|[^)]*)\)', CTL, re.M).group(1).split('|')
        mapped = dict(re.findall(r'if \[ "\$ACTION" = (start-[a-z-]+) \]; then CONFIG_NAME=(perception-[a-z0-9-]+\.json)', CTL))
        self.assertEqual(mapped.get('start-follow'), 'perception-follow.json')
        self.assertEqual(mapped.get('start-aerial'), 'perception-aerial.json')
        for action, profile in mapped.items():
            self.assertIn(action, actions)
            self.assertTrue((FRESH / profile).exists(), profile)


if __name__ == '__main__':
    unittest.main()
