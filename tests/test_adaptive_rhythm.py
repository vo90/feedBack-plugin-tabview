"""Read the serialized GP5 back: assert actual pitches, attacks and positions."""
from copy import deepcopy
from fractions import Fraction as F
from io import BytesIO
from types import SimpleNamespace as Obj

import guitarpro
import pytest
import rhythm
import rs2gp


def song_at(positions, step=None, times=(0, .5, 1, 1.5, 2), strings=None):
    measure = dict(beat_times=list(times[:-1]), end_time=times[-1], num_beats=4)
    notes = []
    for i, q in enumerate(positions):
        end = q + step if step is not None else positions[i+1] if i+1 < len(positions) else 4
        notes.append(Obj(time=rhythm.seconds(float(q), measure),
            sustain=rhythm.seconds(float(end), measure)-rhythm.seconds(float(q), measure),
            string=strings[i] if strings else 0, fret=7 if i%2==0 else 9,
            hammer_on=i%2==1, pull_off=i>0 and i%2==0))
    arr = Obj(path_bass=False, name='Lead', tuning=[0]*6, notes=notes, chords=[])
    # An extra measure marker gives the first measure its exact ending time.
    return Obj(title='Rhythm fixture', artist='Synthetic', album='', song_length=times[-1]+.5,
        arrangements=[arr], beats=[Obj(time=t, measure=i//4 if i%4==0 else -1) for i,t in enumerate(times)])


def export(song):
    return guitarpro.parse(BytesIO(rs2gp.arrangement_to_gp5(song)))


def attacks(gp, bar=0):
    result=[]
    q=F(0)
    for beat in gp.tracks[0].measures[bar].voices[0].beats:
        for note in beat.notes:
            if note.type != guitarpro.NoteType.tie:
                result.append((q, note.value, note.effect.hammer, note.string))
        q += F(beat.duration.time, 960)
    assert q == 4
    return result


@pytest.mark.parametrize('division', [8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56])
def test_dense_binary_and_tuplet_notes_survive_gp5_roundtrip(division):
    positions=[F(i,division) for i in range(division)]
    song=song_at(positions,step=F(1,division))
    original=deepcopy(song)
    actual=attacks(export(song))
    assert [(q,f,h) for q,f,h,_ in actual] == [(q,7 if i%2==0 else 9,i>0) for i,q in enumerate(positions)]
    assert song == original


def test_mixed_binary_triplet_measure_and_tied_duration_remainder():
    positions=[F(0),F(1,32),F(1,3),F(1,2),F(1)]
    gp=export(song_at(positions))
    assert [a[0] for a in attacks(gp)] == positions
    notes=[n for b in gp.tracks[0].measures[0].voices[0].beats for n in b.notes]
    assert any(n.type==guitarpro.NoteType.tie for n in notes)
    assert all(not n.effect.hammer for n in notes if n.type==guitarpro.NoteType.tie)


def test_variable_beat_intervals_use_musical_time_not_average_tempo():
    positions=[F(i,16) for i in range(64)]
    gp=export(song_at(positions,step=F(1,16),times=(0,.5,.9,1.2,1.6)))
    assert [a[0] for a in attacks(gp)] == positions


def test_sequential_strings_stay_separate_and_true_chord_stays_simultaneous():
    song=song_at([F(0),F(1,16),F(1,8)],strings=[0,1,2])
    extra=deepcopy(song.arrangements[0].notes[0]);extra.string=3;extra.fret=12
    song.arrangements[0].notes.append(extra)
    actual=attacks(export(song))
    assert [(q,f) for q,f,_,_ in actual] == [(0,12),(0,7),(F(1,16),9),(F(1,8),7)]


def test_ordinary_binary_rhythm_retains_existing_grid():
    song=song_at([F(0),F(1,8),F(1,2),F(1),F(2),F(3)])
    measure=rs2gp._parse_measures(song.beats)[0]
    grid,_=rhythm.layout(rs2gp._merge_events(song.arrangements[0]),measure)
    assert grid == 8
    assert [a[0] for a in attacks(export(song))] == [0,F(1,8),F(1,2),1,2,3]


def test_unrepresentable_density_reports_measure_instead_of_discarding_note():
    with pytest.raises(rhythm.RhythmError,match='Measure 1:.*closely spaced'):
        export(song_at([F(0),F(1,1000)]))


def test_millisecond_rounding_keeps_tuplets_and_terminal_note_inside_bar():
    positions=[F(i,12) for i in range(48)]
    song=song_at(positions,step=F(1,12))
    for n in song.arrangements[0].notes:
        n.time=round(n.time,3)
    assert [a[0] for a in attacks(export(song))] == positions


def test_adaptive_split_harmonic_and_bar_mappings_keep_exact_addresses():
    import base64
    song=song_at([F(0),F(5,32),F(10,32)])
    for n in song.arrangements[0].notes:
        n.harmonic=True;n.harmonic_node=3.2;n.harmonic_pitch=28;n.ghost=True
    bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    gp=guitarpro.parse(BytesIO(base64.b64decode(bundle['gp5'])))
    assert [a[0] for a in attacks(gp)] == [0,F(5,32),F(10,32)]
    for entry in bundle['harmonics']:
        note=next(n for n in gp.tracks[0].measures[entry['bar']].voices[0].beats[entry['beat']].notes
                  if n.string==entry['gpString'])
        assert note.value==entry['fret'] and note.effect.ghostNote


def test_split_duration_does_not_extend_an_ended_note():
    song=song_at([F(0),F(5,32),F(10,32)])
    song.arrangements[0].notes[0].sustain=float(F(4,32))*.5
    gp=export(song)
    first=gp.tracks[0].measures[0].voices[0].beats
    assert first[0].notes[0].value==7
    assert first[1].status==guitarpro.BeatStatus.rest
    assert first[2].notes[0].value==9


def test_display_limit_is_reported_by_route_without_generic_server_failure(tmp_path,monkeypatch):
    import sys
    import routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    file=tmp_path/'dense.feedpak';file.write_bytes(b'route fixture')
    loaded=Obj(song=song_at([F(0),F(1,1000)]),manifest={})
    monkeypatch.setitem(sys.modules,'sloppak',Obj(load_song=lambda *args:loaded))
    app=FastAPI();routes.setup(app,{'get_dlc_dir':lambda:tmp_path,'get_sloppak_cache_dir':lambda:tmp_path/'cache'})
    response=TestClient(app).get('/api/plugins/tabview/gp5/dense.feedpak')
    assert response.status_code==422
    assert 'Measure 1' in response.text and 'highway retains every note' in response.text
