"""MIDI export and lightweight WAV preview generation."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from app.models import SongProject


def _safe_meta_name(name: str) -> str:
    return name.encode("latin-1", errors="replace").decode("latin-1")


def export_midi(project: SongProject, destination: Path, notes: list[NoteEvent] | None = None) -> None:
    """Write selected notes from an editable project to a standard MIDI file."""
    midi = MidiFile(ticks_per_beat=480)
    conductor = MidiTrack()
    conductor.append(MetaMessage("track_name", name=_safe_meta_name(project.title), time=0))
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(project.bpm), time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    midi.tracks.append(conductor)
    note_set = list(notes) if notes is not None else None
    for track_index, source_track in enumerate(project.tracks):
        track_notes = [note for note in source_track.notes if note_set is None or note in note_set]
        if not track_notes:
            continue
        midi_track = MidiTrack()
        midi_track.append(MetaMessage("track_name", name=_safe_meta_name(source_track.name), time=0))
        channel = 9 if source_track.name == "鼓组" else min(track_index, 8)
        if channel != 9:
            midi_track.append(Message("program_change", program=source_track.program, channel=channel, time=0))

        sorted_notes = sorted(track_notes, key=lambda note: (note.start, note.end, note.pitch))
        active_notes: dict[int, tuple[float, NoteEvent]] = {}
        previous_tick = 0
        for note in sorted_notes:
            absolute_tick = round(note.start * project.bpm / 60 * midi.ticks_per_beat)
            delta = max(0, absolute_tick - previous_tick)
            if delta > 0:
                for pitch, active_note in list(active_notes.items()):
                    end_tick = round(active_note[0] * project.bpm / 60 * midi.ticks_per_beat)
                    if end_tick <= absolute_tick:
                        midi_track.append(Message("note_off", note=pitch, velocity=0, channel=channel, time=max(0, end_tick - previous_tick)))
                        previous_tick = end_tick
                        active_notes.pop(pitch, None)
            midi_track.append(Message("note_on", note=note.pitch, velocity=note.velocity, channel=channel, time=delta))
            previous_tick = absolute_tick
            active_notes[note.pitch] = (note.end, note)

        for pitch, (end_time, note) in list(active_notes.items()):
            absolute_tick = round(end_time * project.bpm / 60 * midi.ticks_per_beat)
            delta = max(0, absolute_tick - previous_tick)
            midi_track.append(Message("note_off", note=pitch, velocity=0, channel=channel, time=delta))
            previous_tick = absolute_tick

        midi.tracks.append(midi_track)
    midi.save(destination)


def build_preview_wav(project: SongProject) -> Path:
    """Synthesize a short multi-instrument preview without external MIDI hardware."""
    sample_rate = 22050
    length = max(1.0, min(project.duration or 16.0, 45.0))
    buffer = np.zeros(int(length * sample_rate), dtype=np.float32)
    for note in project.all_notes():
        if note.start >= length:
            continue
        start = int(note.start * sample_rate)
        stop = min(len(buffer), int(note.end * sample_rate))
        if stop <= start:
            continue
        times = np.arange(stop - start) / sample_rate
        if note.instrument == "鼓组":
            envelope = np.exp(-times * 18)
            noise = np.random.randn(stop - start).astype(np.float32) * envelope
            buffer[start:stop] += 0.24 * noise
            continue

        frequency = 440 * 2 ** ((note.pitch - 69) / 12)
        if note.instrument == "贝斯":
            waveform = np.sign(np.sin(2 * np.pi * frequency * times)) * np.exp(-times * 2.5)
            buffer[start:stop] += 0.18 * waveform
        elif note.instrument == "和声":
            waveform = np.sin(2 * np.pi * frequency * times) * np.exp(-times * 2.0)
            buffer[start:stop] += 0.12 * waveform
        else:
            waveform = np.sin(2 * np.pi * frequency * times)
            envelope = np.minimum(1.0, times * 20) * np.exp(-times * 1.9)
            buffer[start:stop] += 0.16 * waveform * envelope

    audio = (np.clip(buffer, -1, 1) * 32767).astype(np.int16)
    output = Path(tempfile.gettempdir()) / "ruki_music_preview.wav"
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return output
