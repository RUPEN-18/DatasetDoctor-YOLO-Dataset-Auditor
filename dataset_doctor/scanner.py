"""Auditing engine, independent of Qt. Source files are never modified."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import hashlib
import math
import os
import struct
import warnings

from PIL import Image
import yaml

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}
SPLITS = {'train': 'train', 'val': 'val', 'valid': 'val', 'validation': 'val', 'test': 'test'}
MAX_PIXELS = 40_000_000


class ScanCancelled(Exception):
    pass


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str
    line: int | None = None
    related: list[str] = field(default_factory=list)


@dataclass
class Annotation:
    line: int
    class_id: int
    box: list[float]


@dataclass
class ImageRecord:
    path: str
    label: str
    split: str
    width: int = 0
    height: int = 0
    digest: str = ''
    readable: bool = False
    label_exists: bool = False
    empty_label: bool = False
    annotations: list[Annotation] = field(default_factory=list)
    invalid_lines: list[int] = field(default_factory=list)
    duplicate_lines: list[int] = field(default_factory=list)


@dataclass
class ScanResult:
    root: str
    classes: list[str]
    records: list[ImageRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    label_paths: list[str] = field(default_factory=list)
    duplicate_groups: list[list[str]] = field(default_factory=list)
    overlap_groups: list[list[str]] = field(default_factory=list)
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration: float = 0.0
    # SHA256 of every audited image/label/config; used to reject stale fix plans.
    fingerprints: dict[str, str] = field(default_factory=dict)

    @property
    def counts(self) -> dict:
        annotations = Counter(a.class_id for r in self.records for a in r.annotations)
        return {
            'images': len(self.records), 'labels': len(self.label_paths),
            'readable': sum(r.readable for r in self.records),
            'backgrounds': sum(r.empty_label for r in self.records),
            'annotations': sum(annotations.values()),
            'errors': sum(i.severity == 'error' for i in self.issues),
            'warnings': sum(i.severity == 'warning' for i in self.issues),
            'reviews': sum(i.severity == 'review' for i in self.issues),
            'duplicates': sum(len(g) - 1 for g in self.duplicate_groups),
            'overlap_groups': len(self.overlap_groups),
            'classes': {name: annotations[n] for n, name in enumerate(self.classes)},
            'splits': dict(Counter(r.split for r in self.records)),
        }

    @property
    def health(self) -> int:
        # Affected-image ratio, not a model-quality or accuracy prediction.
        if not self.records:
            return 0
        affected = set()
        paths = {r.path for r in self.records}
        label_map = {r.label: r.path for r in self.records}
        for i in self.issues:
            if i.severity != 'error':
                continue
            for p in [i.path, *i.related]:
                if p in paths:
                    affected.add(p)
                if p in label_map:
                    affected.add(label_map[p])
        return round(100 * (len(paths) - len(affected)) / len(paths))

    def to_dict(self) -> dict:
        return {**asdict(self), 'counts': self.counts, 'health': self.health, 'schema_version': 1}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def label_for(path: Path) -> Path:
    parts = list(path.parts)
    positions = [n for n, part in enumerate(parts) if part.lower() == 'images']
    if positions:
        parts[positions[-1]] = 'labels'
    return Path(*parts).with_suffix('.txt')


def split_for(path: Path) -> str:
    for part in path.parts[:-1]:
        if part.lower() in SPLITS:
            return SPLITS[part.lower()]
    return 'unassigned'


def read_classes(root: Path) -> tuple[list[str], list[Issue], Path | None]:
    configs = [root / name for name in ('data.yaml', 'data.yml', 'dataset.yaml', 'dataset.yml') if (root / name).is_file()]
    if not configs:
        return [], [], None
    config = configs[0]
    issues = []
    if len(configs) > 1:
        issues.append(Issue('warning', 'multiple_configs', config.name, 'Multiple configs found; using ' + config.name))
    if config.is_symlink():
        return [], [Issue('error', 'config_error', config.name, 'Symbolic link configs are not followed.')], None
    try:
        if config.stat().st_size > 1024 * 1024:
            raise ValueError('Config exceeds the 1 MiB limit.')
        data = yaml.safe_load(config.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('Expected a YAML mapping.')
        names = data.get('names')
        if isinstance(names, dict):
            keys = list(names)
            if any(not isinstance(k, int) or isinstance(k, bool) for k in keys) or sorted(keys) != list(range(len(keys))):
                raise ValueError('Class name keys must be consecutive integers starting at 0.')
            names = [names[n] for n in range(len(keys))]
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            raise ValueError('names must be a non-empty list or an integer-keyed mapping of strings.')
        if len(set(names)) != len(names):
            raise ValueError('Class names must be unique.')
        if 'nc' in data and (type(data['nc']) is not int or data['nc'] != len(names)):
            issues.append(Issue('error', 'class_count_mismatch', config.name, 'nc does not match the number of class names.'))
        return names, issues, config
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [], [Issue('error', 'config_error', config.name, str(exc))], config


def parse_label(text: str, num_classes: int) -> tuple[list[Annotation], list[Issue], list[int], list[int]]:
    annotations, issues, invalid, duplicates = [], [], [], []
    seen = set()
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split()
        message, code = '', 'invalid_label'
        if len(fields) != 5:
            message = f'Expected 5 values (class x y width height); found {len(fields)}. Detection boxes only.'
        else:
            try:
                if not fields[0].isascii() or not fields[0].isdigit():
                    raise ValueError('Class ID must be a non-negative integer.')
                class_id = int(fields[0])
                if not 0 <= class_id < num_classes:
                    code = 'invalid_class'
                    raise ValueError(f'Class ID {class_id} is outside 0–{num_classes - 1}.')
                box = [float(v) for v in fields[1:]]
                if not all(math.isfinite(v) for v in box):
                    raise ValueError('Box coordinates must be finite numbers.')
                x, y, w, h = box
                code = 'invalid_box'
                if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                    raise ValueError('Centers must be in [0,1]; width and height must be in (0,1].')
                if x - w / 2 < -1e-6 or y - h / 2 < -1e-6 or x + w / 2 > 1 + 1e-6 or y + h / 2 > 1 + 1e-6:
                    raise ValueError('Bounding box edges extend beyond the image.')
                key = (class_id, *box)
                if key in seen:
                    duplicates.append(line_number)
                    issues.append(Issue('warning', 'duplicate_annotation', '', 'Repeated class and identical box; excluded from instance counts.', line_number))
                else:
                    seen.add(key)
                    annotations.append(Annotation(line_number, class_id, box))
            except (ValueError, OverflowError) as exc:
                message = str(exc)
        if message:
            invalid.append(line_number)
            issues.append(Issue('error', code, '', message, line_number))
    return annotations, issues, invalid, duplicates


def scan_dataset(root: str | Path, classes: list[str] | None = None,
                 progress: Callable[[int, int, str], None] | None = None,
                 cancelled: Callable[[], bool] | None = None) -> ScanResult:
    import time
    started = time.monotonic()
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Choose an existing dataset directory.')
    names, config_issues, config = read_classes(root)
    if classes:
        if not all(n.strip() for n in classes) or len(set(classes)) != len(classes):
            raise ValueError('Override class names must be non-empty and unique.')
        names = classes
    if not names:
        raise ValueError('No usable class names found. Provide data.yaml with names, or enter class names in Settings.')
    result = ScanResult(str(root), names, issues=config_issues)
    if classes:
        result.issues.append(Issue('review', 'class_override', '.', 'Class names were supplied manually; verify their order matches the label IDs.'))
    def check_cancel():
        if cancelled and cancelled():
            raise ScanCancelled()
    def rel(p):
        return p.relative_to(root).as_posix()
    paths = []
    def walk_error(exc):
        name = str(exc.filename or root)
        result.issues.append(Issue('error', 'directory_unreadable', name, str(exc)))
    for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
        check_cancel()
        folders[:] = sorted(f for f in folders if f not in {'.git', '.venv', '__pycache__'} and not f.startswith('.'))
        for folder in list(folders):
            p = Path(directory) / folder
            if p.is_symlink():
                folders.remove(folder)
                result.issues.append(Issue('warning', 'symlink_skipped', rel(p), 'Symbolic link directory skipped.'))
        for name in sorted(files):
            p = Path(directory) / name
            if p.is_symlink():
                result.issues.append(Issue('warning', 'symlink_skipped', rel(p), 'Symbolic link file skipped.'))
            elif p.suffix.lower() in EXTENSIONS or p.suffix.lower() == '.txt':
                paths.append(p)
    images = [p for p in paths if p.suffix.lower() in EXTENSIONS and 'labels' not in [x.lower() for x in p.relative_to(root).parts[:-1]]]
    image_dirs = {p.parent for p in images}
    labels = [p for p in paths if p.suffix.lower() == '.txt' and ('labels' in [x.lower() for x in p.relative_to(root).parts[:-1]] or p.parent in image_dirs or p.parent == root) and p.name.lower() not in {'classes.txt', 'readme.txt', 'license.txt', 'requirements.txt'}]
    # Match case-insensitively for Windows portability; flag collisions instead of guessing.
    indexed = defaultdict(list)
    for p in images + labels:
        indexed[rel(p).casefold()].append(p)
    for group in indexed.values():
        if len(group) > 1:
            result.issues.append(Issue('error', 'case_collision', rel(group[0]), 'Paths differ only by case and collide on Windows.', related=[rel(p) for p in group[1:]]))
    label_index = defaultdict(list)
    for p in labels:
        label_index[rel(p).casefold()].append(p)
    result.label_paths = [rel(p) for p in labels]
    pair_counts = Counter(label_for(p.relative_to(root)).as_posix().casefold() for p in images)
    used_labels = set()
    hashes = defaultdict(list)
    for index, path in enumerate(images):
        check_cancel()
        relative = path.relative_to(root)
        expected = label_for(relative)
        matches = label_index.get(expected.as_posix().casefold(), [])
        label = matches[0] if len(matches) == 1 else root / expected
        rec = ImageRecord(rel(path), rel(label), split_for(relative), label_exists=len(matches) == 1)
        result.records.append(rec)
        if progress:
            progress(index + 1, len(images), rec.path)
        if pair_counts[expected.as_posix().casefold()] > 1:
            result.issues.append(Issue('error', 'ambiguous_pair', rec.path, 'Several images share one label stem. Rename and relabel them before fixes.', related=[rec.label]))
        try:
            result.fingerprints[rec.path] = file_hash(path)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as im:
                    if im.width * im.height > MAX_PIXELS:
                        raise ValueError('Image exceeds the 40 megapixel safety limit.')
                    im.verify()
                with Image.open(path) as im:
                    im.load()  # verify alone does not detect every truncated file.
                    rec.width, rec.height = im.size
                    pixels = im.convert('RGB')
                    h = hashlib.sha256(struct.pack('>II', *im.size))
                    for y in range(0, im.height, 256):
                        check_cancel()
                        h.update(pixels.crop((0, y, im.width, min(y + 256, im.height))).tobytes())
                    rec.digest = h.hexdigest()
                    rec.readable = True
                    hashes[rec.digest].append(rec)
        except ScanCancelled:
            raise
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            result.issues.append(Issue('error', 'unreadable_image', rec.path, f'Image could not be fully decoded: {exc}'))
        if not rec.label_exists:
            result.issues.append(Issue('warning', 'missing_label', rec.path, 'No unique matching label file. Unannotated images may be intentional backgrounds; review before training.', related=[expected.as_posix()]))
        else:
            used_labels.add(rec.label)
            try:
                result.fingerprints[rec.label] = file_hash(label)
                if label.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError('Label exceeds the 10 MiB limit.')
                content = label.read_text(encoding='utf-8-sig')
                rec.empty_label = not content.strip()
                if rec.empty_label:
                    result.issues.append(Issue('review', 'empty_label', rec.label, 'Empty label: valid YOLO background candidate. Confirm the image contains no target objects.'))
                rec.annotations, issues, rec.invalid_lines, rec.duplicate_lines = parse_label(content, len(names))
                for issue in issues:
                    issue.path = rec.label
                result.issues.extend(issues)
            except (OSError, UnicodeError, ValueError) as exc:
                result.issues.append(Issue('error', 'unreadable_label', rec.label, str(exc)))
    for label in labels:
        check_cancel()
        if rel(label) not in used_labels:
            result.issues.append(Issue('warning', 'missing_image', rel(label), 'Label has no unique matching image.'))
        if rel(label) not in result.fingerprints:
            try:
                result.fingerprints[rel(label)] = file_hash(label)
            except OSError as exc:
                result.issues.append(Issue('error', 'unreadable_label', rel(label), str(exc)))
    for group in hashes.values():
        if len(group) < 2:
            continue
        group_paths = [r.path for r in group]
        result.duplicate_groups.append(group_paths)
        result.issues.append(Issue('warning', 'duplicate_image', group_paths[0], f'{len(group)} images have identical decoded RGB pixels and dimensions.', related=group_paths[1:]))
        splits = {r.split for r in group} - {'unassigned'}
        if len(splits) > 1:
            result.overlap_groups.append(group_paths)
            result.issues.append(Issue('error', 'split_overlap', group_paths[0], 'Identical image content crosses dataset splits: ' + ', '.join(sorted(splits)), related=group_paths[1:]))
        signatures = {tuple(sorted((a.class_id, *a.box) for a in r.annotations)) for r in group if r.label_exists and not r.invalid_lines}
        if len(signatures) > 1:
            result.issues.append(Issue('warning', 'annotation_conflict', group_paths[0], 'Duplicate images have different valid annotations.', related=group_paths[1:]))
    instance_counts = Counter(a.class_id for r in result.records for a in r.annotations)
    counts = [instance_counts[c] for c in range(len(names))]
    for n, count in enumerate(counts):
        if count == 0:
            result.issues.append(Issue('warning', 'unused_class', '.', f'No valid instances for class {n}: {names[n]}.'))
    positive = [n for n in counts if n]
    if len(positive) > 1 and max(positive) / min(positive) >= 5:
        result.issues.append(Issue('warning', 'class_imbalance', '.', f'Most/least represented nonzero classes differ by {max(positive) / min(positive):.1f}× (review heuristic ≥5×).'))
    if not images:
        result.issues.append(Issue('error', 'no_images', '.', 'No supported images were discovered.'))
    elif any(r.split == 'unassigned' for r in result.records):
        result.issues.append(Issue('review', 'unassigned_split', '.', 'Some images have no conventional train/val/valid/test directory; overlap detection cannot infer their splits.'))
    if config:
        try:
            result.fingerprints[rel(config)] = file_hash(config)
        except OSError as exc:
            result.issues.append(Issue('error', 'config_error', rel(config), str(exc)))
    result.duration = time.monotonic() - started
    return result
