"""Audio feature extraction and a transcription workflow optimized for noisy MP3 sources.

This module uses optional stem separation, spectral cleaning, and higher-precision
pitch tracking to improve transcription accuracy for melody, bass, harmony, and drums.
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

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
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


def _load_audio(path: Path, sr: int = 22050) -> tuple[np.ndarray, int]:
    import librosa

    audio, sample_rate = librosa.load(path, sr=sr, mono=True)
    if audio.size == 0:
        raise ValueError("无法加载音频：文件为空或格式不受支持。")
    return librosa.util.normalize(audio), sample_rate


def _bandpass_filter(audio: np.ndarray, sr: int, low: float, high: float, order: int = 4) -> np.ndarray:
    try:
        from scipy.signal import butter, filtfilt
    except ImportError:
        return audio
    nyquist = sr / 2.0
    low_cut = max(1.0, low / nyquist)
    high_cut = min(0.999, high / nyquist)
    b, a = butter(order, [low_cut, high_cut], btype="band")
    return filtfilt(b, a, audio)


def _lowpass_filter(audio: np.ndarray, sr: int, cutoff: float, order: int = 4) -> np.ndarray:
    try:
        from scipy.signal import butter, filtfilt
    except ImportError:
        return audio
    nyquist = sr / 2.0
    b, a = butter(order, cutoff / nyquist, btype="low")
    return filtfilt(b, a, audio)


def _spectral_denoise(audio: np.ndarray, sr: int) -> np.ndarray:
    try:
        import noisereduce as nr

        noise_clip = audio[: min(len(audio), sr // 2)]
        return nr.reduce_noise(y=audio, sr=sr, y_noise=noise_clip, prop_decrease=0.85)
    except Exception:
        import librosa

        stft = librosa.stft(audio, n_fft=2048, hop_length=512)
        magnitude, phase = np.abs(stft), np.angle(stft)
        threshold = np.median(magnitude) * 1.4
        mask = magnitude >= threshold
        clean_mag = magnitude * mask
        return librosa.istft(clean_mag * np.exp(1j * phase), hop_length=512, length=len(audio))


def _separate_stems(audio: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    try:
        from spleeter.separator import Separator

        splitter = Separator("spleeter:4stems")
        stereo = np.vstack((audio, audio)).T
        prediction = splitter.separate(stereo)
        melody = librosa.to_mono(prediction["vocals"].T)
        bass = librosa.to_mono(prediction["bass"].T)
        drums = librosa.to_mono(prediction["drums"].T)
        accompaniment = librosa.to_mono(prediction["accompaniment"].T)
        harmony = accompaniment - bass
        return melody, bass, drums, harmony
    except Exception:
        import librosa

        harmonic, percussive = librosa.effects.hpss(audio, margin=4.0)
        bass = _lowpass_filter(harmonic, sr, 250)
        melody = _bandpass_filter(harmonic, sr, 120, 2400)
        harmony = harmonic - bass
        drums = percussive
        return melody, bass, drums, harmony


def _extract_notes_from_f0(
    y: np.ndarray,
    sr: int,
    bpm: float,
    instrument: str,
    fmin: str,
    fmax: str,
    threshold_ratio: float = 0.15,
    min_duration: float | None = None,
    prefer_low: bool = False,
    offset: float = 0.0,
) -> list[NoteEvent]:
    import librosa

    f0, voiced_flag, voiced_probs = librosa.pyin(
        y,
        fmin=librosa.note_to_hz(fmin),
        fmax=librosa.note_to_hz(fmax),
        sr=sr,
        frame_length=2048,
        hop_length=256,
        threshold=0.1,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=256)
    step = 60.0 / bpm / 4
    min_duration = min_duration or step

    notes: list[NoteEvent] = []
    active_pitch = None
    active_start = 0.0
    active_confidence = 0.0
    for index, (timestamp, pitch_hz, voiced) in enumerate(zip(times, f0, voiced_flag)):
        pitch = None
        if voiced and pitch_hz is not None and not np.isnan(pitch_hz):
            candidate = int(round(librosa.hz_to_midi(pitch_hz)))
            if 28 <= candidate <= 96:
                if prefer_low and candidate > 52:
                    candidate = None
                elif voiced_probs is not None:
                    prob = float(voiced_probs[index])
                    if prob >= threshold_ratio:
                        pitch = candidate
                        active_confidence = max(active_confidence, prob)
                else:
                    pitch = candidate
        has_note = pitch is not None
        if has_note and pitch != active_pitch:
            if active_pitch is not None:
                duration = max(min_duration, _quantize(timestamp - active_start, step))
                if duration >= min_duration:
                    notes.append(NoteEvent(_quantize(active_start, step) + offset, duration, active_pitch, 88, min(1.0, active_confidence), instrument))
            active_pitch = pitch
            active_start = float(timestamp)
            active_confidence = float(voiced_probs[index]) if voiced_probs is not None else 0.75
        elif has_note and pitch == active_pitch:
            active_confidence = max(active_confidence, float(voiced_probs[index]) if voiced_probs is not None else 0.75)
        elif not has_note and active_pitch is not None:
            duration = max(min_duration, _quantize(timestamp - active_start, step))
            if duration >= min_duration:
                notes.append(NoteEvent(_quantize(active_start, step) + offset, duration, active_pitch, 88, min(1.0, active_confidence), instrument))
            active_pitch = None

    if active_pitch is not None:
        duration = max(min_duration, _quantize(float(times[-1] + step - active_start), step))
        notes.append(NoteEvent(_quantize(active_start, step) + offset, duration, active_pitch, 88, min(1.0, active_confidence), instrument))
    return notes


def analyze_audio(path: Path, progress_callback=None) -> SongProject:
    """Analyze audio into an editable, multi-track transcription project."""
    import librosa

    def report(percent: int, message: str) -> None:
        if progress_callback:
            progress_callback(percent, message)

    report(8, "正在读取音频…")
    audio, sample_rate = _load_audio(path)
    duration = len(audio) / sample_rate
    report(20, "正在识别 BPM 与节拍…")
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sample_rate, start_bpm=120.0, tightness=100)
    bpm = float(np.asarray(tempo).item()) if np.size(tempo) else 120.0
    bpm = bpm if math.isfinite(bpm) and bpm > 30 else 120.0
    report(34, "正在清洗音频…")
    audio = _spectral_denoise(audio, sample_rate)
    report(48, "正在分轨音频…")
    melody_audio, bass_audio, drums_audio, harmony_audio = _separate_stems(audio, sample_rate)
    report(58, "正在提取调性与和弦…")
    chroma = librosa.feature.chroma_cqt(y=melody_audio, sr=sample_rate)
    key = _estimate_key(chroma)
    report(68, "正在识别主旋律与贝斯…")
    melody = _extract_notes_from_f0(melody_audio, sample_rate, bpm, "主旋律", "C3", "C7", threshold_ratio=0.1)
    bass = _extract_notes_from_f0(bass_audio, sample_rate, bpm, "贝斯", "E1", "C4", threshold_ratio=0.08, min_duration=0.12, prefer_low=True)
    report(78, "正在生成和声与鼓点…")
    harmony, chords = _generate_harmony(duration, bpm, key)
    drums = _extract_drums(drums_audio, sample_rate, bpm)
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


def regenerate_measure(project: SongProject, measure_idx: int, beats_per_measure: int = 4) -> None:
    """Re-generate a single measure from the original audio source if available."""
    if project.audio_path is None or not project.audio_path.exists():
        return

    audio, sample_rate = _load_audio(project.audio_path)
    measure_length = beats_per_measure * 60.0 / project.bpm
    start = measure_idx * measure_length
    if start >= len(audio) / sample_rate:
        return

    segment = _slice_audio_segment(audio, sample_rate, start, measure_length)
    melody_audio, bass_audio, drums_audio, harmony_audio = _separate_stems(segment, sample_rate)
    melody = _extract_notes_from_f0(
        melody_audio,
        sample_rate,
        project.bpm,
        "主旋律",
        "C3",
        "C7",
        threshold_ratio=0.1,
        offset=start,
    )
    bass = _extract_notes_from_f0(
        bass_audio,
        sample_rate,
        project.bpm,
        "贝斯",
        "E1",
        "C4",
        threshold_ratio=0.08,
        min_duration=0.12,
        prefer_low=True,
        offset=start,
    )
    drums = _extract_drums(drums_audio, sample_rate, project.bpm)
    for note in drums:
        note.start = min(note.start + start, project.duration)

    measure_start = start
    measure_end = start + measure_length
    for track in project.tracks:
        track.notes = [
            note for note in track.notes
            if note.end <= measure_start or note.start >= measure_end
        ]

    for track in project.tracks:
        if track.name == "主旋律":
            track.notes.extend(melody)
        elif track.name == "贝斯":
            track.notes.extend(bass)
        elif track.name == "鼓组":
            track.notes.extend(drums)
        elif track.name == "和声":
            harmony, _ = _generate_harmony(measure_length, project.bpm, project.key)
            for note in harmony:
                note.start = min(note.start + start, project.duration)
            track.notes.extend(harmony)

    project.update_measure_metadata()
