"""Headless auditing; does not import PySide6."""
from __future__ import annotations
from pathlib import Path
import argparse
import sys
from .scanner import scan_dataset
from .exports import csv_report, html_report, json_report
from .fixes import build_plan, write_clean_copy


def main(argv=None):
    parser = argparse.ArgumentParser(description='Dataset Doctor — audit YOLO detection datasets without a GUI')
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--classes', help='Comma-separated names in class-ID order; overrides YAML')
    parser.add_argument('--report', type=Path, help='New JSON, HTML or CSV report path outside the source dataset')
    parser.add_argument('--clean-copy', type=Path, help='New output dataset folder; removes duplicate annotation rows only')
    args = parser.parse_args(argv)
    try:
        result = scan_dataset(args.dataset, args.classes.split(',') if args.classes else None)
        c = result.counts
        print(f'Dataset Doctor | {Path(result.root).name}')
        print(f'{c["images"]} images | {c["annotations"]} valid instances | {c["errors"]} errors | {c["warnings"]} warnings | {c["reviews"]} review items')
        for name, count in c['classes'].items():
            print(f'  {name}: {count}')
        if args.report:
            target = args.report.expanduser().resolve()
            kind = target.suffix.lower().lstrip('.')
            if kind not in {'html', 'json', 'csv'}:
                raise ValueError('Report extension must be .html, .json or .csv.')
            if target.is_relative_to(Path(result.root)):
                raise ValueError('Reports must be saved outside the source dataset.')
            # Exclusive creation avoids accidental overwrites in scripts.
            with target.open('x', encoding='utf-8') as stream:
                stream.write({'json': json_report, 'csv': csv_report, 'html': html_report}[kind](result))
            print(f'Report: {target}')
        if args.clean_copy:
            plan = build_plan(result)
            print('Planned changes:')
            for action in plan.actions:
                print(f'  {action.path}: remove rows {action.lines}')
            path = write_clean_copy(result, plan, args.clean_copy)
            print(f'Separate dataset copy: {path}. Rescan and review remaining issues.')
        return 1 if c['errors'] else 0
    except (ValueError, OSError) as exc:
        print(f'Dataset Doctor: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
