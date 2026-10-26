# Troubleshooting

## Windows setup

- Extract the entire ZIP before running scripts.
- Install 64-bit Python 3.11/3.12 and enable **Add Python to PATH**. Open a new terminal after installation.
- Run `setup_windows.bat` once with an active internet connection, then `run_app.bat`.
- `ModuleNotFoundError: PySide6`: setup did not finish, or you used a different Python interpreter. Run setup again, then launch using the provided script.
- `No matching distribution found`: check that your Python version, CPU architecture and OS have compatible PySide6 wheels. Try Python 3.11/3.12 in a fresh virtual environment.
- On a company network, blocked package downloads may require your network administrator's approved package source. Do not disable certificate verification.
- If you moved the project after setup, delete only the project's `.venv` and rerun setup. Virtual environments are not portable.
- Do not delete or modify your dataset to troubleshoot an application dependency problem.

## Qt platform / display errors

The GUI needs a graphical desktop. A headless terminal cannot display windows without a display server. For testing, use `QT_QPA_PLATFORM=offscreen`; for actual auditing without a desktop, use `python -m dataset_doctor.cli`.

On Linux, Qt may require OS-specific XCB/system libraries, such as `libxcb-cursor0`. Install the appropriate packages for your distribution. If OpenCV or another application sets Qt plugin environment variables, launch this project in its own fresh environment.

## No usable class names

Select the dataset root containing `data.yaml`. Check that it contains `names`, for example:

```yaml
nc: 2
names:
  - Safety-Helmet
  - Reflective-Jacket
train: train/images
val: valid/images
```

You can instead enter class names in **Settings & help** and rescan. The order must match your annotation IDs. Overrides do not change source YAML.

## Large datasets

All images are fully decoded to validate them and compute pixel fingerprints; this is intentionally more thorough than reading filenames. Larger files take longer, even on a fast CPU. Work is processed one image at a time with a background worker. Use Cancel to stop after the current file. Image records and findings remain in memory, so very large datasets or labels may require more RAM. There is no claimed million-image performance target.

Images larger than 40 megapixels, YAML larger than 1 MiB and labels larger than 10 MiB are flagged instead of processed. The default limits are defined in `scanner.py`.

## Labels marked invalid

This app supports axis-aligned YOLO detection rows with five fields. Segmentation polygons, OBB, pose and classification labels need their own validators. Convert them intentionally rather than using Discard invalid rows to remove them.

## Duplicate content still present after a fix

Automatic fixes change labels only. Duplicate images and split overlap need a deliberate decision about which files to keep. Dataset Doctor does not silently choose an evaluation split or delete training samples.

## Creating a copy failed

- Use a new output path outside the source dataset. Existing folders are rejected.
- Resolve ambiguous image stems, case collisions, symlinks, unreadable label files and unreadable directories first.
- If source files or metadata changed after the audit, rescan before generating a new plan.
- The copy may retain a corrupted image: image repair is outside the automatic operations. Review all remaining issues.
- Check output disk space; all audited image and label bytes must fit.
- Generated YAML omits the `path` key and has relative directories. Pass its absolute filename to the training framework and check the resolved paths. Unassigned/missing splits need manual setup.

## GUI validation status

Read `docs/VALIDATION.md` for the actual checks run in the build environment. The smoke-check script can be used on your PC after dependency installation.
