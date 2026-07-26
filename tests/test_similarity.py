import tempfile
import unittest
from pathlib import Path

from mido import Message, MidiFile, MidiTrack

from main import compute_midi_similarity


def write_midi(path: Path, notes: list[tuple[float, float, int]]) -> None:
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    current_tick = 0
    for start, duration, pitch in notes:
        start_tick = int(round(start * 480))
        if start_tick > current_tick:
            delta = start_tick - current_tick
        else:
            delta = 0
        track.append(Message("note_on", note=pitch, velocity=64, time=delta))
        current_tick += delta
        duration_tick = max(1, int(round(duration * 480)))
        track.append(Message("note_off", note=pitch, velocity=0, time=duration_tick))
        current_tick += duration_tick
    midi.tracks.append(track)
    midi.save(path)


class SimilarityTests(unittest.TestCase):
    def test_onset_mismatch_reduces_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.mid"
            reference_path = Path(temp_dir) / "reference.mid"
            write_midi(source_path, [(0.0, 0.3, 60), (0.6, 0.3, 64)])
            write_midi(reference_path, [(0.0, 0.3, 60), (0.3, 0.3, 64)])

            score = compute_midi_similarity(source_path, reference_path)

            self.assertLess(score, 1.0)
            self.assertGreater(score, 0.0)


if __name__ == "__main__":
    unittest.main()
