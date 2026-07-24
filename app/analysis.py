"""Audio feature extraction and a lightweight transcription baseline.

This module deliberately separates the user interface from machine-learning work.
The baseline works offline with librosa and leverages harmonic/percussive
separation, stronger pitch selection, and per-measure confidence tracking.
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


def _chord_root_and_mode(key_name: str) -> tuple[int, str]:
    root_name, mode = key_name.split()
    root_pitch = PITCH_CLASSES.index(root_name) if root_name in PITCH_CLASSES else 0
    return root_pitch, mode


def _build_chord_progression(root_pitch: int, mode: str) -> list[tuple[str, list[int]]]:
    if mode == "Minor":
        degrees = [0, 5, 7, 0]
        quality = ["m", "m", "", "m"]
    else:
        degrees = [0, 5, 7, 0]
        quality = ["", "", "", ""]
    progression: list[tuple[str, list[int]]] = []
    for degree, suffix in zip(degrees, quality):
        chord_root = (root_pitch + degree) % 12
        name = f"{PITCH_CLASSES[chord_root]}{suffix}"
        third = 4 if suffix == "" else 3
        progression.append((name, [chord_root, chord_root + third, chord_root + 7]))
    return progression


def _extract_pitched_line(
    y: np.ndarray,
    sr: int,
    bpm: float,
    instrument: str,
    fmin: str,
    fmax: str,
    threshold_ratio: float = 0.15,
    prefer_low: bool = False,
    offset: float = 0.0,
) -> list[NoteEvent]:
    import librosa

    pitches, magnitudes = librosa.piptrack(
        y=y,
        sr=sr,
        fmin=librosa.note_to_hz(fmin),
        fmax=librosa.note_to_hz(fmax),
    )
    frame_times = librosa.frames_to_time(np.arange(pitches.shape[1]), sr=sr)
    max_mag = float(np.max(magnitudes)) if np.any(magnitudes) else 1.0
    step = 60.0 / bpm / 4

    melody: list[NoteEvent] = []
    active_pitch: int | None = None
    active_start = 0.0
    active_confidence = 0.0

    for timestamp, mag_frame in zip(frame_times, magnitudes.T, strict=True):
        best_index = int(np.argmax(mag_frame))
        magnitude = float(mag_frame[best_index])
        pitch = int(round(librosa.hz_to_midi(pitches[best_index, int(round(timestamp * sr / 512))]))) if magnitude >= threshold_ratio * max_mag else None
        if pitch is not None and not 28 <= pitch <= 96:
            pitch = None
        if prefer_low and pitch is not None and pitch > 52:
            pitch = None
        if pitch != active_pitch:
            if active_pitch is not None:
                note_start = _quantize(active_start, step)
                note_duration = max(step, _quantize(float(timestamp - active_start), step))
                if note_duration >= step:
                    melody.append(NoteEvent(note_start + offset, note_duration, active_pitch, 88, min(1.0, active_confidence), instrument))
            active_pitch = pitch
            active_start = float(timestamp)
            active_confidence = magnitude / max_mag if pitch is not None else 0.0
        elif pitch is not None:
            active_confidence = max(active_confidence, magnitude / max_mag)

    if active_pitch is not None:
        note_start = _quantize(active_start, step)
        note_duration = max(step, _quantize(float(frame_times[-1] + step - active_start), step))
        melody.append(NoteEvent(note_start + offset, note_duration, active_pitch, 88, min(1.0, active_confidence), instrument))
    return melody


def _extract_drums(y: np.ndarray, sr: int, bpm: float) -> list[NoteEvent]:
    import librosa

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time", backtrack=False)
    step = 60.0 / bpm / 4
    strength_profile = librosa.util.normalize(onset_env, norm=2) if onset_env.size else np.array([])
    drums: list[NoteEvent] = []
    for time in onset_times:
        onset_frame = int(round(time * sr / 512))
        if 0 <= onset_frame < len(strength_profile):
            confidence = min(1.0, float(strength_profile[onset_frame]))
        else:
            confidence = 0.75
        is_downbeat = round(time / step) % 4 == 0
        note = 36 if is_downbeat else 42 if time % (step * 2) < step else 38
        drums.append(NoteEvent(_quantize(float(time), step), step * 0.8, note, 96, confidence, "鼓组"))
    return drums


def _generate_harmony(duration: float, bpm: float, key: str) -> tuple[list[NoteEvent], list[tuple[float, str]]]:
    root_pitch, mode = _chord_root_and_mode(key)
    progression = _build_chord_progression(root_pitch, mode)
    measure_length = 60.0 / bpm * 4
    harmony: list[NoteEvent] = []
    chords: list[tuple[float, str]] = []
    for index, measure_start in enumerate(np.arange(0, duration, measure_length)):
        chord_name, chord_notes = progression[index % len(progression)]
        current_duration = min(measure_length, max(0.1, duration - measure_start))
        chords.append((float(measure_start), chord_name))
        for pitch in chord_notes:
            harmony.append(NoteEvent(float(measure_start), current_duration, pitch + 48, 72, 0.72, "和声"))
    return harmony, chords


def _create_demo_project() -> SongProject:
    """Provide an editable project so students can explore the interface offline."""
    project = SongProject(title="示例：晴天练习", bpm=112.0, key="C Major", duration=16.0)
    melody = [72, 74, 76, 79, 76, 74, 72, 69, 71, 72, 74, 71, 69, 67, 69, 72]
    project.tracks = [
        Track("主旋律", 0, "#7C5CFC", [NoteEvent(index * 0.5, 0.42, pitch, 96, 0.95, "主旋律") for index, pitch in enumerate(melody)]),
        Track("和声", 48, "#2CB67D", [NoteEvent(index * 2.0, 1.85, pitch, 72, 0.88, "和声") for index, pitch in enumerate([60, 65, 67, 60, 57, 62, 65, 60])]),
        Track("贝斯", 33, "#FF9F43", [NoteEvent(index * 2.0, 1.85, pitch, 82, 0.88, "贝斯") for index, pitch in enumerate([36, 41, 43, 36, 33, 38, 41, 36])]),
        Track("鼓组", 0, "#EF4565", [NoteEvent(index * 0.5, 0.12, 36 if index % 2 == 0 else 42, 100, 0.86, "鼓组") for index in range(32)]),
    ]
    project.chords = [(0, "C"), (2, "F"), (4, "G"), (6, "C"), (8, "Am"), (10, "Dm7"), (12, "G"), (14, "C")]
    project.update_measure_metadata()
    return project


def _slice_audio_segment(audio: np.ndarray, sr: int, start: float, duration: float) -> np.ndarray:
    start_sample = max(0, int(round(start * sr)))
    end_sample = min(len(audio), int(round((start + duration) * sr)))
    return audio[start_sample:end_sample]


def regenerate_measure(project: SongProject, measure_idx: int, beats_per_measure: int = 4) -> None:
    if project.audio_path is None:
        return
    import librosa

    audio, sr = librosa.load(project.audio_path, sr=22050, mono=True)
    measure_length = beats_per_measure * 60.0 / project.bpm
    start_time = measure_idx * measure_length
    segment = _slice_audio_segment(audio, sr, start_time, measure_length)
    if segment.size == 0:
        return

    harmonic, percussive = librosa.effects.hpss(segment)
    melody = _extract_pitched_line(
        harmonic,
        sr,
        project.bpm,
        "主旋律",
        fmin="C3",
        fmax="C7",
        threshold_ratio=0.16,
        offset=start_time,
    )

    melody_track = next((track for track in project.tracks if track.name == "主旋律"), None)
    if melody_track is None:
        melody_track = Track("主旋律", 0, "#7C5CFC", [])
        project.tracks.insert(0, melody_track)

    project.tracks = [
        Track(track.name, track.program, track.color, [note for note in track.notes if note.start < start_time or note.start >= start_time + measure_length], track.muted, track.solo)
        if track.name == melody_track.name else track
        for track in project.tracks
    ]
    melody_track.notes = [note for note in melody_track.notes if note.start < start_time or note.start >= start_time + measure_length]
    melody_track.notes.extend(melody)
    project.update_measure_metadata()


def analyze_audio(path: Path, progress_callback=None) -> SongProject:
    """Analyze audio into an editable, single-pass transcription baseline."""
    import librosa

    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    report(8, "正在读取音频…")
    audio, sample_rate = librosa.load(path, sr=22050, mono=True)
    duration = len(audio) / sample_rate
    report(22, "正在识别 BPM 与节拍…")
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sample_rate, start_bpm=120.0, tightness=100)
    bpm = float(np.asarray(tempo).item()) if np.size(tempo) else 120.0
    bpm = bpm if math.isfinite(bpm) and bpm > 30 else 120.0
    report(38, "正在估算调性与和弦…")
    harmonic, percussive = librosa.effects.hpss(audio)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sample_rate)
    key = _estimate_key(chroma)
    report(54, "正在分轨提取主旋律与贝斯…")
    melody = _extract_pitched_line(harmonic, sample_rate, bpm, "主旋律", "C3", "C7", threshold_ratio=0.16)
    bass = _extract_pitched_line(harmonic, sample_rate, bpm, "贝斯", "E1", "C4", threshold_ratio=0.12, prefer_low=True)
    harmony, chords = _generate_harmony(duration, bpm, key)
    report(72, "正在提取鼓点…")
    drums = _extract_drums(percussive, sample_rate, bpm)
    report(88, "正在处理结果与置信度…")
    project = SongProject(title=path.stem, audio_path=path, bpm=round(bpm, 1), key=key, duration=duration)
    project.tracks = [
        Track("主旋律", 0, "#7C5CFC", melody),
        Track("和声", 48, "#2CB67D", harmony),
        Track("贝斯", 33, "#FF9F43", bass),
        Track("鼓组", 0, "#EF4565", drums),
    ]
    project.chords = chords
    project.update_measure_metadata()
    report(100, "分析完成")
    return project
