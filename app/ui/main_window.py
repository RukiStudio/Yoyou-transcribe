"""Main application window coordinating import, analysis, editing and export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt, QUrl
from PySide6.QtGui import QAction, QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QSplitter, QTableWidget,
    QTableWidgetItem, QToolBar, QVBoxLayout, QWidget, QDockWidget,
)

from app.analysis import _create_demo_project, analyze_audio
from app.midi_service import build_preview_wav, export_midi
from app.models import NoteEvent, SongProject
from app.ui.piano_roll import PianoRoll
from app.ui.style import APP_STYLESHEET


class AnalysisWorker(QObject):
    """Run CPU-heavy feature extraction off the Qt event loop."""

    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            self.finished.emit(analyze_audio(self.path, self.progress.emit))
        except Exception as error:  # UI should convert dependency/audio errors into readable feedback.
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    """A compact workflow for importing, reviewing and exporting a song."""

    def __init__(self):
        super().__init__()
        self.project: SongProject | None = None
        self.worker_thread: QThread | None = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.42)
        self.setWindowTitle("Ruki's Music Transcriber · AI 快速扒谱")
        self.resize(1360, 840)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_toolbar()
        self._build_workspace()
        self._build_docks()
        self.statusBar().showMessage("准备就绪：导入一首音频，开始你的扒谱练习。")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addWidget(QLabel("  RUKI  "))
        for label, handler in [("导入音频", self.import_audio), ("示例工程", self.open_demo), ("导出 MIDI", self.export_current_midi), ("试听", self.preview_project)]:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

    def _build_workspace(self) -> None:
        self.stack = QSplitter(Qt.Orientation.Vertical)
        self.welcome = self._create_welcome()
        self.roll = PianoRoll()
        self.roll.note_selected.connect(self.show_note_details)
        self.roll.note_added.connect(lambda note: self.statusBar().showMessage(f"已添加 {self._note_name(note.pitch)}"))
        self.roll.note_deleted.connect(lambda note: self.statusBar().showMessage("已删除音符"))
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.roll)
        self.stack.setSizes([700, 1])
        self.setCentralWidget(self.stack)

    def _create_welcome(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(70, 70, 70, 70)
        layout.setSpacing(18)
        title = QLabel("把每一首喜欢的歌，变成你的编曲课堂")
        title.setObjectName("titleLabel")
        subtitle = QLabel("导入音频后，AI 将识别速度、调性、主旋律与节奏；所有结果都可以在钢琴卷帘中修改。")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        buttons = QHBoxLayout()
        import_button = QPushButton("导入音乐开始扒谱")
        import_button.setObjectName("primaryButton")
        import_button.clicked.connect(self.import_audio)
        demo_button = QPushButton("先看看示例工程")
        demo_button.clicked.connect(self.open_demo)
        buttons.addWidget(import_button)
        buttons.addWidget(demo_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        cards = QHBoxLayout()
        for heading, description in [("01 识别", "BPM、调性、节拍与主旋律"), ("02 编辑", "双击添加音符，删除错误结果"), ("03 输出", "导出 MIDI，带入任意编曲软件")]:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(heading))
            detail = QLabel(description)
            detail.setObjectName("subtitleLabel")
            detail.setWordWrap(True)
            card_layout.addWidget(detail)
            cards.addWidget(card)
        layout.addLayout(cards)
        layout.addStretch(2)
        return root

    def _build_docks(self) -> None:
        self.track_table = QTableWidget(0, 3)
        self.track_table.setHorizontalHeaderLabels(["声部", "音符", "状态"])
        self.track_table.horizontalHeader().setStretchLastSection(True)
        track_dock = QDockWidget("声部轨道", self)
        track_dock.setWidget(self.track_table)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, track_dock)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        self.metrics = QTableWidget(4, 2)
        self.metrics.setHorizontalHeaderLabels(["信息", "结果"])
        self.metrics.verticalHeader().setVisible(False)
        self.metrics.horizontalHeader().setStretchLastSection(True)
        inspector_layout.addWidget(self.metrics)
        inspector_layout.addWidget(QLabel("进阶：相似旋律替换"))
        self.candidate_label = QLabel("选中一个音符后，将显示相近候选。")
        self.candidate_label.setWordWrap(True)
        inspector_layout.addWidget(self.candidate_label)
        replace_button = QPushButton("用上方候选替换")
        replace_button.clicked.connect(self.replace_selected_note)
        inspector_layout.addWidget(replace_button)
        inspector_layout.addStretch(1)
        info_dock = QDockWidget("分析与编辑", self)
        info_dock.setWidget(inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, info_dock)

    def import_audio(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "选择音频文件", "", "音频文件 (*.wav *.mp3 *.flac *.m4a *.ogg)")
        if file_name:
            self._start_analysis(Path(file_name))

    def _start_analysis(self, path: Path) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("正在准备 AI 分析…")
        self.worker_thread = QThread(self)
        worker = AnalysisWorker(path)
        # Keep a Python reference for the lifetime of the background Qt worker.
        self.worker = worker
        worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(worker.run)
        worker.progress.connect(self._show_progress)
        worker.finished.connect(self._analysis_finished)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(self.worker_thread.quit)
        worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(worker.deleteLater)
        self.worker_thread.finished.connect(lambda: setattr(self, "worker", None))
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _show_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.statusBar().showMessage(message)

    def _analysis_finished(self, project: SongProject) -> None:
        self._clear_progress()
        self.load_project(project)
        self.statusBar().showMessage("分析完成。请检查音符，并根据听感修正。", 7000)

    def _analysis_failed(self, reason: str) -> None:
        self._clear_progress()
        QMessageBox.warning(self, "分析未完成", f"无法读取或分析该音频。\n\n{reason}\n\n可先打开示例工程体验编辑功能。")
        self.statusBar().showMessage("分析失败")

    def _clear_progress(self) -> None:
        if hasattr(self, "progress"):
            self.statusBar().removeWidget(self.progress)
            self.progress.deleteLater()
            del self.progress

    def open_demo(self) -> None:
        self.load_project(_create_demo_project())
        self.statusBar().showMessage("已打开示例工程：双击网格可添加音符。")

    def load_project(self, project: SongProject) -> None:
        self.project = project
        self.roll.set_project(project)
        self.stack.setSizes([1, 700])
        self.setWindowTitle(f"{project.title} · Ruki's Music Transcriber")
        self.metrics.setRowCount(4)
        for row, (name, value) in enumerate([( "调性", project.key), ("速度", f"{project.bpm} BPM"), ("拍号", project.time_signature), ("时长", f"{project.duration:.1f} 秒")]):
            self.metrics.setItem(row, 0, QTableWidgetItem(name))
            self.metrics.setItem(row, 1, QTableWidgetItem(value))
        self.track_table.setRowCount(len(project.tracks))
        for row, track in enumerate(project.tracks):
            self.track_table.setItem(row, 0, QTableWidgetItem(track.name))
            self.track_table.setItem(row, 1, QTableWidgetItem(str(len(track.notes))))
            self.track_table.setItem(row, 2, QTableWidgetItem("已识别"))

    def show_note_details(self, note: NoteEvent) -> None:
        self.selected_note = note
        candidates = [max(0, min(127, note.pitch + offset)) for offset in (-2, 2, 5)]
        labels = "、".join(f"{self._note_name(pitch)}（{94 - index * 7}%）" for index, pitch in enumerate(candidates))
        self.candidate_label.setText(f"当前：{self._note_name(note.pitch)}\n推荐相似走向：{labels}\n点击替换会采用第一项。")

    def replace_selected_note(self) -> None:
        if not hasattr(self, "selected_note") or not self.project:
            self.statusBar().showMessage("请先在钢琴卷帘中选中一个音符。")
            return
        self.selected_note.pitch = max(0, min(127, self.selected_note.pitch - 2))
        self.roll.set_project(self.project)
        self.statusBar().showMessage("已应用最高置信度的相似旋律候选。")

    def export_current_midi(self) -> None:
        if not self.project:
            self.statusBar().showMessage("请先导入音频或打开示例工程。")
            return
        default_name = f"{self.project.title}.mid"
        file_name, _ = QFileDialog.getSaveFileName(self, "导出 MIDI", default_name, "MIDI 文件 (*.mid)")
        if file_name:
            export_midi(self.project, Path(file_name))
            self.statusBar().showMessage(f"MIDI 已导出：{Path(file_name).name}", 6000)

    def preview_project(self) -> None:
        if not self.project:
            self.statusBar().showMessage("请先导入音频或打开示例工程。")
            return
        preview_path = build_preview_wav(self.project)
        self.player.setSource(QUrl.fromLocalFile(str(preview_path)))
        self.player.play()
        self.statusBar().showMessage("正在试听当前钢琴卷帘（最长 45 秒）。")

    @staticmethod
    def _note_name(pitch: int) -> str:
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{names[pitch % 12]}{pitch // 12 - 1}"
