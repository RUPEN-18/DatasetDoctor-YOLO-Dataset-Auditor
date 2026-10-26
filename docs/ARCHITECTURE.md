# Architecture

The PySide6 desktop shell calls a Python engine with no GUI dependencies. The CLI uses the same engine and report functions.

| Component | Responsibility |
|---|---|
| `scanner.py` | Read class metadata; discover local files; pair relative stems; validate labels; verify/decode images; build pixel hashes; aggregate findings |
| `fixes.py` | Build declarative label changes; verify scan fingerprints; copy to temporary output; apply reviewed rows; generate YAML and manifest; publish a new output directory |
| `exports.py` | Escape and serialize the scan result into standalone HTML, formula-safe CSV and JSON |
| `widgets.py` | Draw class bars, split donut and image/box overlays |
| `theme.py` | Shared color, typography, card, navigation, input and table styles |
| `app.py` | Navigation, filtering, worker progress, cancellation, file dialogs and fix confirmation |
| `cli.py` | Reusable headless audit and default cleaned-copy operation |

## Data flow

1. The user selects a root and optional ordered class names.
2. A worker runs `scan_dataset`, reporting progress and polling cancellation.
3. The returned `ScanResult` drives every view and export.
4. The fix workspace derives a `FixPlan` and displays exact label paths and line numbers.
5. An export worker verifies fingerprints, copies audited files, changes labels only in staging and renames staging to a new destination.
6. The user audits the output as a separate dataset.

Images are processed individually; pixel hashes are grouped in a dictionary, avoiding an all-pairs duplicate comparison. The GUI's list/table views retain records in memory. This is a practical local tool, not a distributed data service.

## Important decisions

- An empty label is a background review item. A missing label is a warning because YOLO datasets can intentionally omit background labels.
- All box edges must fit the image, with a `1e-6` tolerance for normalized coordinate rounding.
- Duplicate annotation equality uses the parsed class ID and floating-point coordinate values. Different textual spellings of the same numbers match.
- Pixel duplication hashes dimension-prefixed, decoded first-frame RGB pixels. EXIF rotation is not applied because annotations refer to raw coordinates. Alpha is ignored. Near duplicates and JPEG re-encodings need other techniques.
- Unknown split directories remain `unassigned`. YAML manifests and external paths are deliberately not executed or traversed.
- Configuration uses `yaml.safe_load`; any YAML download hooks are ignored.
- Report text is HTML-escaped; CSV fields beginning with spreadsheet formula prefixes are escaped.
- Source data is not opened for writing. Reports are saved outside it. A cleaned copy always has a new destination and contains a fix manifest.
- Audit fingerprints protect against stale source changes; they are not a substitute for an OS-level snapshot under concurrent writers. Avoid editing the dataset while auditing/exporting.
