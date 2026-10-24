import copy
import unittest
from relative_framing import RelativeFraming


def row(h=200,w=80):
    return dict(source_id='camera',stream_id='boot',frame=dict(width=1280,height=720),
        lock=dict(id=1,epoch=1,state='tracking',control_valid=True,observation_valid=True,
                  box=dict(x=400,y=100,w=w,h=h)))


class FramingTests(unittest.TestCase):
    def test_relative_size_not_metric_or_authority(self):
        f=RelativeFraming()
        self.assertFalse(f.sample(row())['valid'])
        f.sample(row(),set_reference=True)
        result=f.sample(row(100,40))
        self.assertEqual(result['relative_distance'],2)
        self.assertFalse(result['metric_range'])
        self.assertFalse(result['translation_authorized'])

    def test_identity_or_geometry_change_drops_reference(self):
        for change in ('identity','geometry','stream'):
            f=RelativeFraming();f.sample(row(),set_reference=True);r=row()
            if change=='identity':r['lock']['epoch']=2
            elif change=='stream':r['stream_id']='new'
            else:r['frame']['width']=1920
            self.assertFalse(f.sample(r)['valid'])

    def test_clipping_pose_stale_and_nan_rejected(self):
        for change in ('clipped','pose','stale','nan'):
            f=RelativeFraming();f.sample(row(),set_reference=True);r=row()
            if change=='clipped':r['lock']['box']['y']=0
            elif change=='pose':r['lock']['box']['w']=150
            elif change=='stale':r['lock']['control_valid']=False
            else:r['lock']['box']['h']=float('nan')
            self.assertFalse(f.sample(r)['valid'])

    def test_display_zoom_has_no_input_to_range_cue(self):
        f=RelativeFraming();r=row();f.sample(r,set_reference=True)
        before=f.sample(r)
        r=copy.deepcopy(r);r['display_zoom']=4
        self.assertEqual(before,f.sample(r))


if __name__=='__main__':unittest.main()
