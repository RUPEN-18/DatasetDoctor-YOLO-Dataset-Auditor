"""Reviewable label-only changes in a new, atomic dataset copy."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
import json
import os
import shutil
import tempfile
import yaml
from .scanner import ScanResult, ScanCancelled, file_hash


@dataclass
class FixAction:
    path: str
    operation: str
    lines: list[int]
    explanation: str


@dataclass
class FixPlan:
    actions: list[FixAction]
    remove_duplicates: bool
    drop_invalid: bool
    create_backgrounds: bool


def build_plan(result: ScanResult, remove_duplicates=True, drop_invalid=False, create_backgrounds=False) -> FixPlan:
    blocked = {'ambiguous_pair', 'case_collision', 'directory_unreadable', 'unreadable_label', 'symlink_skipped'}
    if any(i.code in blocked for i in result.issues):
        raise ValueError('Resolve ambiguous paths, symbolic links, unreadable labels or directories before creating a cleaned copy.')
    actions = []
    done = set()
    for record in result.records:
        if record.label in done:
            continue
        done.add(record.label)
        lines = sorted(set((record.duplicate_lines if remove_duplicates else []) + (record.invalid_lines if drop_invalid else [])))
        if lines:
            actions.append(FixAction(record.label, 'remove_rows', lines, 'Remove only the listed annotation lines. Other rows are preserved.'))
        elif not record.label_exists and create_backgrounds:
            actions.append(FixAction(record.label, 'create_background', [], 'Create an empty label: explicitly treats the image as background.'))
    return FixPlan(actions, remove_duplicates, drop_invalid, create_backgrounds)


def _safe_child(root: Path, relative: str) -> Path:
    child = root / relative
    if Path(relative).is_absolute() or not child.resolve().is_relative_to(root.resolve()):
        raise ValueError('Unsafe dataset-relative path.')
    return child


def write_clean_copy(result: ScanResult, plan: FixPlan, destination: str | Path,
                     progress: Callable[[int, int, str], None] | None = None,
                     cancelled: Callable[[], bool] | None = None) -> Path:
    root = Path(result.root).resolve()
    destination = Path(destination).expanduser().resolve()
    if destination == root or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('Choose a new output folder outside the source dataset.')
    if destination.exists():
        raise ValueError('Output folder already exists. Choose a new folder name; nothing will be overwritten.')
    # Rebuild the plan from the scan rather than trusting caller-supplied paths or line numbers.
    canonical = build_plan(result, plan.remove_duplicates, plan.drop_invalid, plan.create_backgrounds)
    if canonical != plan:
        raise ValueError('Fix plan does not match the scan.')
    for record in result.records:
        if not record.label_exists and (root / record.label).exists():
            raise ValueError(f'A previously missing label now exists: {record.label}. Rescan.')
    files = sorted(set([r.path for r in result.records] + result.label_paths))
    if any(p not in result.fingerprints for p in files):
        raise ValueError('Some source files could not be read. Resolve them and rescan before copying.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.dataset-doctor-', dir=destination.parent))
    def check_cancel():
        if cancelled and cancelled():
            raise ScanCancelled()
    try:
        for n, relative in enumerate(files, 1):
            check_cancel()
            source = _safe_child(root, relative)
            if source.is_symlink() or not source.is_file() or file_hash(source) != result.fingerprints[relative]:
                raise ValueError(f'Source changed since scan: {relative}. Rescan before exporting fixes.')
            target = _safe_child(staging, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if file_hash(target) != result.fingerprints[relative]:
                raise ValueError(f'Source changed while copying: {relative}. Rescan.')
            if progress:
                progress(n, len(files), relative)
        # Config also participates in staleness protection, even though it is regenerated.
        for relative, digest in result.fingerprints.items():
            if relative not in files and file_hash(_safe_child(root, relative)) != digest:
                raise ValueError(f'Configuration changed since scan: {relative}. Rescan.')
        for action in plan.actions:
            check_cancel()
            target = _safe_child(staging, action.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if action.operation == 'create_background':
                if target.exists():
                    raise ValueError('Background target unexpectedly exists.')
                target.write_text('', encoding='utf-8')
            else:
                rows = target.read_text(encoding='utf-8-sig').splitlines()
                keep = [row for n, row in enumerate(rows, 1) if n not in action.lines]
                target.write_text('\n'.join(keep) + ('\n' if keep else ''), encoding='utf-8')
        config = {'nc': len(result.classes), 'names': result.classes}
        for split in ('train', 'val', 'test'):
            parents = sorted({str(Path(r.path).parent).replace('\\', '/') for r in result.records if r.split == split}, key=len)
            minimal = []
            for parent in parents:
                if not any(Path(parent).is_relative_to(Path(p)) for p in minimal):
                    minimal.append(parent)
            if minimal:
                config[split] = minimal[0] if len(minimal) == 1 else minimal
        (staging / 'data.yaml').write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding='utf-8')
        meta = staging / '.dataset_doctor'
        meta.mkdir(exist_ok=True)
        (meta / 'fix_manifest.json').write_text(json.dumps({'source': result.root, 'scan_time': result.scanned_at, 'actions': [asdict(a) for a in plan.actions], 'notes': ['Use the absolute path to this data.yaml when training; split paths are relative to this file.', 'Only audited images and labels were copied. Other source metadata is not copied.', 'data.yaml was regenerated with relative directories and the audited class names.', 'Unassigned splits need manual configuration. Duplicate images and remaining issues were retained.']}, indent=2), encoding='utf-8')
        check_cancel()
        if destination.exists():
            raise ValueError('Output folder appeared while exporting. Choose another destination.')
        os.rename(staging, destination)
        return destination
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
