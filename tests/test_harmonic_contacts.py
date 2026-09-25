from copy import deepcopy
import base64,io
import guitarpro
from test_whammy_map import bar_song
import rs2gp


def test_contact_export_has_one_attack_tied_continuations_and_exact_sidecar():
    song=bar_song();n=song.arrangements[0].notes[0];n.whammy=None;n.fret=14
    n.harmonic_changes={'version':1,'events':[{'start':2.5,'end':4,
        'target':{'kind':'artificial','node':7,'interval':19,'policy':'harmonic'},'source_id':'source:tie'}]}
    before=deepcopy(n.__dict__)
    bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    gp=guitarpro.parse(io.BytesIO(base64.b64decode(bundle['gp5'])))
    notes=[n for m in gp.tracks[0].measures for b in m.voices[0].beats for n in b.notes]
    assert sum(n.type==guitarpro.NoteType.normal for n in notes)==1
    assert sum(n.type==guitarpro.NoteType.tie for n in notes)>=2
    assert all(n.value==14 for n in notes)
    entries=bundle['harmonicContacts']['notes']
    assert entries and entries[0]['event']==n.harmonic_changes['events'][0]
    assert all(e['tie'] for e in entries[1:])
    assert any(b.text=='AH 21' for m in gp.tracks[0].measures for b in m.voices[0].beats)
    assert song.arrangements[0].notes[0].__dict__==before
