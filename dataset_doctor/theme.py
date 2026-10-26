"""Small, consistent design system for the desktop application."""
COLORS = ['#0d9488', '#5478ed', '#e6a340', '#b56cce', '#e57889', '#38a5ba', '#86984a', '#826cbd']
STYLE = '''
* { font-family: "Segoe UI", "Inter", "DejaVu Sans"; font-size: 13px; }
QMainWindow, QWidget#shell { background: #f3f6fa; color: #192b42; }
QLabel { color: #192b42; background: transparent; }
QLabel#muted { color: #77869a; font-size: 12px; }
QLabel#eyebrow { color: #74849a; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 27px; font-weight: 700; color: #17283e; }
QLabel#section { font-size: 16px; font-weight: 700; }
QLabel#metric { font-size: 30px; font-weight: 700; }
QLabel#brand { color: #f0f5fa; font-size: 19px; font-weight: 700; }
QLabel#brandSub { color: #8297ae; font-size: 11px; }
QLabel#navLabel { color: #6f859f; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QFrame#sidebar { background: #142237; border: 0; }
QFrame#card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; }
QFrame#banner { background: #e8f4f1; border: 1px solid #cce5df; border-radius: 10px; }
QLabel#bannerTitle { color: #146858; font-size: 15px; font-weight: 700; }
QPushButton { background: #fff; border: 1px solid #dbe3ed; border-radius: 7px; padding: 9px 16px; color: #263d58; font-weight: 600; }
QPushButton:hover { background: #edf3f7; border-color: #b7c8d8; }
QPushButton:pressed { background: #dfebf0; }
QPushButton#primary { background: #0c8c7c; color: white; border: 1px solid #0c8c7c; }
QPushButton#primary:hover { background: #087969; }
QPushButton:disabled { background: #edf1f5; color: #a0adba; border-color: #e2e8ef; }
QPushButton#nav { text-align: left; color: #a9b9cd; background: transparent; border: 0; border-radius: 7px; padding: 12px 14px; font-size: 13px; }
QPushButton#nav:hover { background: #1c304a; color: white; }
QPushButton#nav:checked { background: #23443f; color: #6ee2c3; }
QPushButton#sidebarAction { background: #20324b; color: #dce7f4; border: 1px solid #30445e; }
QLineEdit, QComboBox, QPlainTextEdit { color: #263d58; background: white; border: 1px solid #dbe3ed; border-radius: 6px; padding: 8px; selection-background-color: #d2f0e9; selection-color: #174d44; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #0d9488; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: white; color: #263d58; selection-background-color: #e4f4ef; }
QTableWidget { background: white; color: #29415c; border: 1px solid #e2e8f0; border-radius: 7px; gridline-color: #eef2f6; selection-background-color: #e5f4ef; selection-color: #134e42; alternate-background-color: #fafcfe; }
QTableWidget::item { padding: 9px 10px; border-bottom: 1px solid #eef2f6; }
QHeaderView::section { background: #f7f9fc; color: #7a899d; padding: 11px 10px; border: 0; border-bottom: 1px solid #e5ebf1; font-size: 10px; font-weight: 700; }
QListWidget { background: white; border: 1px solid #e2e8f0; border-radius: 7px; color: #29415c; padding: 5px; outline: none; }
QListWidget::item { padding: 10px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #e2f2ed; color: #0d7163; }
QListWidget::item:hover { background: #f0f5f8; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #c8d3df; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 8px; background: transparent; }
QScrollBar::handle:horizontal { background: #c8d3df; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { color: #29415c; spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #bbcbd8; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #0d9488; border-color: #0d9488; image: url(none); }
QProgressBar { border: 0; background: #dfe8ed; height: 6px; border-radius: 3px; color: transparent; }
QProgressBar::chunk { background: #10aa94; border-radius: 3px; }
QSplitter::handle { background: #f3f6fa; width: 14px; }
QToolTip { color: #e9f0f8; background: #17283e; border: 0; padding: 7px; }
QMessageBox { background: #f3f6fa; }
'''
