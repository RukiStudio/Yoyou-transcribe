"""Single source of visual design tokens for the student-friendly workspace."""

APP_STYLESHEET = """
QMainWindow { background: #101624; color: #E9EDF5; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; font-size: 13px; }
QToolBar { background: #151D2E; border: 0; spacing: 8px; padding: 10px 14px; }
QToolButton, QPushButton { background: #25304A; color: #F8FAFC; border: 0; border-radius: 8px; padding: 8px 12px; }
QToolButton:hover, QPushButton:hover { background: #34436A; }
QPushButton#primaryButton { background: #7C5CFC; font-weight: 700; padding: 10px 16px; }
QPushButton#primaryButton:hover { background: #9279FF; }
QDockWidget { color: #E9EDF5; font-weight: 700; }
QDockWidget::title { background: #151D2E; padding: 10px; }
QTreeWidget, QListWidget, QTableWidget { background: #151D2E; color: #E9EDF5; border: 0; border-radius: 8px; padding: 5px; }
QHeaderView::section { background: #202A40; color: #AEB9D4; border: 0; padding: 7px; }
QLabel#titleLabel { font-size: 28px; font-weight: 800; color: #F8FAFC; }
QLabel#subtitleLabel { font-size: 15px; color: #AEB9D4; }
QLabel#metricValue { font-size: 20px; font-weight: 800; color: #FFD166; }
QFrame#card { background: #182238; border-radius: 14px; }
QProgressBar { background: #273044; border: 0; border-radius: 6px; text-align: center; color: #FFFFFF; }
QProgressBar::chunk { background: #7C5CFC; border-radius: 6px; }
"""
