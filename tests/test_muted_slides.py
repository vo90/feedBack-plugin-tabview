import io
from types import SimpleNamespace

import guitarpro
import pytest
import rs2gp


@pytest.mark.parametrize('direction', ['up', 'down'])
@pytest.mark.parametrize('ghost', [False, True])
def test_unpitched_slide_roundtrip_keeps_x_ghost_and_direction(direction, ghost):
    song = guitarpro.Song()
    voice = song.tracks[0].measures[0].voices[0]
    note = SimpleNamespace(time=0, string=0, fret=127, sustain=1, mute=True, ghost=ghost,
                           slide_out_marks=[{'direction': direction, 'start': 0, 'end': 1}])
    events = rs2gp._merge_events(SimpleNamespace(notes=[note], chords=[]))
    voice.beats = rs2gp._create_beats(events,
        {'num_beats': 4, 'beat_times': [0, .5, 1, 1.5], 'end_time': 2}, voice, 6)
    buffer = io.BytesIO(); guitarpro.write(song, buffer); buffer.seek(0)
    parsed = guitarpro.parse(buffer).tracks[0].measures[0].voices[0].beats[0].notes[0]
    assert parsed.type == guitarpro.NoteType.dead and parsed.value == 0
    assert parsed.effect.ghostNote == ghost
    assert parsed.effect.slides == [guitarpro.SlideType.outUpwards if direction == 'up' else guitarpro.SlideType.outDownwards]
    assert note.fret == 127


def test_multiple_directions_are_retained_without_extra_attacks_or_fake_slide_target():
    song = guitarpro.Song(); voice = song.tracks[0].measures[0].voices[0]
    events = [{'type': 'note', 'time': 0, 'string': 0, 'fret': 127, 'mute': True,
               'slide_out_marks': [{'direction': 'down', 'start': 0, 'end': .5},
                                   {'direction': 'up', 'start': .5, 'end': 1}]}]
    beats = rs2gp._create_beats(events,
        {'num_beats': 4, 'beat_times': [0, .5, 1, 1.5], 'end_time': 2}, voice, 6)
    assert beats[0].text == 'MUTED SLIDE down then up'
    assert len([n for b in beats for n in b.notes]) == 1
    assert not beats[0].notes[0].effect.slides
