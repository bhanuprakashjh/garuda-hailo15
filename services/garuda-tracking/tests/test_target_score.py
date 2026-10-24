"""Ground-truth metric checks: physical identity, unobserved time and exact-input joins."""
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/"bench"))
from fresh_target_score import annotation_template, apply_predictions, evaluate, read_recording
from fresh_target_replay import replay

TARGET = [.2,.2,.1,.2]
DISTRACTOR = [.7,.2,.1,.2]


def sample(index, observed=True, predicted=None, ident=1, epoch=1):
    predicted = TARGET if predicted is None else predicted
    capture = 1000+index*50
    detection = dict(label="cell phone",confidence=.9,box=dict(zip(("x","y","w","h"),TARGET)))
    lock = dict(id=epoch,track_id=ident,epoch=epoch,observation_valid=observed,control_valid=observed,
                box={k:v*(1280 if k in ("x","w") else 720) for k,v in zip(("x","y","w","h"),predicted)})
    lock["class"] = "cell phone"
    return dict(recording_id="test",source_id="camera",stream_id="process",clock_domain="boot",
                nv12_sha256=hashlib.sha256(b"abcdef").hexdigest(),sample_index=index,
                input_w=2,input_h=2,pixel_format="NV12",packed_stride=2,
                frame=dict(sequence=index+1,capture_ms=capture,now_ms=capture+10,timestamp_valid=True,
                           detections=[detection],motion=dict(dx=0,dy=0,valid=False)),
                output=dict(sequence=index+1,capture_monotonic_ms=capture,publish_monotonic_ms=capture+10,
                            frame=dict(width=1280,height=720),lock=lock))


def truth_for(rows):
    result = annotation_template(rows,"cell phone")
    result.update(annotator="synthetic_fixture",selection=dict(epoch=1,start_sequence=rows[0]["frame"]["sequence"]))
    for gt in result["frames"]:
        gt.update(visibility="visible",box=TARGET,distractors=[dict(id="other-phone",box=DISTRACTOR)])
    return result


class TargetScoreTests(unittest.TestCase):
    def test_observed_target_does_not_imply_usable_control(self):
        rows = [sample(0),sample(1)]
        rows[0]["output"]["lock"]["control_valid"] = False
        s = evaluate(rows,truth_for(rows))["selection"]
        self.assertEqual(s["correct_visible_fraction"],1)
        self.assertEqual(s["correct_visible_control_fraction"],.5)
        self.assertEqual(s["visible_lost_time_ms"],0)
        self.assertEqual(s["visible_control_unavailable_ms"],50)

    def test_wrong_identity_is_not_mot_id_churn(self):
        rows = [sample(0),sample(1,ident=2),sample(2,observed=False),
                sample(3,predicted=DISTRACTOR,ident=9),sample(4,ident=2)]
        result = evaluate(rows,truth_for(rows));s = result["selection"]
        self.assertEqual(s["physical_identity_switches"],2)
        self.assertEqual(s["correct_target_mot_id_changes"],1)
        self.assertEqual(s["false_reacquisition_events"],1)
        self.assertEqual(s["wrong_object_observation_frames"],1)
        self.assertEqual(s["incorrect_or_unverified_control_frames"],1)
        self.assertEqual(s["visible_time_ms"],200)
        self.assertEqual(s["visible_lost_time_ms"],100)
        self.assertEqual(s["recovery_episodes"][-1]["delay_ms"],100)

    def test_unknown_and_sparse_frames_do_not_invent_tracking_time(self):
        rows = [sample(0),sample(10,observed=False),sample(20,predicted=DISTRACTOR)]
        t = truth_for(rows);s = evaluate(rows,t)["selection"]
        self.assertIsNone(s["visible_lost_time_ms"])
        self.assertEqual(s["physical_identity_switches"],0)
        self.assertTrue(any(not e["recovered"] for e in s["recovery_episodes"]))
        t = annotation_template(rows,"cell phone");result = evaluate(rows,t)
        self.assertIsNone(result["detector"]["target_recall"])
        self.assertIsNone(result["selection"]["correct_visible_fraction"])
        self.assertIsNone(result["selection"]["physical_identity_switches"])

    def test_occlusion_return_delay_and_censored_end(self):
        rows = [sample(i,observed=i in (0,4)) for i in range(6)]
        t = truth_for(rows)
        for index in (1,2): t["frames"][index].update(visibility="occluded",box=None)
        s = evaluate(rows,t)["selection"]
        recovered = [e for e in s["recovery_episodes"] if e["recovered"]]
        self.assertEqual(recovered[-1]["start_sequence"],4)
        self.assertEqual(recovered[-1]["delay_ms"],50)
        self.assertEqual(s["recovery_episodes"][-1]["censored_reason"],"end_of_recording")

    def test_overlapping_truth_is_unverified_not_a_claimed_identity_switch(self):
        rows = [sample(0)];t = truth_for(rows);t["frames"][0]["distractors"][0]["box"] = TARGET
        s = evaluate(rows,t)["selection"]
        self.assertEqual(s["overlap_ambiguous_frames"],1)
        self.assertEqual(s["correct_observation_frames"],0)
        self.assertEqual(s["wrong_object_observation_frames"],0)
        self.assertEqual(s["incorrect_or_unverified_control_frames"],1)

    def test_epoch_change_is_reported_separately(self):
        rows = [sample(0),sample(1,predicted=DISTRACTOR,epoch=2)]
        s = evaluate(rows,truth_for(rows))["selection"]
        self.assertEqual(s["epoch_mismatch_frames"],1)
        self.assertEqual(s["physical_identity_switches"],0)

    def test_absence_does_not_count_as_detector_success(self):
        rows = [sample(0)];t = truth_for(rows);t["frames"][0].update(visibility="out_of_view",box=None)
        result = evaluate(rows,t)
        self.assertIsNone(result["detector"]["target_recall"])
        self.assertEqual(result["selection"]["incorrect_or_unverified_control_frames"],1)

    def test_annotation_integrity_and_review_required(self):
        rows = [sample(0)]
        for mutate in (lambda t:t["frames"][0].update(nv12_sha256="wrong"),
                       lambda t:t["frames"][0].update(capture_ms=1001),
                       lambda t:t.update(annotator="UNREVIEWED"),
                       lambda t:t["frames"][0].update(box=[0,0,float("nan"),.1])):
            t = truth_for(rows);mutate(t)
            with self.assertRaises(ValueError):evaluate(rows,t)

    def test_exact_recording_rejects_pixel_tamper_and_incomplete_footer(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d);row = sample(0)
            (p/"summary.json").write_text(json.dumps(dict(complete=True,frames=1,producer=["camera","process","boot"])))
            (p/"end.json").write_text(json.dumps(dict(complete=True,sent=1,recording_id="test")))
            (p/"request.json").write_text(json.dumps(dict(frames=1,recording_id="test")))
            (p/"000000.json").write_text(json.dumps(row));(p/"000000.nv12").write_bytes(b"abcdef")
            self.assertEqual(len(read_recording(p)),1)
            (p/"000000.nv12").write_bytes(b"abcdeg")
            with self.assertRaisesRegex(ValueError,"hash"):read_recording(p)
            (p/"end.json").write_text(json.dumps(dict(complete=False,sent=1,recording_id="test")))
            with self.assertRaisesRegex(ValueError,"incomplete"):read_recording(p)

    def test_paired_source_integrity_is_checked_before_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);row=sample(0);row["isp_timestamp_ns"]=1_000_000_000
            row["output"]["frame"]=dict(width=2,height=2)
            row["source_image"]=dict(width=2,height=2,pixel_format="NV12",packed_stride=2,
                byte_offset=6,byte_length=6,isp_timestamp_ns=1_000_000_000,
                sha256=hashlib.sha256(b"ghijkl").hexdigest())
            (p/"summary.json").write_text(json.dumps(dict(complete=True,frames=1,paired_frames=1,producer=["camera","process","boot"])))
            (p/"end.json").write_text(json.dumps(dict(complete=True,sent=1,recording_id="test")))
            (p/"request.json").write_text(json.dumps(dict(frames=1,recording_id="test")))
            (p/"000000.json").write_text(json.dumps(row));(p/"000000.nv12").write_bytes(b"abcdef")
            (p/"000000.source.nv12").write_bytes(b"ghijkl")
            self.assertEqual(len(read_recording(p)),1)
            truth=annotation_template([row],"cell phone")
            self.assertEqual(truth["frames"][0]["source_nv12_sha256"],row["source_image"]["sha256"])
            truth["frames"][0]["source_nv12_sha256"]="different-source"
            with self.assertRaisesRegex(ValueError,"source image"):evaluate([row],truth)
            (p/"000000.source.nv12").write_bytes(b"ghijkm")
            with self.assertRaisesRegex(ValueError,"source hash"):read_recording(p)

    def test_prediction_join_rejects_reordered_or_missing_frames(self):
        rows = [sample(0),sample(1)]
        predictions = [{**{k:r[k] for k in ("recording_id","source_id","stream_id","clock_domain","nv12_sha256")},
                        "sequence":r["frame"]["sequence"],"capture_ms":r["frame"]["capture_ms"],
                        "output":r["output"],"detections":r["frame"]["detections"],"provenance":{"kind":"synthetic"}} for r in rows]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/"p.jsonl"
            def write(rs):p.write_text("".join(json.dumps(r)+"\n" for r in rs))
            write(predictions);self.assertEqual(len(apply_predictions(rows,p)[0]),2)
            write(predictions[::-1])
            with self.assertRaisesRegex(ValueError,"sequence"):apply_predictions(rows,p)
            write(predictions[:1])
            with self.assertRaisesRegex(ValueError,"coverage"):apply_predictions(rows,p)

    def test_actual_cpp_replay_visible_detector_dropout(self):
        binary = pathlib.Path(os.environ.get("GARUDA_REPLAY_BIN","/tmp/garuda-fresh/native/garuda-track-replay"))
        if not binary.exists():self.skipTest("build garuda-track-replay to check real tracker integration")
        rows = [sample(i) for i in range(20)]
        for i in range(10,14):rows[i]["frame"]["detections"] = []
        predictions = replay(rows,binary,"cell phone")
        for row,p in zip(rows,predictions):row["output"] = p["output"]
        result = evaluate(rows,truth_for(rows));s = result["selection"]
        self.assertEqual(result["detector"]["target_recall"],.8)
        self.assertEqual(s["physical_identity_switches"],0)
        self.assertEqual(s["false_reacquisition_events"],0)
        self.assertEqual(s["visible_lost_time_ms"],350)
        self.assertEqual(s["recovery_episodes"][-1]["delay_ms"],200)


if __name__ == "__main__":unittest.main()
