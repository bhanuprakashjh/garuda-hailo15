import copy
from dataclasses import replace
import json
import pathlib
import sys
import unittest
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from fresh_follow import FreshFollow
from fresh_target_adapter import from_fresh
from garuda_interfaces import TargetObservation
from fresh_follow_observe import poll

MS = 1_000_000


def observation(**changes):
    values = dict(source_id="camera", stream_id="run-1", clock_domain="board.boot-1",
                  sequence=1, capture_ns=1000*MS, publish_ns=1010*MS, sample_ns=1020*MS,
                  freshness_ns=200*MS, valid_for_ns=180*MS, observation_age_ns=20*MS,
                  epoch=1, track_id=7, label="person", bbox=(.6,.2,.2,.5), confidence=.9,
                  position_std_fraction=.03, timestamp_valid=True, observation_valid=True,
                  control_valid=True, state="tracking", reason="tracking")
    values.update(changes)
    return TargetObservation(**values)


def envelope():
    return dict(tracker_contract="garuda.fresh.v1", source_id="camera", stream_id="run-1",
                clock_domain="board.boot-1", sequence=1, capture_monotonic_ms=1000,
                publish_monotonic_ms=1010, sample_monotonic_ms=1020, age_ms=20,
                freshness_budget_ms=200, valid_for_ms=180, timestamp_valid=True,
                frame=dict(width=1280,height=720),
                tracks=[dict(id=7,label="person",ambiguous=False,coasting=False,conf=.9)],
                lock=dict(id=1,track_id=7,epoch=1,**{"class":"person"}, box=dict(x=768,y=144,w=256,h=360),
                          uncertainty_px=38.4,obs_age_ms=20,observation_valid=True,control_valid=True,
                          state="tracking",reason="tracking"),
                image_target=dict(valid=True,u=.7,v=.45,width_fraction=.2,height_fraction=.5))


class FreshFollowTests(unittest.TestCase):
    def setUp(self):
        self.follow = FreshFollow("camera", "run-1", 1)

    def hold(self, decision, reason=None):
        cmd = decision.command
        self.assertFalse(cmd.valid)
        self.assertEqual((cmd.yaw_rate,cmd.forward_vel,cmd.vertical_vel),(0,0,0))
        if reason:
            self.assertEqual(cmd.reason,reason)

    def test_unrelated_clocks_and_transport_expiry(self):
        # Receiver clock deliberately 8999 seconds ahead of the source clock.
        self.assertTrue(self.follow.ingest(observation(),9000000*MS,9000010*MS))
        decision = self.follow.tick(9000020*MS)
        self.assertTrue(decision.command.valid)
        self.assertGreater(decision.command.yaw_rate,0)
        self.assertEqual((decision.command.forward_vel,decision.command.vertical_vel),(0,0))
        self.assertEqual(decision.observation_age_upper_ns,40*MS)
        self.assertFalse(decision.to_dict()["range_available"])
        self.hold(self.follow.tick(9000180*MS),"target_expired")

    def test_duplicate_frozen_body_cannot_renew(self):
        self.follow.ingest(observation(),0,10*MS)
        initial_deadline = self.follow.deadline
        for t in (50,100,150):
            self.follow.ingest(observation(),t*MS,(t+1)*MS)
            self.assertEqual(self.follow.deadline,initial_deadline)
        self.hold(self.follow.tick(180*MS),"target_expired")
        self.assertFalse(self.follow.ingest(observation(),190*MS,191*MS))
        self.hold(self.follow.tick(192*MS))

    def test_source_restart_selection_change_and_clock_change_hold(self):
        self.follow.ingest(observation(),0,MS)
        for values in (dict(stream_id="run-2"),dict(epoch=2),dict(source_id="another-camera"),dict(clock_domain="board.boot-2")):
            self.assertFalse(self.follow.ingest(observation(**values),2*MS,3*MS))
            self.hold(self.follow.tick(4*MS))
            # fresh controller for each independent fault
            self.setUp();self.follow.ingest(observation(),0,MS)

    def test_mot_id_can_change_within_selected_identity(self):
        self.follow.ingest(observation(),0,MS)
        returning = observation(sequence=2,capture_ns=1050*MS,publish_ns=1060*MS,sample_ns=1070*MS,track_id=99)
        self.assertTrue(self.follow.ingest(returning,50*MS,51*MS))
        self.assertEqual(self.follow.tick(52*MS).command.target_id,99)
        self.assertEqual(self.follow.tick(53*MS).epoch,1)

    def test_old_frames_and_timestamp_discontinuities(self):
        self.follow.ingest(observation(sequence=2),0,MS)
        for changes in (dict(sequence=1),dict(capture_ns=999*MS),dict(sequence=3),
                        dict(sample_ns=1019*MS),dict(publish_ns=1009*MS)):
            self.assertFalse(self.follow.ingest(observation(sequence=2,**changes) if 'sequence' not in changes else observation(**changes),2*MS,3*MS))
            self.hold(self.follow.tick(4*MS),"source_out_of_order")
            self.setUp();self.follow.ingest(observation(sequence=2),0,MS)

    def test_ambiguous_coasting_lost_uncertain_and_slow_delivery(self):
        for state in ("ambiguous","coasting","lost","reacquiring"):
            self.setUp()
            self.assertFalse(self.follow.ingest(observation(state=state,control_valid=False,observation_valid=False,reason=state),0,MS))
            self.hold(self.follow.tick(2*MS))
        self.setUp()
        self.assertFalse(self.follow.ingest(observation(position_std_fraction=.13),0,MS))
        self.hold(self.follow.tick(2*MS),"target_uncertain")
        self.setUp()
        self.assertFalse(self.follow.ingest(observation(),0,181*MS))
        self.hold(self.follow.tick(182*MS),"target_expired")

    def test_local_clock_regression_and_invalid_packet_clear_command(self):
        self.follow.ingest(observation(),10*MS,11*MS)
        self.hold(self.follow.tick(9*MS),"receiver_clock_regressed")
        self.setUp();self.follow.ingest(observation(),10*MS,11*MS)
        self.follow.reject("invalid_packet")
        self.hold(self.follow.tick(12*MS),"invalid_packet")

    def test_source_cannot_expand_consumer_budget(self):
        self.assertFalse(self.follow.ingest(observation(freshness_ns=5000*MS,valid_for_ns=4000*MS,
                                                       sample_ns=1500*MS,observation_age_ns=500*MS),0,MS))
        self.hold(self.follow.tick(2*MS))

    def test_schema_roundtrip_and_bad_values(self):
        self.assertEqual(TargetObservation.from_dict(json.loads(json.dumps(observation().to_dict()))),observation())
        for changes in (dict(confidence=float('nan')),dict(position_std_fraction=-1),dict(epoch=True),
                        dict(control_valid="true"),dict(capture_ns=2000*MS),dict(bbox=(.9,.2,.2,.5)),
                        dict(state="ambiguous"),dict(schema="garuda.target_observation.v2")):
            with self.assertRaises(ValueError):
                observation(**changes)

    def test_fresh_envelope_geometry_and_validity(self):
        self.assertEqual(from_fresh(envelope()),observation())
        for edit in (lambda s:s['image_target'].update(u=.2),lambda s:s['tracks'][0].update(ambiguous=True),
                     lambda s:s.update(age_ms=0),lambda s:s.pop('stream_id'),lambda s:s['lock'].update(control_valid="true")):
            value = copy.deepcopy(envelope());edit(value)
            with self.assertRaises((ValueError,KeyError)):
                from_fresh(value)

    def test_blocked_http_worker_does_not_block_command_expiry(self):
        class Handler(BaseHTTPRequestHandler):
            paused = False
            sequence = 0

            def log_message(self,*args):
                pass

            def do_GET(self):
                if Handler.paused:
                    time.sleep(.5)
                    return
                Handler.sequence += 1
                raw = envelope()
                now = time.monotonic_ns()/MS
                raw.update(sequence=Handler.sequence,capture_monotonic_ms=now-20,
                           publish_monotonic_ms=now-10,sample_monotonic_ms=now)
                encoded = json.dumps(raw).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(encoded)));self.end_headers()
                self.wfile.write(encoded)

        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        stop,messages = threading.Event(),queue.Queue(maxsize=1)
        worker = threading.Thread(target=poll,args=(f'http://127.0.0.1:{server.server_port}/api/state',stop,messages),daemon=True)
        worker.start()
        try:
            o,started,received,error = messages.get(timeout=1)
            self.assertIsNone(error)
            self.assertTrue(self.follow.ingest(o,started,received))
            self.assertTrue(self.follow.tick(time.monotonic_ns()).command.valid)
            Handler.paused = True
            end = time.monotonic()+.45
            decisions = []
            while time.monotonic() < end:
                try:
                    o,started,received,error = messages.get_nowait()
                    if error:self.follow.reject('transport_'+error)
                    else:self.follow.ingest(o,started,received)
                except queue.Empty:
                    pass
                decisions.append(self.follow.tick(time.monotonic_ns()))
                time.sleep(.025)
            self.assertGreaterEqual(len(decisions),10)
            for decision in decisions[-5:]:self.hold(decision)
        finally:
            stop.set();worker.join(timeout=.6);server.shutdown();server.server_close()

    @unittest.skipUnless(os.environ.get('GARUDA_REPLAY_BIN'), 'native C++ replay path required')
    def test_actual_cpp_tracker_to_follow_closed_loop(self):
        sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/'bench'))
        from fresh_follow_sim import run
        for label in ('person','cell phone'):
            summary,rows = run(os.environ['GARUDA_REPLAY_BIN'],label)
            self.assertLess(summary['final_framing_error'],.08)
            for fault in summary['faults'].values():self.assertTrue(fault['hold_after_deadline'])
            self.assertTrue(all(r['range_available'] is False for r in rows))


if __name__ == "__main__":
    unittest.main()
