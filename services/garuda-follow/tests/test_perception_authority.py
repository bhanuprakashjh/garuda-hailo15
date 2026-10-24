import copy
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from perception_authority import PerceptionAuthority
from test_fresh_follow import envelope

MS=1_000_000


class PerceptionAuthorityTests(unittest.TestCase):
    def test_real_envelope_duplicate_expiry_and_producer_binding(self):
        p=PerceptionAuthority("camera","run-1",1,execution="live")
        row=envelope()
        self.assertTrue(p.ingest(row,1000*MS,1001*MS))
        i=p.tick(1002*MS)
        self.assertTrue(i.command_eligible)
        self.assertEqual((i.source_id,i.stream_id,i.sequence),("camera","run-1",1))
        self.assertEqual(i.forward_vel,0) # board default is yaw-only
        for t in (1050,1100,1150):
            p.ingest(row,t*MS,(t+1)*MS);p.tick((t+2)*MS)
        self.assertFalse(p.tick(1181*MS).command_eligible)
        changed=copy.deepcopy(row);changed['stream_id']='other-process'
        self.assertFalse(p.ingest(changed,1200*MS,1201*MS))
        self.assertFalse(p.tick(1202*MS).command_eligible)

    def test_transport_error_and_contradictory_envelope_fail_closed(self):
        p=PerceptionAuthority("camera","run-1",1,execution="live")
        row=envelope();p.ingest(row,0,MS)
        self.assertTrue(p.tick(2*MS).command_eligible)
        p.reject('transport_stall');self.assertFalse(p.tick(3*MS).command_eligible)
        row['image_target']['valid']=False
        self.assertFalse(p.ingest(row,4*MS,5*MS))
        self.assertFalse(p.tick(6*MS).command_eligible)
