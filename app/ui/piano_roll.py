"""Interactive piano-roll editor for inspected transcription notes."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView

from app.models import NoteEvent, SongProject


class PianoNoteItem(QGraphicsRectItem):
    """Graphics item retaining the exact NoteEvent it edits."""

    def __init__(self, note: NoteEvent, color: str, x: float, y: float, width: float, height: float):
        super().__init__(x, y, width, height)
        self.note = note
        self.setBrush(QColor(color))
        self.setPen(QPen(QColor("#FFFFFF"), 1))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        self._is_resizing = False
        self._resize_start_x = 0.0
        self._initial_width = width

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value.toPointF() if isinstance(value, QPointF) else QPointF(value)
            x = max(0.0, new_pos.x())
            y = max(0.0, new_pos.y())
            return QPointF(x, y)
        return super().itemChange(change, value)

    def hoverMoveEvent(self, event):
        if event.pos().x() >= self.rect().width() - 10:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().x() >= self.rect().width() - 10:
            self._is_resizing = True
            self._resize_start_x = event.pos().x()
            self._initial_width = self.rect().width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            delta = event.pos().x() - self._resize_start_x
            new_width = max(8.0, self._initial_width + delta)
            self.setRect(0, 0, new_width, self.rect().height())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._is_resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PianoRoll(QGraphicsView):
    """A focused piano roll: click notes, double-click empty space to add one."""

    note_selected = Signal(object)
    note_added = Signal(object)
    note_deleted = Signal(object)

    pixels_per_second = 92
    row_height = 15
    highest_pitch = 96
    lowest_pitch = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.project: SongProject | None = None
        self._edit_mode = "select"
        self._active_track = "主旋律"
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#121827"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def set_edit_mode(self, mode: str) -> None:
        self._edit_mode = mode
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == "select" else QGraphicsView.DragMode.NoDrag)

    def set_active_track(self, name: str) -> None:
        self._active_track = name

    def _pitch_y(self, pitch: int) -> float:
        return (self.highest_pitch - pitch) * self.row_height

    def set_project(self, project: SongProject) -> None:
        """Redraw grid, chord labels and all project notes."""
        self.project = project
        self.scene.clear()
        height = (self.highest_pitch - self.lowest_pitch + 1) * self.row_height
        width = max(1200, (project.duration + 4) * self.pixels_per_second)
        self.scene.setSceneRect(0, 0, width, height)
        grid_pen = QPen(QColor("#273044"))
        for pitch in range(self.lowest_pitch, self.highest_pitch + 1):
            y = self._pitch_y(pitch)
            self.scene.addLine(0, y, width, y, grid_pen)
        seconds_per_beat = 60 / project.bpm
        measure_count = int(math.ceil(project.duration / (seconds_per_beat * 4)))
        for beat in range(measure_count * 4 + 2):
            x = beat * seconds_per_beat * self.pixels_per_second
            if beat % 4 == 0:
                pen = QPen(QColor("#65708A"))
            else:
                pen = QPen(QColor("#273044"))
            self.scene.addLine(x, 0, x, height, pen)
        for start, chord in project.chords:
            label = self.scene.addText(chord)
            label.setDefaultTextColor(QColor("#FFD166"))
            label.setPos(start * self.pixels_per_second + 4, 4)
        for track in project.tracks:
            for note in track.notes:
                item = PianoNoteItem(
                    note,
                    track.color,
                    note.start * self.pixels_per_second,
                    self._pitch_y(note.pitch) + 1,
                    max(8, note.duration * self.pixels_per_second),
                    self.row_height - 2,
                )
                item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, self._edit_mode == "select")
                self.scene.addItem(item)
        self.centerOn(0, self._pitch_y(60))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        item = self.itemAt(event.pos())
        if isinstance(item, PianoNoteItem):
            self.note_selected.emit(item.note)

    def mouseDoubleClickEvent(self, event):
        """Add a snapped note to the selected track when using pencil mode."""
        if self.project is None or self._edit_mode != "pencil":
            return super().mouseDoubleClickEvent(event)

        item = self.itemAt(event.pos())
        if isinstance(item, PianoNoteItem):
            return

        point = self.mapToScene(event.pos())
        step = 60 / self.project.bpm / 4
        start = max(0.0, round((point.x() / self.pixels_per_second) / step) * step)
        pitch = max(self.lowest_pitch, min(self.highest_pitch, self.highest_pitch - round(point.y() / self.row_height)))
        track = next((t for t in self.project.tracks if t.name == self._active_track), None)
        if track is None:
            return
        note = NoteEvent(start, step * 2, pitch, instrument=track.name)
        track.notes.append(note)
        self.set_project(self.project)
        self.note_added.emit(note)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.project is None:
            return

        step = 60 / self.project.bpm / 4
        changed = False
        for item in self.scene.selectedItems():
            if not isinstance(item, PianoNoteItem):
                continue
            new_start = max(0.0, item.pos().x() / self.pixels_per_second)
            snapped_start = round(new_start / step) * step
            pitch = max(
                self.lowest_pitch,
                min(self.highest_pitch, self.highest_pitch - round(item.pos().y() / self.row_height)),
            )
            item.note.start = snapped_start
            item.note.pitch = pitch
            item.note.duration = max(0.05, item.rect().width() / self.pixels_per_second)
            item.setPos(snapped_start * self.pixels_per_second, self._pitch_y(pitch) + 1)
            changed = True

        if changed:
            self.set_project(self.project)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.project:
            removed = False
            for item in self.scene.selectedItems():
                if isinstance(item, PianoNoteItem):
                    for track in self.project.tracks:
                        if item.note in track.notes:
                            track.notes.remove(item.note)
                            self.note_deleted.emit(item.note)
                            removed = True
                            break
            if removed:
                self.set_project(self.project)
            return
        super().keyPressEvent(event)
