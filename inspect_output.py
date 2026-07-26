from pathlib import Path
from mido import MidiFile

midi = MidiFile('music_transcriber_outputs/test_output.mid')
print('tracks', len(midi.tracks))
for i, track in enumerate(midi.tracks):
    name = ''
    msgs = []
    for msg in track:
        if msg.type == 'track_name':
            name = msg.name
        if msg.type in {'note_on','note_off'}:
            msgs.append((msg.type, msg.channel, msg.note, msg.time, msg.velocity))
    print('track', i, name, 'note_events', len(msgs))
    for item in msgs[:20]:
        print(' ', item)
    print()
