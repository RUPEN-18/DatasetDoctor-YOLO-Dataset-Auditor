# Validation of this release

## Checks completed in the build environment

- **25 standard-library regression tests passed** with Python 3.12, Pillow and PyYAML.
- All Python sources passed compilation using `python -m compileall`.
- The demo audited as expected: 39 images, 42 valid instances, 6 errors, 6 warnings, 1 review item; class counts 37 / 5.
- The CLI produced a structured JSON audit and a standalone HTML report.
- Regression checks cover invalid IDs/boxes, malformed rows, class metadata, nested layouts, corrupt/truncated images, decoded-pixel duplicates, cross-split overlap, annotation conflicts, class imbalance, empty backgrounds, cancellation, unchanged originals, stale source/config rejection, copy cleanup, output path protection, explicit background creation, tampered-plan rejection, symlink exclusion and report escaping.

## Windows usage evidence

User-supplied screenshots from 26 October 2026 show the application running on Windows: the populated overview, image inspector with bounding boxes, fix workspace and report export screen. The overview reports 1,389 images, 27,933 valid annotation instances, 11 errors and 74 warnings. These are visual evidence of runtime use, not a complete end-to-end test of every operation. The screenshots are included in `assets/screenshots/`.

## Build-environment GUI execution status

The PySide6 desktop UI was implemented and syntax-checked, but **was not launched or visually verified in this build environment**. The environment blocked PyPI downloads with HTTP 403, and PySide6 was not preinstalled. No automated GUI smoke-test pass is claimed. The screenshots above were supplied from a separate Windows run.

After running `setup_windows.bat` on your PC, launch `run_app.bat` and click **Try demo**. The optional `scripts/verify_ui.py` exercises all six pages, filters, box preview, fix-plan invalidation and a worker scan, and saves real window captures. This script is included for verification; it was not run successfully here due to the missing Qt dependency.

The ZIP is a source release, not a prebuilt executable. The screenshots demonstrate that the UI launched on Windows; automated UI checks, launcher behavior and each native folder-dialog operation were not independently verified in the build environment.
