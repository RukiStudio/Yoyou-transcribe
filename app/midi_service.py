"""MIDI export and lightweight WAV preview generation."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from app.models import SongProject


def export_midi(project: SongProject, destination: Path) -> None:
    """Write all editable tracks to a standard MIDI file."""
    midi = MidiFile(ticks_per_beat=480)
    conductor = MidiTrack()
    conductor.append(MetaMessage("track_name", name=project.title, time=0))
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(project.bpm), time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    midi.tracks.append(conductor)
    for track_index, source_track in enumerate(project.tracks):
        midi_track = MidiTrack()
        midi_track.append(MetaMessage("track_name", name=source_track.name, time=0))
        channel = 9 if source_track.name == "鼓组" else min(track_index, 8)
        if channel != 9:
            midi_track.append(Message("program_change", program=source_track.program, channel=channel, time=0))
        events = []
        for note in source_track.notes:
            events.extend([(note.start, True, note), (note.end, False, note)])
        previous_tick = 0
        for time_seconds, is_start, note in sorted(events, key=lambda event: (event[0], not event[1])):
            absolute_tick = round(time_seconds * project.bpm / 60 * midi.ticks_per_beat)
            delta = max(0, absolute_tick - previous_tick)
            message_type = "note_on" if is_start else "note_off"
            velocity = note.velocity if is_start else 0
            midi_track.append(Message(message_type, note=note.pitch, velocity=velocity, channel=channel, time=delta))
            previous_tick = absolute_tick
        midi.tracks.append(midi_track)
    midi.save(destination)


def build_preview_wav(project: SongProject) -> Path:
    """Synthesize a short piano-roll preview without external MIDI hardware."""
    sample_rate = 22050
    length = max(1.0, min(project.duration or 16.0, 45.0))
    buffer = np.zeros(int(length * sample_rate), dtype=np.float32)
    for note in project.all_notes():
        if note.start >= length or note.instrument == "鼓组":
            continue
        start = int(note.start * sample_rate)
        stop = min(len(buffer), int(note.end * sample_rate))
        if stop <= start:
            continue
        times = np.arange(stop - start) / sample_rate
        frequency = 440 * 2 ** ((note.pitch - 69) / 12)
        envelope = np.minimum(1, times * 24) * np.exp(-times * 2.2)
        buffer[start:stop] += 0.14 * np.sin(2 * np.pi * frequency * times) * envelope
    audio = (np.clip(buffer, -1, 1) * 32767).astype(np.int16)
    output = Path(tempfile.gettempdir()) / "ruki_music_preview.wav"
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return output
