"""Regression tests for structural findings and non-destructive copy behavior."""
import csv
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image
import yaml
from dataset_doctor.scanner import ScanCancelled, scan_dataset, parse_label, file_hash
from dataset_doctor.fixes import build_plan, write_clean_copy, FixAction
from dataset_doctor.exports import csv_report, html_report, json_report


class DatasetCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'dataset'
        self.root.mkdir()
        self.config(['helmet', 'jacket'])

    def tearDown(self):
        self.temp.cleanup()

    def config(self, names):
        (self.root / 'data.yaml').write_text(yaml.safe_dump({'nc': len(names), 'names': names}), encoding='utf-8')

    def image(self, relative, color='red', label='0 0.5 0.5 0.2 0.2\n'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (80, 60), color).save(path)
        if label is not None:
            parts = list(Path(relative).parts)
            if 'images' in parts:
                parts[parts.index('images')] = 'labels'
            target = (self.root / Path(*parts)).with_suffix('.txt')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(label, encoding='utf-8')
        return path

    def codes(self, result):
        return {i.code for i in result.issues}

    def test_empty_background_is_review_only(self):
        self.image('train/images/a.png', label='\n ')
        result = scan_dataset(self.root)
        empty = next(i for i in result.issues if i.code == 'empty_label')
        self.assertEqual(empty.severity, 'review')
        self.assertEqual(result.counts['errors'], 0)
        self.assertEqual(result.counts['backgrounds'], 1)

    def test_missing_labels_and_orphan(self):
        self.image('images/train/a.png', label=None)
        orphan = self.root / 'labels/train/orphan.txt'
        orphan.parent.mkdir(parents=True)
        orphan.write_text('0 0.5 0.5 0.2 0.2')
        result = scan_dataset(self.root)
        self.assertTrue({'missing_label', 'missing_image'} <= self.codes(result))
        self.assertEqual(result.records[0].split, 'train')

    def test_nested_image_first_layout(self):
        self.image('images/val/nested/a.PNG')
        result = scan_dataset(self.root)
        self.assertTrue(result.records[0].label_exists)
        self.assertEqual(result.records[0].label, 'labels/val/nested/a.txt')
        self.assertEqual(result.records[0].split, 'val')

    def test_invalid_boxes_ids_nan_and_polygon(self):
        content = '\n'.join(['0 0.5 0.5 0.2 0.2', '3 0.5 0.5 0.2 0.2', '0 0.95 0.5 0.2 0.2', '1 nan 0.5 0.2 0.2', '0 0.1 0.1 0.2 0.2 0.3 0.3', '0 0.5 0.5 0 0.2', '-1 0.5 0.5 0.2 0.2', '0.0 0.5 0.5 0.2 0.2'])
        annotations, issues, invalid, dup = parse_label(content, 2)
        self.assertEqual(len(annotations), 1)
        self.assertEqual(len(invalid), 7)
        self.assertEqual(len(issues), 7)
        self.assertFalse(dup)

    def test_boundary_tolerance_and_duplicate_rows(self):
        annotations, issues, invalid, duplicate = parse_label('0 0.1 0.1 0.2 0.2\n0 0.1000 0.1 0.2 0.2\n0 0.9 0.9 0.2 0.2', 2)
        self.assertEqual(len(annotations), 2)
        self.assertEqual(duplicate, [2])
        self.assertFalse(invalid)

    def test_pixel_duplicate_with_different_encoding_and_overlap(self):
        self.image('train/images/a.png')
        self.image('valid/images/b.bmp')
        self.image('test/images/c.png', color='blue')
        result = scan_dataset(self.root)
        self.assertEqual(len(result.duplicate_groups), 1)
        self.assertEqual(len(result.overlap_groups), 1)
        self.assertIn('split_overlap', self.codes(result))
        self.assertEqual(result.counts['duplicates'], 1)
        self.assertEqual(result.health, 33)

    def test_duplicate_annotation_conflicts(self):
        self.image('train/images/a.png')
        self.image('val/images/b.png', label='1 0.5 0.5 0.2 0.2')
        self.assertIn('annotation_conflict', self.codes(scan_dataset(self.root)))

    def test_corrupt_and_truncated_images(self):
        path = self.root / 'train/images/corrupt.png'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'not an image')
        good = self.image('train/images/truncated.png', color='green')
        data = good.read_bytes()
        good.write_bytes(data[:len(data)//2])
        result = scan_dataset(self.root)
        self.assertEqual(sum(i.code == 'unreadable_image' for i in result.issues), 2)

    def test_class_mapping_and_invalid_metadata(self):
        (self.root / 'data.yaml').write_text('nc: 3\nnames: {0: helmet, 1: jacket}')
        self.image('train/images/a.png')
        self.assertIn('class_count_mismatch', self.codes(scan_dataset(self.root)))
        (self.root / 'data.yaml').write_text('names: {1: helmet, 3: jacket}')
        with self.assertRaises(ValueError):
            scan_dataset(self.root)
        result = scan_dataset(self.root, ['helmet', 'jacket'])
        self.assertIn('config_error', self.codes(result))
        self.assertIn('class_override', self.codes(result))

    def test_empty_dataset_and_unassigned_splits(self):
        result = scan_dataset(self.root)
        self.assertEqual(result.health, 0)
        self.assertIn('no_images', self.codes(result))
        self.image('a.png')
        result = scan_dataset(self.root)
        self.assertEqual(result.records[0].split, 'unassigned')
        self.assertIn('unassigned_split', self.codes(result))

    def test_cancellation(self):
        self.image('train/images/a.png')
        with self.assertRaises(ScanCancelled):
            scan_dataset(self.root, cancelled=lambda: True)

    def test_class_imbalance_counts(self):
        self.image('train/images/a.png', label='\n'.join(f'0 {0.1+i*0.1} 0.5 0.1 0.1' for i in range(6)) + '\n1 0.5 0.5 0.2 0.2')
        result = scan_dataset(self.root)
        self.assertIn('class_imbalance', self.codes(result))
        self.assertEqual(result.counts['classes'], {'helmet': 6, 'jacket': 1})

    def test_fix_copy_preserves_original_and_only_selected_rows(self):
        source = '0 0.5 0.5 0.2 0.2\n0 0.500 0.5 0.2 0.2\n3 0.5 0.5 0.2 0.2\n'
        self.image('train/images/a.png', label=source)
        before = {p.relative_to(self.root).as_posix(): file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        result = scan_dataset(self.root)
        plan = build_plan(result)
        self.assertEqual(plan.actions[0].lines, [2])
        target = write_clean_copy(result, plan, self.base / 'copy')
        self.assertEqual((target / 'train/labels/a.txt').read_text(), '0 0.5 0.5 0.2 0.2\n3 0.5 0.5 0.2 0.2\n')
        after = {p.relative_to(self.root).as_posix(): file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertIn('invalid_class', self.codes(scan_dataset(target)))
        self.assertTrue((target / '.dataset_doctor/fix_manifest.json').exists())

    def test_drop_invalid_without_removing_duplicates(self):
        self.image('train/images/a.png', label='0 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2\n7 0.5 0.5 0.2 0.2')
        result = scan_dataset(self.root)
        plan = build_plan(result, remove_duplicates=False, drop_invalid=True)
        self.assertEqual(plan.actions[0].lines, [3])
        target = write_clean_copy(result, plan, self.base / 'copy')
        codes = self.codes(scan_dataset(target))
        self.assertIn('duplicate_annotation', codes)
        self.assertNotIn('invalid_class', codes)

    def test_create_background_requires_opt_in(self):
        self.image('train/images/a.png', label=None)
        result = scan_dataset(self.root)
        self.assertFalse(build_plan(result).actions)
        plan = build_plan(result, create_backgrounds=True)
        target = write_clean_copy(result, plan, self.base / 'copy')
        self.assertEqual((target / 'train/labels/a.txt').read_text(), '')
        self.assertFalse((self.root / 'train/labels/a.txt').exists())

    def test_reject_source_destination_and_existing_folder(self):
        self.image('train/images/a.png')
        result = scan_dataset(self.root)
        for path in [self.root, self.root / 'copy', self.base]:
            with self.assertRaises(ValueError):
                write_clean_copy(result, build_plan(result), path)
        existing = self.base / 'exists'
        existing.mkdir()
        with self.assertRaises(ValueError):
            write_clean_copy(result, build_plan(result), existing)

    def test_changed_source_rejected_and_staging_removed(self):
        self.image('train/images/a.png')
        result = scan_dataset(self.root)
        (self.root / 'train/labels/a.txt').write_text('')
        with self.assertRaises(ValueError):
            write_clean_copy(result, build_plan(result), self.base / 'copy')
        self.assertFalse((self.base / 'copy').exists())
        self.assertFalse(list(self.base.glob('.dataset-doctor-*')))

    def test_new_missing_label_invalidates_copy(self):
        self.image('train/images/a.png', label=None)
        result = scan_dataset(self.root)
        plan = build_plan(result, create_backgrounds=True)
        target = self.root / 'train/labels/a.txt'
        target.parent.mkdir(parents=True)
        target.write_text('0 0.5 0.5 0.2 0.2')
        with self.assertRaises(ValueError):
            write_clean_copy(result, plan, self.base / 'copy')

    def test_changed_config_rejected(self):
        self.image('train/images/a.png')
        result = scan_dataset(self.root)
        self.config(['a', 'b'])
        with self.assertRaises(ValueError):
            write_clean_copy(result, build_plan(result), self.base / 'copy')

    def test_copy_cancellation_removes_staging(self):
        self.image('train/images/a.png')
        result = scan_dataset(self.root)
        with self.assertRaises(ScanCancelled):
            write_clean_copy(result, build_plan(result), self.base / 'copy', cancelled=lambda: True)
        self.assertFalse((self.base / 'copy').exists())
        self.assertFalse(list(self.base.glob('.dataset-doctor-*')))

    def test_ambiguous_label_pair_blocks_fixes(self):
        self.image('train/images/a.png')
        self.image('train/images/a.jpg', color='green')
        result = scan_dataset(self.root)
        self.assertIn('ambiguous_pair', self.codes(result))
        with self.assertRaises(ValueError):
            build_plan(result)

    def test_symlinks_skipped(self):
        image = self.image('train/images/a.png')
        try:
            (image.parent / 'linked.png').symlink_to(image)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable on this platform')
        result = scan_dataset(self.root)
        self.assertEqual(len(result.records), 1)
        self.assertIn('symlink_skipped', self.codes(result))
        with self.assertRaises(ValueError):
            build_plan(result)

    def test_tampered_fix_plan_rejected(self):
        self.image('train/images/a.png', label='0 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2')
        result = scan_dataset(self.root)
        plan = build_plan(result)
        plan.actions[0].path = '../escape.txt'
        with self.assertRaises(ValueError):
            write_clean_copy(result, plan, self.base / 'copy')

    def test_report_escaping_and_serialization(self):
        self.image('train/images/=formula.png', label=None)
        result = scan_dataset(self.root)
        result.issues[0].path = '=HYPERLINK("bad")'
        result.issues[0].message = '<script>alert(1)</script>'
        result.classes[0] = '<img src=x>'
        report = html_report(result)
        self.assertNotIn('<script>', report)
        self.assertIn('&lt;script&gt;', report)
        self.assertIn('&lt;img src=x&gt;', report)
        rows = list(csv.reader(io.StringIO(csv_report(result).lstrip('\ufeff'))))
        self.assertTrue(rows[1][2].startswith("'="))
        self.assertEqual(json.loads(json_report(result))['schema_version'], 1)

    def test_demo_matches_expected_findings(self):
        from scripts.create_demo import make_demo
        shutil.rmtree(self.root)
        make_demo(self.root)
        result = scan_dataset(self.root)
        self.assertEqual(result.counts['images'], 39)
        self.assertEqual(result.counts['errors'], 6)
        self.assertEqual(result.counts['annotations'], 42)
        self.assertEqual(result.counts['classes'], {'Safety-Helmet': 37, 'Reflective-Jacket': 5})
        self.assertTrue({'missing_label', 'missing_image', 'empty_label', 'duplicate_annotation', 'invalid_class', 'invalid_box', 'invalid_label', 'unreadable_image', 'duplicate_image', 'split_overlap', 'class_imbalance'} <= self.codes(result))


if __name__ == '__main__':
    unittest.main()
