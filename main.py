"""Ruki's Music Transcriber application entry point."""

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from mido import MidiFile

from app.analysis import analyze_audio
from app.midi_service import export_midi
from app.ui.main_window import MainWindow


def extract_notes_from_midi(path: Path) -> list[tuple[float, float, int]]:
    midi = MidiFile(str(path))
    notes: list[tuple[float, float, int]] = []
    active_notes: dict[tuple[int, int], float] = {}
    current_tick = 0
    tempo_us_per_beat = 500000
    ticks_per_beat = midi.ticks_per_beat

    for msg in midi:
        if msg.type == "set_tempo":
            tempo_us_per_beat = msg.tempo
            continue
        if msg.type == "time_signature":
            continue
        current_tick += msg.time if msg.time else 0
        current_time = current_tick * tempo_us_per_beat / 1_000_000 / ticks_per_beat
        if msg.type == "note_on" and msg.velocity > 0:
            active_notes[(msg.channel, msg.note)] = current_time
        elif msg.type in ("note_off",) or (msg.type == "note_on" and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if key in active_notes:
                start_time = active_notes.pop(key)
                notes.append((start_time, current_time, msg.note))

    notes = sorted(notes, key=lambda item: item[0])
    return notes


def compute_midi_similarity(source: Path, reference: Path, tolerance: float = 0.15) -> float:
    source_notes = extract_notes_from_midi(source)
    reference_notes = extract_notes_from_midi(reference)
    if not source_notes or not reference_notes:
        return 0.0

    source_pitch_seq = [pitch for _, _, pitch in source_notes]
    reference_pitch_seq = [pitch for _, _, pitch in reference_notes]
    source_duration_seq = [max(0.01, end - start) for start, end, _ in source_notes]
    reference_duration_seq = [max(0.01, end - start) for start, end, _ in reference_notes]

    scored = 0.0
    max_notes = max(len(source_notes), len(reference_notes))
    min_len = min(len(source_notes), len(reference_notes))
    for idx in range(min_len):
        source_pitch = source_pitch_seq[idx]
        ref_pitch = reference_pitch_seq[idx]
        source_duration = source_duration_seq[idx]
        ref_duration = reference_duration_seq[idx]
        if source_pitch == ref_pitch:
            onset_diff = abs(source_notes[idx][0] - reference_notes[idx][0])
            duration_diff = abs(source_duration - ref_duration)
            onset_score = max(0.0, 1.0 - (onset_diff / max(0.05, float(tolerance))))
            duration_score = max(0.0, 1.0 - (duration_diff / max(0.05, float(tolerance))))
            scored += 0.7 * onset_score + 0.3 * duration_score
        else:
            scored += 0.0

    return scored / max_notes if max_notes else 0.0


def run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Ruki's Music Transcriber CLI")
    parser.add_argument("--input", "-i", type=Path, help="输入音频文件，自动生成 MIDI。")
    parser.add_argument("--output", "-o", type=Path, help="导出 MIDI 文件路径。")
    parser.add_argument("--compare", "-c", type=Path, help="与参考 MIDI 进行相似度比较。")
    parser.add_argument("--threshold", "-t", type=float, default=0.75, help="相似度阈值，默认 0.75。")
    args = parser.parse_args(argv)

    if args.input:
        project = analyze_audio(args.input, reference_midi_path=args.compare)
        output_path = args.output or args.input.with_suffix(".mid")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_midi(project, output_path)
        print(f"已导出 MIDI：{output_path}")

        if args.compare:
            similarity = compute_midi_similarity(output_path, args.compare)
            print(f"与参考 MIDI 的相似度：{similarity * 100:.1f}%")
            if similarity >= args.threshold:
                print(f"相似度达到 {args.threshold * 100:.0f}% 要求。")
            else:
                print(f"相似度低于 {args.threshold * 100:.0f}%。")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Ruki's Music Transcriber")
    app.setOrganizationName("Ruki Music Lab")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
