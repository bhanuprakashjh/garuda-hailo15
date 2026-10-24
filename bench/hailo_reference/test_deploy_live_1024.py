import copy
import unittest
from deploy_live_1024 import configuration, healthy


class Live1024Tests(unittest.TestCase):
    def test_only_input_and_detector_route_change(self):
        cfg=dict(frame_w=1280,frame_h=720,ai_stream='sink0',tracking={'control_confidence':.4},person_reid_hef='keep')
        app={'application_input_streams':{'resolutions':[dict(stream_id='sink0',width=640,height=640,framerate=20),
            dict(stream_id='sink1',width=1280,height=720)]},'digital_zoom':{'enabled':False}}
        media={'profiles':[]};profile={'iq_settings':'keep','sensor_config':'keep','application_settings':'old'}
        originals=copy.deepcopy([cfg,media,profile,app])
        result=configuration(cfg,media,profile,app,'/stage')
        self.assertEqual(originals,[cfg,media,profile,app])
        new=result['candidate.json']
        self.assertEqual(new['tracking'],cfg['tracking']);self.assertEqual(new['person_reid_hef'],'keep')
        self.assertFalse(new['detection_tiles']);self.assertFalse(new['managed_detection']);self.assertEqual(new['target_roi'],'off')
        self.assertFalse(new['capture_source'])
        streams=result['application.json']['application_input_streams']['resolutions']
        self.assertEqual((streams[0]['width'],streams[0]['height']),(1024,576))
        self.assertEqual(streams[0]['framerate'],20);self.assertEqual(streams[1],app['application_input_streams']['resolutions'][1])
        self.assertEqual(result['profile.json']['iq_settings'],'keep');self.assertEqual(result['profile.json']['sensor_config'],'keep')

    def test_health_rejects_extra_passes_and_staleness(self):
        s=dict(timestamp_valid=True,age_ms=100,diag=dict(detection_tiles=dict(enabled=False,managed_detection=False,detector_passes_this_frame=1),
            target_roi=dict(mode='off',inferences=0),person_embedding=dict(faulted=False),capture_stream=dict(active=False)))
        self.assertTrue(healthy(s));s['diag']['detection_tiles']['detector_passes_this_frame']=5
        self.assertFalse(healthy(s));s['diag']['detection_tiles']['detector_passes_this_frame']=1;s['age_ms']=501
        self.assertFalse(healthy(s))
        s['age_ms']=100;del s['diag']['detection_tiles'];del s['diag']['target_roi']
        self.assertTrue(healthy(s))


if __name__=='__main__':unittest.main()
