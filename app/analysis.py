"""Audio feature extraction and a lightweight transcription baseline.

This module deliberately separates the user interface from machine-learning work.
The baseline works offline with librosa.  A future Demucs adapter can populate the
same Track model after source separation without changing the editor.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from app.models import NoteEvent, SongProject, Track

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _estimate_key(chroma: np.ndarray) -> str:
    """Estimate a practical major/minor key from aggregate chroma energy."""
    profile_major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    profile_minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    energy = chroma.mean(axis=1)
    if not np.any(energy) or np.std(energy) < 1e-8:
        return "C Major"
    scores: list[tuple[float, str]] = []
    for index, name in enumerate(PITCH_CLASSES):
        major_score = float(np.corrcoef(energy, np.roll(profile_major, index))[0, 1])
        minor_score = float(np.corrcoef(energy, np.roll(profile_minor, index))[0, 1])
        scores.append((major_score if math.isfinite(major_score) else -1, f"{name} Major"))
        scores.append((minor_score if math.isfinite(minor_score) else -1, f"{name} Minor"))
    return max(scores, key=lambda score: score[0])[1]


def _quantize(value: float, step: float) -> float:
    """Snap seconds to a sixteenth-note grid based on the estimated BPM."""
    return max(0.0, round(value / step) * step)


def _create_demo_project() -> SongProject:
    """Provide an editable project so students can explore the interface offline."""
    project = SongProject(title="示例：晴天练习", bpm=112.0, key="C Major", duration=16.0)
    melody = [72, 74, 76, 79, 76, 74, 72, 69, 71, 72, 74, 71, 69, 67, 69, 72]
    project.tracks = [
        Track("主旋律", 0, "#7C5CFC", [NoteEvent(index * 0.5, 0.42, pitch, instrument="主旋律") for index, pitch in enumerate(melody)]),
        Track("和声", 0, "#2CB67D", [NoteEvent(index * 2.0, 1.85, pitch, 72, instrument="和声") for index, pitch in enumerate([60, 65, 67, 60, 57, 62, 65, 60])]),
        Track("贝斯", 33, "#FF9F43", [NoteEvent(index * 2.0, 1.85, pitch, 82, instrument="贝斯") for index, pitch in enumerate([36, 41, 43, 36, 33, 38, 41, 36])]),
        Track("鼓组", 0, "#EF4565", [NoteEvent(index * 0.5, 0.12, 36 if index % 2 == 0 else 42, 100, instrument="鼓组") for index in range(32)]),
    ]
    project.chords = [(0, "C"), (2, "F"), (4, "G"), (6, "C"), (8, "Am"), (10, "Dm7"), (12, "G"), (14, "C")]
    return project


def analyze_audio(path: Path, progress_callback=None) -> SongProject:
    """Analyze audio into an editable, single-pass transcription baseline.

    Results represent the dominant pitched line and onset-based drum rhythm. They
    are intentionally labelled as estimates; advanced separation belongs to the
    optional-model integration layer documented in the README.
    """
    import librosa

    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    report(8, "正在读取音频…")
    audio, sample_rate = librosa.load(path, sr=22050, mono=True)
    duration = len(audio) / sample_rate
    report(24, "正在识别 BPM 与节拍…")
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sample_rate)
    bpm = float(np.asarray(tempo).item()) if np.size(tempo) else 120.0
    bpm = bpm if math.isfinite(bpm) and bpm > 30 else 120.0
    report(40, "正在估算调性与和弦…")
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    key = _estimate_key(chroma)
    report(56, "正在提取主旋律…")
    pitches, magnitudes = librosa.piptrack(y=audio, sr=sample_rate, fmin=librosa.note_to_hz("E2"), fmax=librosa.note_to_hz("C7"))
    frame_times = librosa.frames_to_time(np.arange(pitches.shape[1]), sr=sample_rate)
    dominant = pitches[np.argmax(magnitudes, axis=0), np.arange(pitches.shape[1])]
    hop_seconds = float(frame_times[1] - frame_times[0]) if len(frame_times) > 1 else 0.05
    step = 60.0 / bpm / 4
    melody: list[NoteEvent] = []
    active_pitch: int | None = None
    active_start = 0.0
    for timestamp, frequency in zip(frame_times, dominant, strict=True):
        pitch = int(round(librosa.hz_to_midi(frequency))) if frequency > 0 else None
        if pitch is not None and not 28 <= pitch <= 96:
            pitch = None
        if pitch != active_pitch:
            if active_pitch is not None:
                note_start = _quantize(active_start, step)
                note_duration = max(step, _quantize(float(timestamp - active_start), step))
                if note_duration >= step:
                    melody.append(NoteEvent(note_start, note_duration, active_pitch, 88, 0.68, "主旋律"))
            active_pitch = pitch
            active_start = float(timestamp)
    if active_pitch is not None:
        melody.append(NoteEvent(_quantize(active_start, step), max(step, _quantize(duration - active_start, step)), active_pitch, 88, 0.68, "主旋律"))
    report(78, "正在提取鼓点与和弦标记…")
    onset_times = librosa.onset.onset_detect(y=audio, sr=sample_rate, units="time")
    drums = [NoteEvent(_quantize(float(time), step), step, 36 if index % 2 == 0 else 42, 96, 0.62, "鼓组") for index, time in enumerate(onset_times)]
    beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)
    chord_names = [key.split()[0], "IV", "V", "I"]
    chords = [(float(time), chord_names[index % len(chord_names)]) for index, time in enumerate(beat_times[::4])]
    report(96, "正在整理乐谱…")
    project = SongProject(title=path.stem, audio_path=path, bpm=round(bpm, 1), key=key, duration=duration)
    project.tracks = [Track("主旋律", 0, "#7C5CFC", melody), Track("鼓组", 0, "#EF4565", drums)]
    project.chords = chords
    report(100, "分析完成")
    return project
