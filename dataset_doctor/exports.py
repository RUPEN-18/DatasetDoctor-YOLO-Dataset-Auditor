"""Portable, escaped report generation; no network resources."""
from __future__ import annotations
from collections import Counter
import csv
import html
import io
import json
from .scanner import ScanResult


def json_report(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


def safe_cell(value):
    text = str(value if value is not None else '')
    # Prevent spreadsheet applications interpreting dataset-controlled values as formulas.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def csv_report(result: ScanResult) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['severity', 'check', 'path', 'line', 'message', 'related_files'])
    for issue in result.issues:
        writer.writerow(map(safe_cell, [issue.severity, issue.code, issue.path, issue.line, issue.message, '; '.join(issue.related)]))
    return '\ufeff' + stream.getvalue()


def html_report(result: ScanResult) -> str:
    esc = lambda value: html.escape(str(value))
    c = result.counts
    cards = ''.join(f'<article><b>{c[key]:,}</b><span>{label}</span></article>' for key, label in [('images','Images'),('annotations','Valid instances'),('errors','Errors'),('warnings','Warnings'),('reviews','Review items')])
    rows = ''.join(f'<tr><td><em class="{i.severity}">{esc(i.severity)}</em></td><td>{esc(i.code)}</td><td>{esc(i.path)}{":" + str(i.line) if i.line else ""}</td><td>{esc(i.message)}<small>{esc(" · ".join(i.related))}</small></td></tr>' for i in result.issues)
    dist = ''.join(f'<tr><td>{n}</td><td>{esc(name)}</td><td>{c["classes"][name]:,}</td></tr>' for n, name in enumerate(result.classes))
    splits = ', '.join(f'{esc(k)}: {v:,}' for k, v in c['splits'].items())
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dataset Doctor · Audit report</title>
<style>body{{font:15px system-ui;background:#f3f6fa;color:#172438;margin:0}}main{{max-width:1180px;margin:48px auto;padding:0 28px}}h1{{font-size:36px;margin-bottom:4px}}.eyebrow{{color:#088976;font-weight:700;letter-spacing:2px}}p,small{{color:#627086}}.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:30px 0}}article{{background:white;border:1px solid #e0e6ee;border-radius:12px;padding:22px;min-width:130px}}b{{display:block;font-size:30px}}span,small{{display:block}}table{{border-collapse:collapse;width:100%;background:white;margin:18px 0 36px}}th,td{{text-align:left;padding:14px;border-bottom:1px solid #e7edf3;vertical-align:top;overflow-wrap:anywhere}}th{{background:#eaf0f6}}em{{font-style:normal;font-weight:700}}.error{{color:#cf4058}}.warning{{color:#ab6a02}}.review{{color:#087d86}}button{{float:right;border:0;background:#0b887a;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}}@media print{{button{{display:none}}main{{margin:10px}}body{{background:white}}tr{{break-inside:avoid}}}}</style>
<main><button onclick="window.print()">Print / Save PDF</button><div class="eyebrow">DATASET DOCTOR / AUDIT REPORT</div><h1>{esc(__import__('pathlib').Path(result.root).name)}</h1><p>{esc(result.root)}<br>{esc(result.scanned_at)} · {result.duration:.2f}s · YOLO detection</p><div class="cards">{cards}</div>
<h2>{result.health}% of discovered images free of recorded errors</h2><p>This is a structural check, not a training readiness score or model-accuracy estimate. Dataset-level errors, warnings and review items still require attention. Counts exclude invalid and repeated annotation rows.</p><p>Splits: {splits or 'none'}<br>Duplicates: {c['duplicates']} extra copies · Cross-split duplicate groups: {c['overlap_groups']}</p>
<h2>Class distribution</h2><table><tr><th>ID</th><th>Class</th><th>Valid instances</th></tr>{dist}</table>
<h2>Issues ({len(result.issues):,})</h2><table><tr><th>Severity</th><th>Check</th><th>File / line</th><th>Finding</th></tr>{rows or '<tr><td colspan="4">No issues detected by the supported checks.</td></tr>'}</table>
<p>Duplicate detection compares decoded RGB pixels and dimensions. Re-encoded JPEGs, near duplicates and semantic annotation mistakes may go undetected. Split names come from directory names, not YAML manifests. Fixes require human review.</p></main></html>'''
