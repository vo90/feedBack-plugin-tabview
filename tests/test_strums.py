from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace as Obj
import hashlib
import json
import guitarpro
import pytest
import strums
import rs2gp
from test_adaptive_rhythm import song_at


def fixture(direction='down'):
    strings=list(range(6)) if direction=='down' else list(reversed(range(6)))
    song=song_at([i/96 for i in range(6)],strings=strings)
    group={'trackId':'0','sourceId':'songsterr:0:0:0:0','time':0.,'direction':direction,
           'notes':[{'t':n.time,'s':n.string,'f':n.fret} for n in song.arrangements[0].notes]}
    return song,[group]


@pytest.mark.parametrize('direction',['up','down'])
def test_gp5_roundtrip_has_chord_direction_all_frets_and_unchanged_gameplay(direction):
    song,groups=fixture(direction);before=deepcopy(song)
    data=rs2gp.arrangement_to_gp5(song,strum_context=groups)
    gp=guitarpro.parse(BytesIO(data));beat=gp.tracks[0].measures[0].voices[0].beats[0]
    assert len(beat.notes)==6
    assert beat.effect.stroke.direction==getattr(guitarpro.BeatStrokeDirection,direction)
    assert {(6-n.string,n.value) for n in beat.notes}=={(n.string,n.fret) for n in song.arrangements[0].notes}
    assert song==before


@pytest.mark.parametrize('fault',['none','missing','fret','time','ambiguous','same-string'])
def test_nearby_notes_are_not_guessed_or_partially_grouped(fault):
    song,groups=fixture();events=rs2gp._merge_events(song.arrangements[0])
    if fault=='none':groups=None
    if fault=='missing':events.pop()
    if fault=='fret':groups[0]['notes'][0]['f']=99
    if fault=='time':groups[0]['notes'][0]['t']+=.002
    if fault=='ambiguous':events.append(deepcopy(events[0]))
    if fault=='same-string':
        extra=deepcopy(events[1]);extra['time']=0;events.append(extra)
    original=deepcopy(events)
    actual=strums.display_events(events,groups)
    assert actual==sorted(original,key=lambda e:e['time']) and events==original


def test_effects_and_absolute_sounding_end_are_retained():
    song,groups=fixture();events=rs2gp._merge_events(song.arrangements[0])
    events[1]['mute']=True;events[2]['ghost']=True
    actual=strums.display_events(events,groups)[0]
    assert actual['chord_notes'][1]['mute'] and actual['chord_notes'][2]['ghost']
    assert all(n['performed_time']+n['sustain']==events[i]['time']+events[i]['sustain'] for i,n in enumerate(actual['chord_notes']))


def test_source_hash_track_and_direction_bind_receipt_even_without_notation(tmp_path):
    song,groups=fixture();source={'tracks':[{'id':0}],'parts':[{'measures':[{'voices':[{'beats':[{'brushStroke':{'direction':'down'}}]}]}]}]}
    raw=json.dumps(source).encode();(tmp_path/'source.json').write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
    receipt={'version':1,'timeDomain':'recording_seconds','sourceSha256':digest,'groups':groups}
    (tmp_path/'strums.json').write_text(json.dumps(receipt),encoding='utf-8')
    loaded=Obj(source_dir=tmp_path,arrangement_ids=['0'],manifest={'song_import':{'source':'songsterr','sourceFile':'source.json','scoreHash':digest,'strumsFile':'strums.json'}})
    assert strums.load_context(loaded,0)==groups
    groups[0]['direction']='up';(tmp_path/'strums.json').write_text(json.dumps(receipt),encoding='utf-8')
    with pytest.raises(ValueError,match='direction'):strums.load_context(loaded,0)
    (tmp_path/'source.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='source'):strums.load_context(loaded,0)


def test_repeated_occurrences_remain_separate_groups():
    song,groups=fixture();events=rs2gp._merge_events(song.arrangements[0]);later=deepcopy(events)
    for e in later:e['time']+=2
    other=deepcopy(groups[0]);other['time']+=2
    for n in other['notes']:n['t']+=2
    actual=strums.display_events(events+later,groups+[other])
    assert [e['time'] for e in actual]==[0,2] and all(len(e['chord_notes'])==6 for e in actual)
