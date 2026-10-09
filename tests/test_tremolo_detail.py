from copy import deepcopy
from io import BytesIO
import guitarpro
import pytest
import rs2gp
from test_adaptive_rhythm import song_at, attacks


def mark(rate,start=0,end=2):
    return dict(start=start,end=end,rate=rate,period=.125 if rate else None,
                phase=0,mode='specified' if rate else 'unspecified')


def export(song):return guitarpro.parse(BytesIO(rs2gp.arrangement_to_gp5(song)))


@pytest.mark.parametrize('rate', [8,16,32])
def test_written_rate_survives_serialization_without_extra_attacks(rate):
    song=song_at([0]);n=song.arrangements[0].notes[0]
    before=attacks(export(song));n.tremolo=True;n.tremolo_marks=[mark([1,rate])]
    original=deepcopy(song);gp=export(song)
    assert attacks(gp)==before and song==original
    notes=[n for b in gp.tracks[0].measures[0].voices[0].beats for n in b.notes]
    assert notes and all(n.effect.tremoloPicking.duration.value==rate for n in notes)


@pytest.mark.parametrize('marks',[None,[mark(None)],[mark([1,64])]])
def test_generic_does_not_invent_eighths_or_speed_label(marks):
    song=song_at([0]);n=song.arrangements[0].notes[0];n.tremolo=True;n.tremolo_marks=marks
    gp=export(song);beats=gp.tracks[0].measures[0].voices[0].beats
    assert all(n.effect.tremoloPicking is None for b in beats for n in b.notes)
    assert any(b.text=='trem.' for b in beats)


def test_delayed_instruction_uses_tie_not_new_picked_attack():
    song=song_at([0]);n=song.arrangements[0].notes[0];n.tremolo=True;n.tremolo_marks=[mark([1,16],1,2)]
    gp=export(song);beats=gp.tracks[0].measures[0].voices[0].beats
    assert len(attacks(gp))==1
    assert beats[0].notes[0].effect.tremoloPicking is None
    assert beats[1].notes[0].type==guitarpro.NoteType.tie
    assert beats[1].notes[0].effect.tremoloPicking.duration.value==16


def test_mark_end_and_intervening_other_string_keep_ties():
    song=song_at([0,1,3],step=1,strings=[0,1,2]);n=song.arrangements[0].notes[0]
    n.sustain=2;n.tremolo=True;n.tremolo_marks=[mark([1,32],0,1)]
    gp=export(song);beats=gp.tracks[0].measures[0].voices[0].beats
    held=[(b.start,n) for b in beats for n in b.notes if n.string==6]
    assert sum(n.type!=guitarpro.NoteType.tie for _,n in held)==1
    assert len(held)>=3
    assert held[-1][1].effect.tremoloPicking is None


def test_empty_detail_has_no_picking_instruction():
    song=song_at([0]);n=song.arrangements[0].notes[0];n.tremolo=True;n.tremolo_marks=[]
    gp=export(song)
    assert all(n.effect.tremoloPicking is None for b in gp.tracks[0].measures[0].voices[0].beats for n in b.notes)
