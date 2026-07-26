from pathlib import Path
from collections import Counter
from mido import MidiFile

midi = MidiFile('train.mid')
notes = []
active = {}
current_tick = 0
tempo_us_per_beat = 500000
ticks_per_beat = midi.ticks_per_beat
for msg in midi:
    if msg.type == 'set_tempo':
        tempo_us_per_beat = msg.tempo
        continue
    if msg.type == 'time_signature':
        continue
    current_tick += msg.time if msg.time else 0
    current_time = current_tick * tempo_us_per_beat / 1_000_000 / ticks_per_beat
    if msg.type == 'note_on' and msg.velocity > 0:
        active[(msg.channel, msg.note)] = current_time
    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
        key = (msg.channel, msg.note)
        if key in active:
            start = active.pop(key)
            notes.append((start, current_time, msg.note, msg.channel))

notes.sort(key=lambda item: item[0])
print('raw notes', len(notes))
# keep the highest-pitched note in each short window and remove obvious chordal duplicates
window = 0.25
selected = []
for idx, note in enumerate(notes):
    start, end, pitch, channel = note
    if idx == 0:
        selected.append(note)
        continue
    prev = selected[-1]
    if start - prev[1] < window and pitch < prev[2]:
        continue
    selected.append(note)
print('selected', len(selected))
for item in selected[:80]:
    print(item)
