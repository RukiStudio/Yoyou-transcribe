import tempfile
from pathlib import Path
from mido import Message, MidiFile, MidiTrack
from main import extract_notes_from_midi, compute_midi_similarity


def write_midi(path: Path, notes: list[tuple[float, float, int]]) -> None:
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    current_tick = 0
    for start, duration, pitch in notes:
        start_tick = int(round(start * 480))
        if start_tick > current_tick:
            track.append(Message('note_on', note=pitch, velocity=64, time=start_tick - current_tick))
            current_tick = start_tick
        else:
            track.append(Message('note_on', note=pitch, velocity=64, time=0))
        duration_tick = max(1, int(round(duration * 480)))
        track.append(Message('note_off', note=pitch, velocity=0, time=duration_tick))
        current_tick += duration_tick
    midi.tracks.append(track)
    midi.save(path)

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / 'x.mid'
    q = Path(d) / 'y.mid'
    write_midi(p, [(0.0, 0.3, 60), (0.5, 0.5, 64)])
    write_midi(q, [(0.0, 0.5, 60), (0.5, 0.5, 64)])
    print('source notes', extract_notes_from_midi(p))
    print('reference notes', extract_notes_from_midi(q))
    print('similarity', compute_midi_similarity(p, q))
