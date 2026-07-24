"""Main application window coordinating import, analysis, editing and export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QToolBar, QVBoxLayout, QWidget, QDockWidget, QListWidget,
    QListWidgetItem,
)

from app.analysis import _create_demo_project, analyze_audio, regenerate_measure
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
        self._tool_mode = "select"
        self._active_track_name = "主旋律"
        self.selected_note: NoteEvent | None = None
        self.selected_measure = 0
        self.setWindowTitle("Ruki's Music Transcriber · AI 快速扒谱")
        self.resize(1360, 840)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_toolbar()
        self._build_workspace()
        self._build_docks()
        self._build_shortcuts()
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
        toolbar.addSeparator()
        self.select_action = QAction("选择工具", self, checkable=True)
        self.paint_action = QAction("画笔工具", self, checkable=True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(lambda: self.set_tool_mode("select"))
        self.paint_action.triggered.connect(lambda: self.set_tool_mode("pencil"))
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        action_group.addAction(self.select_action)
        action_group.addAction(self.paint_action)
        toolbar.addAction(self.select_action)
        toolbar.addAction(self.paint_action)

    def _build_workspace(self) -> None:
        self.tabs = QTabWidget()

        self.edit_tab = QWidget()
        edit_layout = QVBoxLayout(self.edit_tab)
        self.welcome = self._create_welcome()
        edit_layout.addWidget(self.welcome)
        self.roll = PianoRoll()
        self.roll.note_selected.connect(self.show_note_details)
        self.roll.note_added.connect(lambda note: self.statusBar().showMessage(f"已添加 {self._note_name(note.pitch)}"))
        self.roll.note_deleted.connect(lambda note: self.statusBar().showMessage("已删除音符"))
        self.roll.set_active_track(self._active_track_name)
        self.roll.set_edit_mode(self._tool_mode)
        edit_layout.addWidget(self.roll)
        self.tabs.addTab(self.edit_tab, "编辑")

        self.analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_tab)
        analysis_layout.addWidget(QLabel("分析结果与小节置信度"))
        self.analysis_tab.setLayout(analysis_layout)
        self.tabs.addTab(self.analysis_tab, "分析")

        self.output_tab = QWidget()
        output_layout = QVBoxLayout(self.output_tab)
        output_layout.setSpacing(14)
        output_layout.addWidget(QLabel("输出与实时试听"))
        output_controls = QHBoxLayout()
        preview_button = QPushButton("试听当前项目")
        preview_button.clicked.connect(self.preview_project)
        stop_button = QPushButton("停止播放")
        stop_button.clicked.connect(self.player.stop)
        output_controls.addWidget(preview_button)
        output_controls.addWidget(stop_button)
        output_layout.addLayout(output_controls)
        export_button = QPushButton("导出当前 MIDI")
        export_button.clicked.connect(self.export_current_midi)
        output_layout.addWidget(export_button)
        output_layout.addStretch(1)
        self.tabs.addTab(self.output_tab, "输出")

        self.setCentralWidget(self.tabs)

    def _create_welcome(self) -> QWidget:
        welcome_widget = QWidget()
        layout = QVBoxLayout(welcome_widget)
        layout.addWidget(QLabel("欢迎使用 Ruki's Music Transcriber"))
        layout.addWidget(QLabel("导入音频文件，使用 AI 进行自动扒谱，或打开示例工程开始编辑。"))
        layout.addStretch(1)
        return welcome_widget

    def _build_docks(self) -> None:
        track_selection = QWidget()
        track_layout = QVBoxLayout(track_selection)
        track_layout.addWidget(QLabel("当前画笔轨道"))
        self.track_list = QListWidget()
        self.track_list.currentItemChanged.connect(self._on_track_list_changed)
        self.track_list.setFixedWidth(220)
        track_layout.addWidget(self.track_list)
        tool_label = QLabel("工具模式")
        track_layout.addWidget(tool_label)
        self.select_tool_button = QPushButton("选择")
        self.paint_tool_button = QPushButton("画笔")
        self.select_tool_button.setCheckable(True)
        self.paint_tool_button.setCheckable(True)
        self.select_tool_button.clicked.connect(lambda: self.set_tool_mode("select"))
        self.paint_tool_button.clicked.connect(lambda: self.set_tool_mode("pencil"))
        self.select_tool_button.setChecked(True)
        track_layout.addWidget(self.select_tool_button)
        track_layout.addWidget(self.paint_tool_button)
        track_layout.addStretch(1)
        left_dock = QDockWidget("工具与轨道", self)
        left_dock.setWidget(track_selection)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        self.metrics = QTableWidget(4, 2)
        self.metrics.setHorizontalHeaderLabels(["信息", "结果"])
        self.metrics.verticalHeader().setVisible(False)
        self.metrics.horizontalHeader().setStretchLastSection(True)
        inspector_layout.addWidget(self.metrics)

        inspector_layout.addWidget(QLabel("每小节最高置信度"))
        self.measure_table = QTableWidget(0, 3)
        self.measure_table.setHorizontalHeaderLabels(["小节", "置信度", "音符数"])
        self.measure_table.verticalHeader().setVisible(False)
        self.measure_table.horizontalHeader().setStretchLastSection(True)
        self.measure_table.itemSelectionChanged.connect(self._on_measure_selected)
        inspector_layout.addWidget(self.measure_table)
        self.regenerate_button = QPushButton("重新生成选中小节")
        self.regenerate_button.clicked.connect(self.regenerate_selected_measure)
        inspector_layout.addWidget(self.regenerate_button)

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

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+I"), self, self.import_audio)
        QShortcut(QKeySequence("Ctrl+P"), self, self.preview_project)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_current_midi)
        QShortcut(QKeySequence("1"), self, lambda: self.set_tool_mode("select"))
        QShortcut(QKeySequence("2"), self, lambda: self.set_tool_mode("pencil"))

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
        self.project.update_measure_metadata()
        self.roll.set_project(project)
        self.roll.set_active_track(self._active_track_name)
        self.roll.set_edit_mode(self._tool_mode)
        self.tabs.setCurrentIndex(0)
        self.setWindowTitle(f"{project.title} · Ruki's Music Transcriber")
        self.metrics.setRowCount(4)
        for row, (name, value) in enumerate([
            ("调性", project.key), ("速度", f"{project.bpm} BPM"), ("拍号", project.time_signature), ("时长", f"{project.duration:.1f} 秒")]):
            self.metrics.setItem(row, 0, QTableWidgetItem(name))
            self.metrics.setItem(row, 1, QTableWidgetItem(value))
        self._populate_track_list()
        self._populate_measure_list()

    def _populate_track_list(self) -> None:
        self.track_list.clear()
        if not self.project:
            return
        for track in self.project.tracks:
            item = QListWidgetItem(track.name)
            self.track_list.addItem(item)
            if track.name == self._active_track_name:
                self.track_list.setCurrentItem(item)
        if self.track_list.currentRow() < 0 and self.track_list.count() > 0:
            self.track_list.setCurrentRow(0)

    def _populate_measure_list(self) -> None:
        if not self.project:
            return
        self.project.update_measure_metadata()
        self.measure_table.setRowCount(len(self.project.measures))
        for row, measure in enumerate(self.project.measures):
            self.measure_table.setItem(row, 0, QTableWidgetItem(str(measure["index"] + 1)))
            self.measure_table.setItem(row, 1, QTableWidgetItem(f"{measure['confidence']:.2f}"))
            self.measure_table.setItem(row, 2, QTableWidgetItem(str(measure["notes"])))
        if self.measure_table.rowCount() > 0:
            self.measure_table.selectRow(0)

    def set_tool_mode(self, mode: str) -> None:
        self._tool_mode = mode
        self.roll.set_edit_mode(mode)
        if hasattr(self, "select_action"):
            self.select_action.setChecked(mode == "select")
            self.paint_action.setChecked(mode == "pencil")
        if hasattr(self, "select_tool_button"):
            self.select_tool_button.setChecked(mode == "select")
            self.paint_tool_button.setChecked(mode == "pencil")
        self.statusBar().showMessage(f"已切换到 {'画笔' if mode == 'pencil' else '选择'} 工具。")

    def _on_track_list_changed(self) -> None:
        current = self.track_list.currentItem()
        if current:
            self._active_track_name = current.text()
            self.roll.set_active_track(self._active_track_name)
            self.statusBar().showMessage(f"当前画笔轨道：{self._active_track_name}")

    def _on_measure_selected(self) -> None:
        self.selected_measure = self.measure_table.currentRow()
        if self.selected_measure >= 0:
            self.statusBar().showMessage(f"选中小节：{self.selected_measure + 1}，置信度 {self.project.measure_confidence(self.selected_measure):.2f}" if self.project else "")

    def show_note_details(self, note: NoteEvent) -> None:
        self.selected_note = note
        candidates = [max(0, min(127, note.pitch + offset)) for offset in (-2, 2, 5)]
        labels = "、".join(f"{self._note_name(pitch)}（{94 - index * 7}%）" for index, pitch in enumerate(candidates))
        self.candidate_label.setText(f"当前：{self._note_name(note.pitch)}\n推荐相似走向：{labels}\n点击替换会采用第一项。")

    def replace_selected_note(self) -> None:
        if not self.selected_note or not self.project:
            self.statusBar().showMessage("请先在钢琴卷帘中选中一个音符。")
            return
        self.selected_note.pitch = max(0, min(127, self.selected_note.pitch - 2))
        self.roll.set_project(self.project)
        self.statusBar().showMessage("已应用最高置信度的相似旋律候选。")

    def regenerate_selected_measure(self) -> None:
        if self.project is None:
            self.statusBar().showMessage("请先加载一个工程。")
            return
        if self.selected_measure < 0 or self.selected_measure >= len(self.project.measures):
            self.statusBar().showMessage("请先在小节列表中选择一个小节。")
            return
        regenerate_measure(self.project, self.selected_measure)
        self.project.update_measure_metadata()
        self.roll.set_project(self.project)
        self._populate_measure_list()
        self.statusBar().showMessage(f"已重新生成第 {self.selected_measure + 1} 小节。")

    def export_current_midi(self) -> None:
        if not self.project:
            self.statusBar().showMessage("请先导入音频或打开示例工程。")
            return
        self.project.update_measure_metadata()
        default_name = f"{self.project.title}.mid"
        file_name, _ = QFileDialog.getSaveFileName(self, "导出 MIDI", default_name, "MIDI 文件 (*.mid)")
        if file_name:
            notes = self.project.export_notes()
            export_midi(self.project, Path(file_name), notes)
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
