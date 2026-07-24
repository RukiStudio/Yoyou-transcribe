"""Application data models kept independent from the user interface."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NoteEvent:
    """A quantized MIDI note ready for display, editing, preview, and export."""

    start: float
    duration: float
    pitch: int
    velocity: int = 88
    confidence: float = 0.75
    instrument: str = "未知"

    @property
    def end(self) -> float:
        """Return the end time in seconds."""
        return self.start + self.duration


@dataclass
class Track:
    """A logical source track, even when source separation is unavailable."""

    name: str
    program: int
    color: str
    notes: list[NoteEvent] = field(default_factory=list)
    muted: bool = False
    solo: bool = False


@dataclass
class SongProject:
    """All editable analysis results for one imported song."""

    title: str = "未命名工程"
    audio_path: Path | None = None
    bpm: float = 120.0
    key: str = "C Major"
    duration: float = 0.0
    time_signature: str = "4/4"
    tracks: list[Track] = field(default_factory=list)
    chords: list[tuple[float, str]] = field(default_factory=list)
    measures: list[dict] = field(default_factory=list)

    def all_notes(self) -> list[NoteEvent]:
        """Return notes from tracks that are not muted."""
        return [note for track in self.tracks if not track.muted for note in track.notes]

    def measure_notes(self, measure_idx: int, beats_per_measure: int = 4) -> list[NoteEvent]:
        """Return notes belonging to a specific measure for per-measure replacement."""
        measure_length = beats_per_measure * 60.0 / self.bpm
        start_t = measure_idx * measure_length
        end_t = start_t + measure_length
        return [n for n in self.all_notes() if start_t <= n.start < end_t]

    def measure_confidence(self, measure_idx: int, beats_per_measure: int = 4) -> float:
        """Return the highest confidence in a measure; 0.0 if no notes."""
        notes = self.measure_notes(measure_idx, beats_per_measure)
        return max((n.confidence for n in notes), default=0.0)

    def update_measure_metadata(self, beats_per_measure: int = 4) -> None:
        """Refresh per-measure confidence metadata for the current project."""
        measure_length = beats_per_measure * 60.0 / self.bpm
        measure_count = max(1, math.ceil(self.duration / measure_length))
        self.measures = [
            {
                "index": index,
                "confidence": round(self.measure_confidence(index, beats_per_measure), 2),
                "notes": len(self.measure_notes(index, beats_per_measure)),
            }
            for index in range(measure_count)
        ]

    def export_notes(self, beats_per_measure: int = 4) -> list[NoteEvent]:
        """Return a deduplicated, highest-confidence note set for MIDI export."""
        buckets: dict[tuple[int, int, int], NoteEvent] = {}
        for note in self.all_notes():
            measure_idx = int(note.start // (beats_per_measure * 60.0 / self.bpm))
            key = (measure_idx, round(note.start, 4), note.pitch)
            existing = buckets.get(key)
            if existing is None or note.confidence > existing.confidence:
                buckets[key] = note
        return sorted(buckets.values(), key=lambda note: (note.start, note.pitch))

