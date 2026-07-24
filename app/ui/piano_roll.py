"""Interactive piano-roll editor for inspected transcription notes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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


class PianoRoll(QGraphicsView):
    """A focused piano roll: click notes, double-click empty space to add one."""

    note_selected = Signal(object)
    note_added = Signal(object)
    note_deleted = Signal(object)

    pixels_per_second = 92
    row_height = 15
    highest_pitch = 96
    lowest_pitch = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.project: SongProject | None = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#121827"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

    def _pitch_y(self, pitch: int) -> float:
        return (self.highest_pitch - pitch) * self.row_height

    def set_project(self, project: SongProject) -> None:
        """Redraw grid, chord labels and all project notes."""
        self.project = project
        self.scene.clear()
        height = (self.highest_pitch - self.lowest_pitch + 1) * self.row_height
        width = max(900, (project.duration + 4) * self.pixels_per_second)
        self.scene.setSceneRect(0, 0, width, height)
        grid_pen = QPen(QColor("#273044"))
        for pitch in range(self.lowest_pitch, self.highest_pitch + 1):
            y = self._pitch_y(pitch)
            self.scene.addLine(0, y, width, y, grid_pen)
        seconds_per_beat = 60 / project.bpm
        for beat in range(int(project.duration / seconds_per_beat) + 3):
            x = beat * seconds_per_beat * self.pixels_per_second
            pen = QPen(QColor("#65708A") if beat % 4 == 0 else QColor("#273044"))
            self.scene.addLine(x, 0, x, height, pen)
        for start, chord in project.chords:
            label = self.scene.addText(chord)
            label.setDefaultTextColor(QColor("#FFD166"))
            label.setPos(start * self.pixels_per_second + 5, 5)
        for track in project.tracks:
            for note in track.notes:
                item = PianoNoteItem(note, track.color, note.start * self.pixels_per_second, self._pitch_y(note.pitch) + 1, max(5, note.duration * self.pixels_per_second), self.row_height - 2)
                self.scene.addItem(item)
        self.centerOn(0, self._pitch_y(60))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        item = self.itemAt(event.pos())
        if isinstance(item, PianoNoteItem):
            self.note_selected.emit(item.note)

    def mouseDoubleClickEvent(self, event):
        """Add a snapped note to the first track when students double-click."""
        item = self.itemAt(event.pos())
        # Grid lines are also graphics items, so only existing notes block creation.
        if self.project and not isinstance(item, PianoNoteItem):
            point = self.mapToScene(event.pos())
            step = 60 / self.project.bpm / 4
            start = max(0, round((point.x() / self.pixels_per_second) / step) * step)
            pitch = max(self.lowest_pitch, min(self.highest_pitch, self.highest_pitch - round(point.y() / self.row_height)))
            note = NoteEvent(start, step * 2, pitch, instrument=self.project.tracks[0].name)
            self.project.tracks[0].notes.append(note)
            self.set_project(self.project)
            self.note_added.emit(note)
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.project:
            for item in self.scene.selectedItems():
                if isinstance(item, PianoNoteItem):
                    for track in self.project.tracks:
                        if item.note in track.notes:
                            track.notes.remove(item.note)
                            self.note_deleted.emit(item.note)
                            break
            self.set_project(self.project)
            return
        super().keyPressEvent(event)
