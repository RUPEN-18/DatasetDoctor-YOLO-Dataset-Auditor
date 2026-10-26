"""Real Qt smoke checks and captures. Requires installed GUI dependencies.
Run from the project: QT_QPA_PLATFORM=offscreen python scripts/verify_ui.py
"""
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print('PySide6 is unavailable. Install requirements.txt before running the GUI smoke check.', file=sys.stderr)
        return 2
    from dataset_doctor.app import MainWindow
    from dataset_doctor.scanner import scan_dataset
    from dataset_doctor.fixes import build_plan, write_clean_copy

    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    errors = []
    def exception_hook(kind, value, tb):
        errors.append(str(value))
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = exception_hook
    result = scan_dataset(ROOT / 'demo_dataset')
    window.scan_finished(result)
    captures = ROOT / 'ui_captures'
    captures.mkdir(exist_ok=True)
    for index, name in enumerate(['overview', 'issues', 'inspector', 'fixes', 'reports', 'settings']):
        window.go(index)
        if index == 1:
            window.issue_table.selectRow(0)
        if index == 2:
            # A jacket example is visually useful for a two-class overlay.
            for n, rec in enumerate(window.image_rows):
                if rec.path.endswith('site_007.png'):
                    window.image_list.setCurrentRow(n)
                    break
        if index == 3:
            window.preview_fixes()
        app.processEvents()
        pixmap = window.grab()
        assert not pixmap.isNull(), f'No rendered window for {name}'
        assert pixmap.save(str(captures / f'{name}.png')), f'Cannot save {name} capture'
    window.go(1)
    window.severity_filter.setCurrentText('Error')
    assert len(window.issue_rows) == 6
    window.issue_search.setText('split_overlap')
    assert len(window.issue_rows) == 1
    window.issue_table.selectRow(0)
    window.inspect_issue()
    assert window.pages.currentIndex() == 2
    window.image_search.setText('no-such-image')
    assert not window.image_rows
    assert window.canvas.pixmap.isNull()
    window.image_search.clear()
    window.go(3)
    window.drop_invalid.setChecked(True)
    assert window.plan is None
    window.preview_fixes()
    assert window.plan and len(window.plan.actions) == 5
    with tempfile.TemporaryDirectory() as temp:
        target = write_clean_copy(result, window.plan, Path(temp) / 'copy')
        assert target.exists()
    window.start_scan(ROOT / 'demo_dataset')
    deadline = time.monotonic() + 30
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.worker is None, 'Scan worker did not finish in 30 seconds'
    assert window.result.counts['images'] == 39
    assert not errors, 'Qt callback errors: ' + '; '.join(errors)
    window.close()
    print('GUI smoke check passed. Captures:', captures)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
