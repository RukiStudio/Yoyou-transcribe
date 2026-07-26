from pathlib import Path
from mido import MidiFile

midi = MidiFile('train.mid')
print('tracks', len(midi.tracks))
for i, track in enumerate(midi.tracks):
    print('track', i, 'name', track.name if hasattr(track, 'name') else 'n/a')
    msgs = [msg for msg in track if msg.type in {'note_on','note_off','program_change','track_name','set_tempo','time_signature'}]
    print('  messages', len(msgs))
    for msg in msgs[:30]:
        print('   ', msg)
    print()
