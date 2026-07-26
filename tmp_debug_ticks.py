from mido import Message, MidiFile, MidiTrack

midi = MidiFile(ticks_per_beat=480)
track = MidiTrack()
track.append(Message('note_on', note=60, velocity=64, time=0))
track.append(Message('note_off', note=60, velocity=0, time=144))
midi.tracks.append(track)
print('ticks_per_beat', midi.ticks_per_beat)
for msg in midi.tracks[0]:
    print(msg, msg.time)
print('tempo', 500000 / 1000000 / 480)
print('calc', 144 * 500000 / 1000000 / 480)
