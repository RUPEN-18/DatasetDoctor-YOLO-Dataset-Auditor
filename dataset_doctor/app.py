"""Dataset Doctor desktop UI. Run with python main.py."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from . import __version__
from .scanner import ScanCancelled, scan_dataset
from .fixes import build_plan, write_clean_copy
from .exports import csv_report, html_report, json_report
from .theme import STYLE
from .widgets import DistributionChart, ImageCanvas, SplitChart

PROJECT = Path(__file__).resolve().parent.parent


def label(text, role='', wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(role)
    item.setWordWrap(wrap)
    if wrap:
        item.setMinimumWidth(0)
    return item


def button(text, callback=None, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName('primary')
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        item.clicked.connect(callback)
    return item


def row(*widgets, stretch=False):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch:
        layout.addStretch()
    return container


def card(title=None, subtitle=None):
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, 'section'))
    if subtitle:
        layout.addWidget(label(subtitle, 'muted', True))
    return frame, layout


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.setAlternatingRowColors(True)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.setShowGrid(False)
    widget.verticalHeader().setDefaultSectionSize(42)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def set_row(widget, index, values):
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setToolTip(str(value))
        if column == 0 and str(value).lower() in {'error', 'warning', 'review'}:
            item.setForeground(QColor({'error': '#d34b63', 'warning': '#b97a17', 'review': '#198e8b'}[str(value).lower()]))
        widget.setItem(index, column, item)


class Worker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            answer = self.fn(self.progress.emit, self.isInterruptionRequested)
            self.completed.emit(answer)
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    TITLES = ['Dataset overview', 'Issue explorer', 'Image inspector', 'Fix workspace', 'Export reports', 'Settings & help']
    SUBTITLES = ['A clear picture of your data, before the first epoch.', 'Find the file, understand the problem, decide the next step.', 'Inspect your images and valid bounding boxes side by side.', 'Preview every label change. Save a separate dataset copy.', 'Take your findings into a browser, spreadsheet or script.', 'A local workflow for YOLO object-detection datasets.']

    def __init__(self):
        super().__init__()
        self.result = None
        self.worker = None
        self.plan = None
        self.issue_rows = []
        self.image_rows = []
        self.last_output = None
        self.setWindowTitle('Dataset Doctor — YOLO Dataset Auditor')
        self.resize(1440, 940)
        self.setMinimumSize(1160, 760)
        icon = PROJECT / 'assets' / 'icon.png'
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(STYLE)
        shell = QWidget()
        shell.setObjectName('shell')
        self.setCentralWidget(shell)
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.make_sidebar())
        content = QWidget()
        self.content = QVBoxLayout(content)
        self.content.setContentsMargins(32, 28, 32, 20)
        self.content.setSpacing(18)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        titles.addWidget(label('DATASET INTELLIGENCE  /  YOLO DETECTION', 'eyebrow'))
        self.title = label(self.TITLES[0], 'title')
        titles.addWidget(self.title)
        self.subtitle = label(self.SUBTITLES[0], 'muted')
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.demo_button = button('Try demo', self.load_demo)
        self.open_button = button('Open dataset', self.choose_dataset, True)
        header.addWidget(self.demo_button)
        header.addWidget(self.open_button)
        self.content.addLayout(header)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.make_overview())
        self.pages.addWidget(self.make_issues())
        self.pages.addWidget(self.make_inspector())
        self.pages.addWidget(self.make_fixes())
        self.pages.addWidget(self.make_exports())
        self.pages.addWidget(self.make_settings())
        self.content.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        self.status = label('Ready · Open a dataset, or explore the bundled demo.', 'muted')
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(190)
        self.progress.hide()
        self.cancel_button = button('Cancel', self.cancel_work)
        self.cancel_button.hide()
        footer.addWidget(self.status, 1)
        footer.addWidget(self.progress)
        footer.addWidget(self.cancel_button)
        footer.addWidget(label('OFFLINE  •  CPU ONLY', 'eyebrow'))
        self.content.addLayout(footer)
        layout.addWidget(content, 1)
        self.setAcceptDrops(True)
        self.go(0)

    def make_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(216)
        box = QVBoxLayout(sidebar)
        box.setContentsMargins(20, 29, 20, 24)
        box.setSpacing(9)
        mark = label('✚', 'brand')
        mark.setStyleSheet('color:#69dfbc; font-size:38px;')
        box.addWidget(mark)
        box.addWidget(label('Dataset Doctor', 'brand'))
        box.addWidget(label('Healthy data. Better starts.', 'brandSub'))
        box.addSpacing(35)
        box.addWidget(label('WORKSPACE', 'navLabel'))
        self.nav = []
        for n, title in enumerate(['Overview', 'Issues', 'Image inspector', 'Fix workspace', 'Reports']):
            b = button(f'{n+1:02}    {title}', lambda checked=False, index=n: self.go(index))
            b.setObjectName('nav')
            b.setCheckable(True)
            self.nav.append(b)
            box.addWidget(b)
        box.addStretch()
        box.addWidget(label('ACTIVE DATASET', 'navLabel'))
        self.dataset_name = label('No dataset selected', 'brandSub', True)
        box.addWidget(self.dataset_name)
        self.rescan_button = button('Rescan dataset', self.rescan)
        self.rescan_button.setObjectName('sidebarAction')
        self.rescan_button.setEnabled(False)
        box.addWidget(self.rescan_button)
        box.addSpacing(20)
        settings = button('06    Settings & help', lambda: self.go(5))
        settings.setObjectName('nav')
        settings.setCheckable(True)
        self.nav.append(settings)
        box.addWidget(settings)
        box.addWidget(label(f'VERSION {__version__}  /  LOCAL FIRST', 'brandSub'))
        return sidebar

    def go(self, n):
        self.pages.setCurrentIndex(n)
        self.title.setText(self.TITLES[n])
        self.subtitle.setText(self.SUBTITLES[n])
        for i, b in enumerate(self.nav):
            b.setChecked(i == n)

    def make_overview(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        banner = QFrame()
        banner.setObjectName('banner')
        bar = QHBoxLayout(banner)
        bar.setContentsMargins(20, 17, 20, 17)
        info = QVBoxLayout()
        self.banner_title = label('Good models start with healthy data.', 'bannerTitle')
        self.banner_note = label('Select your YOLO dataset folder to run a read-only audit.', 'muted', True)
        info.addWidget(self.banner_title)
        info.addWidget(self.banner_note)
        bar.addLayout(info, 1)
        bar.addWidget(button('View issues  →', lambda: self.go(1)))
        box.addWidget(banner)
        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        self.metric_values = []
        self.metric_notes = []
        for name, note in [('TOTAL IMAGES', 'Across every discovered split'), ('VALID INSTANCES', 'Unique, valid annotation rows'), ('ERRORS', 'Structural issues to investigate'), ('REVIEW ITEMS', 'Backgrounds and audit notes')]:
            frame, lay = card()
            lay.setSpacing(9)
            lay.addWidget(label(name, 'eyebrow'))
            value = label('—', 'metric')
            lay.addWidget(value)
            sub = label(note, 'muted', True)
            lay.addWidget(sub)
            self.metric_values.append(value)
            self.metric_notes.append(sub)
            metrics.addWidget(frame, 1)
        box.addLayout(metrics)
        charts = QHBoxLayout()
        charts.setSpacing(16)
        left, lay = card('Class distribution', 'Valid instances · duplicate annotation rows counted once')
        self.class_chart = DistributionChart()
        lay.addWidget(self.class_chart, 1)
        right, lay = card('Dataset splits', 'Directory-based split assignment')
        self.split_chart = SplitChart()
        lay.addWidget(self.split_chart, 1)
        charts.addWidget(left, 1)
        charts.addWidget(right, 1)
        box.addLayout(charts, 1)
        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        focus, lay = card('What needs attention', 'Most frequent findings in this audit')
        self.top_issues = QLabel('Your audit findings will appear here.\n\nTry the demo dataset for an example with known issues.')
        self.top_issues.setWordWrap(True)
        self.top_issues.setStyleSheet('color:#60758b; line-height:1.7;')
        lay.addWidget(self.top_issues, 1)
        quality, lay = card('Structural health', 'Images without recorded image or label errors')
        self.health_label = label('—', 'metric')
        lay.addWidget(self.health_label)
        self.health_note = label('A structural indicator, not a model accuracy prediction. Warnings and dataset-level errors still need attention.', 'muted', True)
        lay.addWidget(self.health_note)
        bottom.addWidget(focus, 1)
        bottom.addWidget(quality, 1)
        box.addLayout(bottom)
        box.addWidget(label('SOURCE PROTECTION  ·  Audits never edit source files. Fixes are written into a new folder.', 'muted'))
        scroll.setWidget(page)
        return scroll

    def make_issues(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        self.issue_search = QLineEdit()
        self.issue_search.setPlaceholderText('Search file paths, messages or check names…')
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(['All severities', 'Error', 'Warning', 'Review'])
        self.code_filter = QComboBox()
        self.code_filter.addItem('All checks')
        self.issue_split_filter = QComboBox()
        self.issue_split_filter.addItems(['All splits', 'train', 'val', 'test', 'unassigned', 'dataset-level'])
        box.addWidget(row(self.issue_search, self.severity_filter, self.code_filter, self.issue_split_filter))
        self.issue_count = label('Run an audit to explore its findings.', 'muted')
        box.addWidget(self.issue_count)
        self.issue_table = table(['SEVERITY', 'CHECK', 'FILE', 'LINE', 'FINDING'])
        for n, w in enumerate([90, 170, 260, 55]):
            self.issue_table.setColumnWidth(n, w)
        self.issue_table.itemSelectionChanged.connect(self.show_issue_detail)
        self.issue_table.cellDoubleClicked.connect(lambda *_: self.inspect_issue())
        box.addWidget(self.issue_table, 1)
        frame, lay = card('Finding details')
        self.issue_detail = label('Select a finding to see its details and related files.', 'muted', True)
        self.issue_detail.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.issue_detail)
        lay.addWidget(button('Inspect related image  →', self.inspect_issue), 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(frame)
        for w in [self.issue_search]:
            w.textChanged.connect(self.filter_issues)
        for w in [self.severity_filter, self.code_filter, self.issue_split_filter]:
            w.currentTextChanged.connect(self.filter_issues)
        return page

    def make_inspector(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter()
        left = QWidget()
        leftbox = QVBoxLayout(left)
        leftbox.setContentsMargins(0, 0, 0, 0)
        self.image_search = QLineEdit()
        self.image_search.setPlaceholderText('Search images…')
        self.image_split = QComboBox()
        self.image_split.addItems(['All splits', 'train', 'val', 'test', 'unassigned'])
        leftbox.addWidget(self.image_search)
        leftbox.addWidget(self.image_split)
        self.image_count = label('0 images', 'muted')
        leftbox.addWidget(self.image_count)
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self.show_image)
        leftbox.addWidget(self.image_list, 1)
        splitter.addWidget(left)
        right = QWidget()
        rightbox = QVBoxLayout(right)
        rightbox.setContentsMargins(0, 0, 0, 0)
        self.image_title = label('Image preview', 'section')
        self.box_toggle = QCheckBox('Show bounding boxes')
        self.box_toggle.setChecked(True)
        self.box_toggle.toggled.connect(self.toggle_boxes)
        rightbox.addWidget(row(self.image_title, self.box_toggle))
        self.canvas = ImageCanvas()
        rightbox.addWidget(self.canvas, 1)
        self.image_meta = label('Valid detection boxes are overlaid in class colors.', 'muted', True)
        self.image_meta.setTextFormat(Qt.TextFormat.PlainText)
        rightbox.addWidget(self.image_meta)
        self.annotation_table = table(['CLASS ID', 'CLASS NAME', 'X / Y', 'WIDTH / HEIGHT', 'LINE'])
        self.annotation_table.setMaximumHeight(190)
        self.annotation_table.setColumnWidth(1, 170)
        rightbox.addWidget(self.annotation_table)
        splitter.addWidget(right)
        splitter.setSizes([270, 800])
        splitter.setStretchFactor(1, 1)
        box.addWidget(splitter)
        self.image_search.textChanged.connect(self.filter_images)
        self.image_split.currentTextChanged.connect(self.filter_images)
        return page

    def make_fixes(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        frame, lay = card('Choose label operations', 'Duplicate images, split overlap and semantic label mistakes require manual review. They are retained in the copy.')
        self.remove_duplicate_rows = QCheckBox('Remove repeated annotation rows (identical class and box)')
        self.remove_duplicate_rows.setChecked(True)
        self.drop_invalid = QCheckBox('Discard invalid label rows — removes annotations and may leave background images')
        self.create_background = QCheckBox('Create empty labels for missing files — only after confirming those images are backgrounds')
        for w in [self.remove_duplicate_rows, self.drop_invalid, self.create_background]:
            lay.addWidget(w)
            w.toggled.connect(self.invalidate_plan)
        self.preview_button = button('Generate fix preview', self.preview_fixes)
        lay.addWidget(self.preview_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(frame)
        self.fix_summary = label('Generate a preview to see the exact files and line numbers that would change.', 'muted', True)
        box.addWidget(self.fix_summary)
        self.fix_table = table(['OPERATION', 'FILE', 'LINES', 'DETAILS'])
        self.fix_table.setColumnWidth(0, 160)
        self.fix_table.setColumnWidth(1, 260)
        self.fix_table.setMinimumHeight(130)
        self.fix_table.setMaximumHeight(200)
        self.fix_table.itemSelectionChanged.connect(self.show_fix_diff)
        box.addWidget(self.fix_table)
        self.before = QPlainTextEdit()
        self.after = QPlainTextEdit()
        for w, hint in [(self.before, 'Select a change to preview the original label'), (self.after, 'The proposed label will appear here')]:
            w.setReadOnly(True)
            w.setPlaceholderText(hint)
            w.setFont(QFont('Consolas', 10))
            w.setMinimumHeight(115)
            w.setMaximumHeight(170)
        before_card, lay = card('Before')
        lay.addWidget(self.before)
        after_card, lay = card('After')
        lay.addWidget(self.after)
        box.addWidget(row(before_card, after_card))
        frame, lay = card('Save a separate copy', 'Only audited images and labels are copied. data.yaml is regenerated with relative paths; other metadata stays in the source. Review the copy and rescan it before training.')
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText('New output folder, outside the source dataset')
        lay.addWidget(row(self.output_path, button('Choose parent…', self.choose_output)))
        self.save_copy_button = button('Create cleaned copy', self.save_copy, True)
        self.save_copy_button.setEnabled(False)
        lay.addWidget(self.save_copy_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(frame)
        box.addStretch()
        scroll.setWidget(page)
        return scroll

    def make_exports(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        banner, lay = card('An audit you can share', 'Reports contain local dataset paths and label details. Choose the format that fits your workflow.')
        self.report_summary = label('Run an audit to enable report downloads.', 'muted')
        lay.addWidget(self.report_summary)
        box.addWidget(banner)
        self.export_buttons = []
        for fmt, title, desc in [('html', 'Browser report', 'A styled, standalone report with summary metrics, class counts and the full issue list. Print or save as PDF from your browser.'), ('csv', 'Spreadsheet report', 'One row per finding with severity, file path, line number and related files. Opens in Excel; formula-like cells are escaped.'), ('json', 'Developer report', 'Complete structured audit: image records, normalized boxes, issue details, duplicate groups, hashes and counts.')]:
            frame, lay = card(title, desc)
            b = button(f'Export {fmt.upper()}  ↓', lambda checked=False, kind=fmt: self.export_report(kind), fmt == 'html')
            b.setEnabled(False)
            self.export_buttons.append(b)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
            box.addWidget(frame)
        box.addStretch()
        return page

    def make_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        frame, lay = card('Class names', 'By default, class names come from data.yaml / data.yml / dataset.yaml / dataset.yml in the selected folder. The first existing config in that order is used.')
        self.class_override = QLineEdit()
        self.class_override.setPlaceholderText('Optional override, in ID order: Safety-Helmet, Reflective-Jacket')
        lay.addWidget(self.class_override)
        lay.addWidget(label('Comma-separated names start at class ID 0. Overrides take effect on the next scan. Leave blank to use YAML.', 'muted', True))
        box.addWidget(frame)
        frame, lay = card('Supported dataset layouts')
        layouts = label('Split first:  train/images + train/labels, valid/images + valid/labels, test/images + test/labels\nType first:  images/train + labels/train, images/val + labels/val\nFlat:  image.jpg + image.txt in the same directory\n\nNested folders within these layouts are supported. Split aliases val, valid and validation are normalized to val. Choose the dataset root containing data.yaml, not just an images folder.', 'muted', True)
        lay.addWidget(layouts)
        box.addWidget(frame)
        frame, lay = card('What the audit can tell you', 'This release supports YOLO axis-aligned object detection: class x_center y_center width height.')
        lay.addWidget(label('• Boxes must have finite normalized coordinates and remain within the image.\n• Empty labels are review items, not errors. Missing labels are warnings.\n• Duplicates use identical decoded RGB pixels and dimensions, including different lossless encodings.\n• Split overlap is an error when duplicate content crosses recognized split directories.\n• Class imbalance uses a 5× nonzero instance ratio as a review heuristic; unused classes are listed separately.\n• Counts exclude invalid and repeated annotation rows.', 'muted', True))
        box.addWidget(frame)
        frame, lay = card('Scope & privacy')
        lay.addWidget(label('All processing happens on your computer. No uploads, accounts, telemetry, GPU or model weights are required. Internet is needed only to install dependencies.\n\nYAML supplies class metadata; custom YAML split paths, external datasets and text-file image manifests are not resolved. Classification, segmentation, pose and oriented boxes are not supported. Near duplicates, JPEG re-encodings and incorrect object identity need human review. Images over 40 megapixels are flagged instead of decoded. Symlinks are skipped.\n\nThe source is never edited. Cleaned copies retain unresolved image problems and generate a fresh relative-path data.yaml. When splits are unassigned, configure them manually before training. Fix plans are rejected if audited source files change.', 'muted', True))
        box.addWidget(frame)
        box.addWidget(button('Open project folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(PROJECT)))), 0, Qt.AlignmentFlag.AlignLeft)
        box.addStretch()
        scroll.setWidget(page)
        return scroll

    def choose_dataset(self):
        path = QFileDialog.getExistingDirectory(self, 'Select YOLO dataset root')
        if path:
            self.start_scan(path)

    def load_demo(self):
        path = PROJECT / 'demo_dataset'
        if not path.exists():
            QMessageBox.information(self, 'Demo unavailable', 'Run python scripts/create_demo.py from the project folder first.')
            return
        self.start_scan(path)

    def rescan(self):
        if self.result:
            self.start_scan(self.result.root)

    def start_scan(self, path):
        if self.worker:
            return
        raw = self.class_override.text().strip()
        names = [v.strip() for v in raw.split(',')] if raw else None
        self.run_worker(lambda progress, cancelled: scan_dataset(path, names, progress, cancelled), self.scan_finished, 'Scanning dataset…')

    def run_worker(self, fn, callback, status):
        if self.worker:
            return
        self.status.setText(status)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        for b in [self.open_button, self.demo_button, self.rescan_button, self.preview_button, self.save_copy_button]:
            b.setEnabled(False)
        worker = Worker(fn)
        self.worker = worker
        worker.progress.connect(self.update_progress)
        worker.completed.connect(callback)
        worker.failed.connect(self.work_failed)
        worker.cancelled.connect(lambda: self.status.setText('Cancelled. Source files were not changed.'))
        worker.finished.connect(self.work_finished)
        worker.start()

    def update_progress(self, done, total, path):
        self.progress.setValue(round(100 * done / total) if total else 0)
        self.status.setText(f'{done:,} / {total:,} · {path}')
        self.status.setToolTip(path)

    def cancel_work(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText('Cancelling after the current file…')

    def work_failed(self, message):
        self.status.setText('Operation failed. See the error details.')
        QMessageBox.warning(self, 'Dataset Doctor', message)

    def work_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        self.progress.hide()
        self.cancel_button.hide()
        self.open_button.setEnabled(True)
        self.demo_button.setEnabled(True)
        self.rescan_button.setEnabled(self.result is not None)
        self.preview_button.setEnabled(True)
        self.save_copy_button.setEnabled(self.plan is not None and bool(self.plan.actions))

    def scan_finished(self, result):
        self.result = result
        self.invalidate_plan()
        self.last_output = None
        c = result.counts
        self.dataset_name.setText(Path(result.root).name)
        self.dataset_name.setToolTip(result.root)
        self.banner_title.setText('Audit complete. Your next steps are clear.' if result.issues else 'Audit complete. No supported issues detected.')
        self.banner_note.setText(f'{Path(result.root).name}  ·  {c["errors"]:,} errors  ·  {c["warnings"]:,} warnings  ·  {c["reviews"]:,} review items')
        for widget, key in zip(self.metric_values, ['images', 'annotations', 'errors', 'reviews']):
            widget.setText(f'{c[key]:,}')
        self.metric_values[2].setStyleSheet('color:#d34b63;' if c['errors'] else 'color:#0c8c7c;')
        self.class_chart.set_values(c['classes'].items())
        self.split_chart.set_values(sorted(c['splits'].items(), key=lambda item: ['train', 'val', 'test', 'unassigned'].index(item[0])))
        top = Counter(i.code for i in result.issues).most_common(4)
        self.top_issues.setText('\n\n'.join(f'{n:>3}    {code.replace("_", " ").capitalize()}' for code, n in top) or 'No issues found by the supported checks.')
        self.health_label.setText(f'{result.health}%')
        self.code_filter.blockSignals(True)
        self.code_filter.clear()
        self.code_filter.addItem('All checks')
        self.code_filter.addItems(sorted({i.code for i in result.issues}))
        self.code_filter.blockSignals(False)
        self.filter_issues()
        self.filter_images()
        self.output_path.setText(str(Path(result.root).with_name(Path(result.root).name + '_cleaned')))
        self.report_summary.setText(f'{c["images"]:,} images · {len(result.issues):,} findings · {result.duration:.2f}s audit time')
        for b in self.export_buttons:
            b.setEnabled(True)
        self.status.setText(f'Audit complete · {c["images"]:,} images · {result.duration:.2f}s · Source unchanged')
        self.go(0)

    def filter_issues(self, *_):
        if not self.result:
            return
        query = self.issue_search.text().casefold()
        severity = self.severity_filter.currentText().lower()
        code = self.code_filter.currentText()
        split = self.issue_split_filter.currentText()
        image_splits = {r.path: r.split for r in self.result.records}
        image_splits.update({r.label: r.split for r in self.result.records})
        self.issue_rows = [i for i in self.result.issues if (severity == 'all severities' or i.severity == severity) and (code == 'All checks' or i.code == code) and (split == 'All splits' or split in {image_splits.get(p, 'dataset-level') for p in [i.path, *i.related]}) and query in f'{i.code} {i.path} {i.message} {" ".join(i.related)}'.casefold()]
        self.issue_table.setUpdatesEnabled(False)
        self.issue_table.setRowCount(len(self.issue_rows))
        for n, i in enumerate(self.issue_rows):
            set_row(self.issue_table, n, [i.severity, i.code.replace('_', ' '), i.path, i.line or '—', i.message])
        self.issue_table.setUpdatesEnabled(True)
        self.issue_count.setText(f'{len(self.issue_rows):,} of {len(self.result.issues):,} findings · Double-click a row to inspect its image')
        self.issue_detail.setText('Select a finding to see its details and related files.')

    def show_issue_detail(self):
        n = self.issue_table.currentRow()
        if not 0 <= n < len(self.issue_rows):
            return
        i = self.issue_rows[n]
        text = f'{i.path}' + (f' : line {i.line}' if i.line else '') + '\n' + i.message
        if i.related:
            text += '\nRelated: ' + ' · '.join(i.related[:8])
            if len(i.related) > 8:
                text += f' (+{len(i.related) - 8} more in reports)'
        self.issue_detail.setText(text)

    def inspect_issue(self):
        if not self.result:
            return
        n = self.issue_table.currentRow()
        if not 0 <= n < len(self.issue_rows):
            return
        issue = self.issue_rows[n]
        targets = {issue.path, *issue.related}
        rec = next((r for r in self.result.records if r.path in targets or r.label in targets), None)
        if not rec:
            self.status.setText('This finding has no matching image. See the file path and full report.')
            return
        self.image_search.clear()
        self.image_split.setCurrentIndex(0)
        self.filter_images()
        self.image_list.setCurrentRow(self.image_rows.index(rec))
        self.go(2)

    def filter_images(self, *_):
        if not self.result:
            return
        query = self.image_search.text().casefold()
        split = self.image_split.currentText()
        self.image_rows = [r for r in self.result.records if query in r.path.casefold() and (split == 'All splits' or r.split == split)]
        self.image_list.blockSignals(True)
        self.image_list.clear()
        for rec in self.image_rows:
            item = QListWidgetItem(f'{Path(rec.path).name}\n{rec.split}  ·  {len(rec.annotations)} valid boxes')
            item.setToolTip(rec.path)
            self.image_list.addItem(item)
        self.image_list.blockSignals(False)
        self.image_count.setText(f'{len(self.image_rows):,} images')
        if self.image_rows:
            self.image_list.setCurrentRow(0)
        else:
            self.canvas.pixmap = QPixmap()
            self.canvas.error = 'No images match your filters'
            self.canvas.update()
            self.image_title.setText('Image preview')
            self.image_meta.setText('No matching image selected.')
            self.annotation_table.setRowCount(0)

    def show_image(self, n):
        if not self.result or not 0 <= n < len(self.image_rows):
            return
        rec = self.image_rows[n]
        self.image_title.setText(Path(rec.path).name)
        self.image_title.setToolTip(rec.path)
        self.canvas.set_image(Path(self.result.root) / rec.path, rec, self.result.classes)
        findings = [i for i in self.result.issues if rec.path in [i.path, *i.related] or rec.label in [i.path, *i.related]]
        tags = ', '.join(sorted({i.code.replace('_', ' ') for i in findings})) or 'No recorded image-specific findings'
        self.image_meta.setText(f'{rec.path}  ·  {rec.width} × {rec.height}  ·  {rec.split}\n{tags}\nInvalid and repeated rows are excluded from overlays and instance counts.')
        self.annotation_table.setRowCount(len(rec.annotations))
        for n, a in enumerate(rec.annotations):
            set_row(self.annotation_table, n, [a.class_id, self.result.classes[a.class_id], f'{a.box[0]:.4f} / {a.box[1]:.4f}', f'{a.box[2]:.4f} / {a.box[3]:.4f}', a.line])

    def toggle_boxes(self, checked):
        self.canvas.show_boxes = checked
        self.canvas.update()

    def invalidate_plan(self, *_):
        self.plan = None
        if hasattr(self, 'fix_table'):
            self.fix_table.setRowCount(0)
            self.before.clear()
            self.after.clear()
            self.save_copy_button.setEnabled(False)
            self.fix_summary.setText('Generate a preview to see the exact files and line numbers that would change.')

    def preview_fixes(self):
        if not self.result:
            QMessageBox.information(self, 'Open a dataset', 'Run an audit before preparing fixes.')
            return
        try:
            self.plan = build_plan(self.result, self.remove_duplicate_rows.isChecked(), self.drop_invalid.isChecked(), self.create_background.isChecked())
        except ValueError as exc:
            QMessageBox.warning(self, 'Manual review needed', str(exc))
            return
        self.fix_table.setRowCount(len(self.plan.actions))
        for n, a in enumerate(self.plan.actions):
            set_row(self.fix_table, n, [a.operation.replace('_', ' '), a.path, ', '.join(map(str, a.lines)) or '—', a.explanation])
        self.fix_summary.setText(f'{len(self.plan.actions):,} label files would change. All images are retained; unresolved findings remain. Original files are preserved.')
        self.save_copy_button.setEnabled(bool(self.plan.actions) and self.worker is None)
        if self.plan.actions:
            self.fix_table.selectRow(0)

    def show_fix_diff(self):
        n = self.fix_table.currentRow()
        if not self.plan or not 0 <= n < len(self.plan.actions):
            return
        action = self.plan.actions[n]
        path = Path(self.result.root) / action.path
        try:
            old = path.read_text(encoding='utf-8-sig') if path.exists() else ''
            if len(old) > 100_000:
                self.before.setPlainText('Preview omitted: label exceeds 100,000 characters. See report and exact line numbers above.')
                self.after.setPlainText('The copy operation will still apply only the listed line changes.')
                return
            new = '\n'.join(line for n, line in enumerate(old.splitlines(), 1) if n not in action.lines)
            self.before.setPlainText(old or ('[missing label file]' if not path.exists() else '[empty label]'))
            self.after.setPlainText(new or '[empty background label]')
        except (OSError, UnicodeError) as exc:
            self.before.setPlainText(str(exc))
            self.after.clear()

    def choose_output(self):
        parent = QFileDialog.getExistingDirectory(self, 'Choose parent directory for new dataset copy')
        if parent:
            name = Path(self.result.root).name + '_cleaned' if self.result else 'dataset_cleaned'
            self.output_path.setText(str(Path(parent) / name))

    def save_copy(self):
        if self.worker or not self.result or not self.plan or not self.plan.actions:
            return
        path = self.output_path.text().strip()
        if not path:
            QMessageBox.warning(self, 'Output folder required', 'Choose a new output folder.')
            return
        warning = f'Copy the audited images and labels to:\n{path}\n\nApply {len(self.plan.actions)} label changes and regenerate data.yaml?\nThe source is preserved. Unresolved issues remain.'
        if self.plan.drop_invalid:
            warning += '\n\nInvalid annotation rows will be discarded. This may remove all annotations from some images.'
        if self.plan.create_backgrounds:
            warning += '\n\nMissing labels will become empty backgrounds. Confirm those images contain no target objects.'
        if QMessageBox.question(self, 'Create reviewed dataset copy', warning, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        result, plan = self.result, self.plan
        self.run_worker(lambda progress, cancelled: write_clean_copy(result, plan, path, progress, cancelled), self.copy_finished, 'Creating a separate dataset copy…')

    def copy_finished(self, path):
        self.last_output = path
        self.status.setText(f'Cleaned copy saved: {path}')
        QMessageBox.information(self, 'Dataset copy created', f'Saved to:\n{path}\n\nOpen this folder and run a fresh audit before training. Review remaining findings and the regenerated data.yaml.')

    def export_report(self, kind):
        if not self.result:
            return
        name = f'{Path(self.result.root).name}_audit.{kind}'
        path, _ = QFileDialog.getSaveFileName(self, 'Export audit report', str(Path.home() / name), f'{kind.upper()} report (*.{kind})')
        if not path:
            return
        try:
            target = Path(path).resolve()
            # Report exports must never overwrite any source dataset path.
            if target.is_relative_to(Path(self.result.root).resolve()):
                raise ValueError('Save reports outside the source dataset folder.')
            content = {'html': html_report, 'csv': csv_report, 'json': json_report}[kind](self.result)
            target.write_text(content, encoding='utf-8')
            self.status.setText(f'Report saved: {target}')
            if kind == 'html':
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1 and Path(event.mimeData().urls()[0].toLocalFile()).is_dir():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.worker:
            self.start_scan(event.mimeData().urls()[0].toLocalFile())
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.cancel_work()
            self.status.setText('Cancelling the current operation. Close again after it finishes.')
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Dataset Doctor')
    app.setOrganizationName('DatasetDoctor')
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    if '--demo' in sys.argv:
        QTimer.singleShot(150, window.load_demo)
    elif len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        path = sys.argv[1]
        QTimer.singleShot(150, lambda: window.start_scan(path))
    return app.exec()
