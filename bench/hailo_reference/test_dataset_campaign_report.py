import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from dataset_campaign_report import archive,detector_pair


class EvidenceTests(unittest.TestCase):
    def test_pair_rejects_different_images_and_models_before_scoring(self):
        for field in ('image','model'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);left=root/'left';right=root/'right'
                for directory in (left,right):
                    directory.mkdir()
                    run=dict(hef_sha256='model',probe_sha256='probe',preparation=dict(images=[dict(file='a.jpg',image_sha256='image')]))
                    if directory==right:
                        if field=='model':run['hef_sha256']='different'
                        else:run['preparation']['images'][0]['image_sha256']='different'
                    (directory/'run.json').write_text(json.dumps(run))
                with self.assertRaises(ValueError):detector_pair(left,right)

    def test_archive_omits_pixels_and_keeps_verifiable_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();destination=root/'archive'
            raw=b'{"actual":true}\n'
            (source/'events.jsonl').write_bytes(raw)
            (source/'source.nv12').write_bytes(b'pixels')
            (source/'camera.jpg').write_bytes(b'pixels')
            archive(source,destination)
            self.assertFalse((destination/'source.nv12').exists())
            self.assertFalse((destination/'camera.jpg').exists())
            packed=(destination/'events.jsonl.gz').read_bytes()
            manifest=json.loads((destination/'archive-manifest.json').read_text())
            self.assertEqual(gzip.decompress(packed),raw)
            self.assertEqual(manifest['events.jsonl.gz']['sha256'],hashlib.sha256(packed).hexdigest())
            with self.assertRaises(FileExistsError):archive(source,destination)


if __name__=='__main__':unittest.main()
