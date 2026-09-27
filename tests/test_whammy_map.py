from copy import deepcopy
from types import SimpleNamespace as Obj
import rs2gp


def bar_song(sustain=4):
    expression={'version':1,'policy':'optional','segments':[{'start':0,'end':4,
        'source_id':'source:0','group':'source:0@0','curve':[{'t':0,'v':0},{'t':2,'v':-8},{'t':4,'v':0}]}]}
    n=Obj(time=0,string=0,fret=12,sustain=sustain,whammy=expression)
    arr=Obj(path_bass=False,name='Guitar',tuning=[0]*6,notes=[n],chords=[])
    return Obj(title='Bar fixture',artist='Synthetic',album='',song_length=4,arrangements=[arr],
        beats=[Obj(time=i*.5,measure=i//4 if i%4==0 else -1) for i in range(8)])


def test_exact_curve_spans_display_bars_without_new_attacks():
    song=bar_song();bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    m=bundle['whammy'];assert len(m['notes'])==1 and len(m['beats'])==2
    assert m['notes'][0]['expression']==song.arrangements[0].notes[0].whammy
    assert m['beats'][0]['points']==[{'position':0.,'semitones':0.},{'position':15.,'semitones':-2.},
        {'position':30.,'semitones':-4.},{'position':45.,'semitones':-6.},{'position':60.,'semitones':-8.}]
    assert m['beats'][1]['points'][-1]=={'position':60.,'semitones':0.}
    assert not m['limitations']
    m['notes'][0]['expression']['segments'][0]['curve'][0]['v']=9
    assert song.arrangements[0].notes[0].whammy['segments'][0]['curve'][0]['v']==0


def test_partial_display_beat_does_not_invent_release_or_hold():
    song=bar_song();e=song.arrangements[0].notes[0].whammy['segments'][0]
    e['end']=1;e['curve']=[{'t':0,'v':0},{'t':1,'v':-8}]
    m=rs2gp.arrangement_to_gp5(song,include_harmonics=True)['whammy']
    assert m['beats'][0]['points']==[] and len(m['limitations'])==1
    assert m['notes'][0]['expression']['segments'][0]==e


def test_qualitative_vibrato_is_not_an_exact_curve():
    song=bar_song();e=song.arrangements[0].notes[0].whammy['segments'][0]
    e['curve']=[];e['vibrato']='wide'
    m=rs2gp.arrangement_to_gp5(song,include_harmonics=True)['whammy']
    assert all(b['vibrato']=='wide' and b['points']==[] for b in m['beats'])


def test_ordinary_exports_remain_identical():
    import base64
    song=bar_song();song.arrangements[0].notes[0].whammy=None
    b=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    assert base64.b64decode(b['gp5'])==rs2gp.arrangement_to_gp5(song)
    assert b['whammy']['notes']==[] and b['whammy']['beats']==[]


def test_partial_vibrato_does_not_fill_the_display_beat():
    song=bar_song();e=song.arrangements[0].notes[0].whammy['segments'][0]
    e['curve']=[];e['vibrato']='slight';e['start']=.5;e['end']=1
    m=rs2gp.arrangement_to_gp5(song,include_harmonics=True)['whammy']
    assert m['beats'][0]['vibrato'] is None and m['beats'][0]['points']==[]
    assert len(m['limitations'])==1
    assert m['notes'][0]['expression']['segments'][0]==e


def test_adaptive_ties_keep_one_source_expression_at_distinct_addresses():
    import base64
    import guitarpro
    from io import BytesIO
    from fractions import Fraction as F
    from test_adaptive_rhythm import song_at
    song = song_at([F(0), F(5, 32), F(10, 32)])
    first = song.arrangements[0].notes[0]
    first.whammy = deepcopy(bar_song().arrangements[0].notes[0].whammy)
    original = deepcopy(song)
    bundle = rs2gp.arrangement_to_gp5(song, include_harmonics=True)
    entries = bundle['whammy']['notes']
    assert len(entries) > 1
    assert len({e['sourceId'] for e in entries}) == 1
    assert len({(e['bar'], e['voice'], e['beat'], e['string']) for e in entries}) == len(entries)
    gp = guitarpro.parse(BytesIO(base64.b64decode(bundle['gp5'])))
    types = []
    for entry in entries:
        note = next(n for n in gp.tracks[0].measures[entry['bar']].voices[entry['voice']].beats[entry['beat']].notes
                    if n.string == 7 - entry['string'])
        types.append(note.type)
        assert entry['expression'] == first.whammy
        assert entry['time'] == first.time and entry['sustain'] == first.sustain
    assert types[0] == guitarpro.NoteType.normal
    assert all(t == guitarpro.NoteType.tie for t in types[1:])
    assert song == original
