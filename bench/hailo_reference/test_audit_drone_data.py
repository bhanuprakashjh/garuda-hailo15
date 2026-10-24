import json
from pathlib import Path
import tempfile
import unittest

from audit_drone_data import audit, detection_group, image_inventory, sequence_group


class DataAuditTests(unittest.TestCase):
    def test_groups_are_explicit_not_substring_matches(self):
        self.assertEqual(sequence_group('uav0000086_00870_s'), '0000086')
        self.assertEqual(detection_group('0000086_00200_d_0000042.jpg'), '0000086')
        self.assertIsNone(sequence_group('some-uav0000086_00870_s'))
        self.assertIsNone(detection_group('000000098287.jpg'))

    def test_empty_and_broken_inputs_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError): image_inventory(root)
            (root / 'broken.jpg').symlink_to(root / 'absent.jpg')
            with self.assertRaises(FileNotFoundError): image_inventory(root)

    def test_resolved_sources_are_counted_without_claiming_pixel_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); images = root / 'images'; images.mkdir()
            raw = root / '0000086_00000_d_0000001.jpg'; raw.write_bytes(b'fixture')
            for name in ['one.jpg', 'two.jpg']: (images / name).symlink_to(raw)
            result = image_inventory(images)
            self.assertEqual(result['images'], 2)
            self.assertEqual(result['unique_resolved_sources'], 1)
            self.assertEqual(result['filename_groups'], {'0000086': 2})
            self.assertIn('NOT image-content', result['fingerprint_scope'])

    def test_inventory_never_promotes_development_to_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vd = root / 'visdrone'; prepared = root / 'prepared'
            for split in ['VisDrone2019-DET-train', 'VisDrone2019-DET-val']:
                d = vd / split / 'images'; d.mkdir(parents=True)
                (d / '0000086_00000_d_0000001.jpg').write_bytes(b'fixture')
            seq = 'uav0000086_00870_s'
            source = vd / 'VisDrone2019-SOT-val/sequences' / seq; source.mkdir(parents=True)
            (source / '0000001.jpg').write_bytes(b'fixture')
            (vd / 'VisDrone2019-MOT-val/sequences/uav0000086_00000_v').mkdir(parents=True)
            dest = prepared / seq; dest.mkdir(parents=True)
            (dest / 'manifest.json').write_text(json.dumps(dict(sequence=str(source), frames=1, source_sha256='declared')))
            index = root / 'index.json'
            identities = [dict(sequence='uav0000086_00000_v', split='holdout', crops=2),
                          dict(sequence='uav0000117_02622_v', split='train', crops=2)]
            index.write_text(json.dumps(dict(identities=identities)))
            args = (vd, prepared, vd / 'VisDrone2019-DET-train/images', index)
            result = audit(*args)
            self.assertTrue(result['cases'][0]['detector_training_filename_group_match'])
            self.assertTrue(result['cases'][0]['reid_validation_filename_group_match'])
            self.assertEqual(result['eligible_untouched_holdout_sequences'], 0)
            self.assertFalse(result['drone_mount_qualified'])
            identities[1]['sequence'] = 'uav0000086_00400_v'
            index.write_text(json.dumps(dict(identities=identities)))
            with self.assertRaises(ValueError): audit(*args)


if __name__ == '__main__':
    unittest.main()
