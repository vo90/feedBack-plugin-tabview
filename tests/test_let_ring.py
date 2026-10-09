import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import guitarpro
from rs2gp import _note_dict,_apply_effects
from lib.song import note_from_wire


def test_let_ring_is_an_effect_not_a_changed_written_duration():
    raw={'t':2,'s':0,'f':0,'sus':.455,'lr':True,'let_ring_sus':2.73}
    nd=_note_dict(note_from_wire(raw))
    note=guitarpro.Note(guitarpro.Beat(guitarpro.Voice(guitarpro.Measure(guitarpro.Track(guitarpro.Song()),guitarpro.MeasureHeader()))))
    _apply_effects(note,nd)
    assert note.effect.letRing
    assert nd['sustain']==.455
    nd.update(mute=True)
    _apply_effects(note,nd)
    assert not note.effect.letRing


def test_serialized_tab_marks_ring_without_adding_ties_or_changing_rhythm():
    from io import BytesIO
    from test_adaptive_rhythm import song_at, attacks
    from rs2gp import arrangement_to_gp5
    song=song_at([0,1,2,3],step=1,strings=[0,1,2,3])
    before=guitarpro.parse(BytesIO(arrangement_to_gp5(song)))
    for n in song.arrangements[0].notes:
        n.let_ring=True
        n.let_ring_sustain=2-n.time
    after=guitarpro.parse(BytesIO(arrangement_to_gp5(song)))
    assert attacks(before)==attacks(after)
    notes=[n for b in after.tracks[0].measures[0].voices[0].beats for n in b.notes]
    assert len(notes)==4 and all(n.effect.letRing for n in notes)
