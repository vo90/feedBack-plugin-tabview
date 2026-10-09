from copy import deepcopy
from io import BytesIO
import guitarpro
import rs2gp
from test_adaptive_rhythm import song_at, attacks


def export(song): return guitarpro.parse(BytesIO(rs2gp.arrangement_to_gp5(song)))


def test_cues_on_attacks_holds_and_rests_keep_attacks():
    song=song_at([0,3],step=1);song.arrangements[0].notes[0].sustain=2
    before=attacks(export(song))
    song.arrangements[0].wah=[dict(t=t,state=s) for t,s in [(0,'open'),(1,'closed'),(2,'open'),(3,'closed')]]
    original=deepcopy(song);gp=export(song)
    assert song==original and attacks(gp)==before
    beats=[b for m in gp.tracks[0].measures for b in m.voices[0].beats]
    cues=[b for b in beats if b.effect.mixTableChange and b.effect.mixTableChange.wah.display]
    assert [b.effect.mixTableChange.wah.value for b in cues]==[0,100,0,100]
    assert cues[1].notes[0].type==guitarpro.NoteType.tie
    assert cues[2].status==guitarpro.BeatStatus.rest


def test_chord_dedup_and_conflict_keep_explicit_instructions():
    song=song_at([0]);song.arrangements[0].wah=[dict(t=0,state=s) for s in ['open','open','closed']]
    gp=export(song);b=gp.tracks[0].measures[0].voices[0].beats[0]
    assert b.text=='WAH o/+'


def test_absence_keeps_export_identical():
    song=song_at([0,1]);before=rs2gp.arrangement_to_gp5(song)
    song.arrangements[0].wah=[]
    assert before==rs2gp.arrangement_to_gp5(song)
