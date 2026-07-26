# Next development todo

## High priority
- Replace the current heuristic melody extraction with a dedicated melody reconstruction pass that uses reference rhythm and pitch contour more explicitly.
- Add a melody-focused evaluation mode that compares only the main melodic line instead of the whole MIDI track mix.
- Tune the analysis pipeline for the provided training audio so the generated melody gets closer to the reference MIDI.

## Medium priority
- Clean up the temporary debug and inspection scripts once the melody pipeline is stabilized.
- Add a CLI flag for "reference-guided melody only" and expose the chosen melody mode in the GUI.
