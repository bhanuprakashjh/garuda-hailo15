import copy
import unittest
from deploy_visual_target import configuration, healthy


class DeploymentGuards(unittest.TestCase):
    def test_only_visual_flag_changes(self):
        cfg=dict(input_w=1024,input_h=576,managed_detection=False,detection_tiles=False,
                 target_roi='off',tracking=dict(freshness_ms=500),hef='preserved',capture_source=False)
        result=configuration(cfg)
        self.assertTrue(result['tracking'].pop('visual_phone_tracking'))
        self.assertEqual(cfg,result)
        self.assertNotIn('visual_phone_tracking',cfg['tracking'])

    def test_wrong_baseline_refused(self):
        cfg=dict(input_w=1024,input_h=576,managed_detection=False,detection_tiles=False,
                 target_roi='off',tracking={})
        for key,value in [('input_w',640),('managed_detection',True),('detection_tiles',True),('target_roi','assist')]:
            bad=copy.deepcopy(cfg);bad[key]=value
            with self.assertRaises(ValueError):configuration(bad)
        cfg['tracking']['visual_phone_tracking']=True
        with self.assertRaises(ValueError):configuration(cfg)

    def test_health_requires_loaded_feature_and_good_source(self):
        s=dict(timestamp_valid=True,age_ms=100,diag=dict(person_embedding={'faulted':False},
            capture_stream={'active':False},camera_motion={'visual_target':{'reason':'uninitialized'}},
            source_pairing={'matched':10,'invalid':0},rejected_frames=0,input_capture={'remaining':0}))
        self.assertTrue(healthy(s))
        bad=copy.deepcopy(s);bad['diag']['camera_motion']={};self.assertFalse(healthy(bad))
        bad=copy.deepcopy(s);bad['diag']['source_pairing']['matched']=0;self.assertFalse(healthy(bad))
        bad=copy.deepcopy(s);bad['diag']['source_pairing']['invalid']=1;self.assertFalse(healthy(bad))
        bad=copy.deepcopy(s);bad['diag']['rejected_frames']=1;self.assertFalse(healthy(bad))
        bad=copy.deepcopy(s);bad['diag']['capture_stream']['active']=True;self.assertFalse(healthy(bad))
        bad=copy.deepcopy(s);bad['age_ms']=501;self.assertFalse(healthy(bad))


if __name__=='__main__':unittest.main()
