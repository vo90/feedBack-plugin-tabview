"""GP5 display export must not turn FeedPak's unpitched mute into fret 127."""
import io
from types import SimpleNamespace

import guitarpro
import rs2gp


def test_mixed_chord_preserves_harmonic_and_mutes_without_sentinel_pitch():
    gp = guitarpro.Song()
    voice = gp.tracks[0].measures[0].voices[0]
    original = [
        {"string": 0, "fret": 127, "mute": True},
        {"string": 1, "fret": 5, "mute": True},
        {"string": 2, "fret": 4, "harmonic": True},
        {"string": 3, "fret": 0},
    ]
    info = {"num_beats": 4, "beat_times": [0, .5, 1, 1.5], "end_time": 2}
    voice.beats = rs2gp._create_beats(
        [{"time": 0, "type": "chord", "chord_notes": original}], info, voice, 6)
    notes = voice.beats[0].notes
    assert [(n.string, n.value, n.type) for n in notes] == [
        (6, 0, guitarpro.NoteType.dead), (5, 5, guitarpro.NoteType.dead),
        (4, 4, guitarpro.NoteType.normal), (3, 0, guitarpro.NoteType.normal),
    ]
    assert isinstance(notes[2].effect.harmonic, guitarpro.NaturalHarmonic)
    assert original[0]["fret"] == 127  # the source chart is never changed

    # The actual binary round trip retains all chord members and their effects.
    data = io.BytesIO()
    guitarpro.write(gp, data)
    data.seek(0)
    parsed = guitarpro.parse(data).tracks[0].measures[0].voices[0].beats[0].notes
    assert [(n.string, n.value, n.type) for n in parsed] == [
        (n.string, n.value, n.type) for n in reversed(notes)]
    assert isinstance(next(n for n in parsed if n.string == 4).effect.harmonic,
                      guitarpro.NaturalHarmonic)


def test_standalone_unpitched_mute_is_kept_as_a_dead_note():
    gp = guitarpro.Song()
    voice = gp.tracks[0].measures[0].voices[0]
    events = rs2gp._merge_events(SimpleNamespace(
        notes=[SimpleNamespace(time=0, string=2, fret=127, sustain=.5, mute=True)],
        chords=[]))
    notes = rs2gp._create_beats(events,
        {"num_beats": 4, "beat_times": [0, .5, 1, 1.5], "end_time": 2}, voice, 6)[0].notes
    assert len(notes) == 1
    assert notes[0].value == 0
    assert notes[0].type == guitarpro.NoteType.dead
    assert notes[0].string == 4
