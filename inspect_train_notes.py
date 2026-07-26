from mido import MidiFile
from collections import Counter

midi = MidiFile('train.mid')
track = midi.tracks[6]
notes = []
active = {}
current_time = 0.0
for msg in track:
    current_time += msg.time if msg.time else 0.0
    if msg.type == 'note_on' and msg.velocity > 0:
        active[(msg.channel, msg.note)] = current_time
    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
        key = (msg.channel, msg.note)
        if key in active:
            start = active.pop(key)
            notes.append((start, current_time - start, msg.note))

print('notes', len(notes))
for item in notes[:80]:
    print(item)

pitch_counter = Counter(note[2] for note in notes)
print('pitch_counter', pitch_counter)
