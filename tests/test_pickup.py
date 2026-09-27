from copy import deepcopy
from fractions import Fraction
from io import BytesIO
from types import SimpleNamespace as O
import base64
import hashlib
import json

import guitarpro
import pytest
import pickup
import rhythm
import rs2gp


def row(q=1.5, start=.2, end=.95):
    return dict(occurrence=0,signature=[4,4],quarters=q,
                anchors=[dict(time=start,quarter=0),dict(time=end,quarter=q)])


@pytest.mark.parametrize('q', [.25,.5,.75,1,1.5,2,2.5,3])
def test_serialized_pickup_keeps_every_attack_and_written_extent(q):
    p=row(q,end=.2+q*.5)
    times=[.2+i*.125 for i in range(round(q*4))]
    notes=[O(time=t,sustain=.125,string=0,fret=i%12) for i,t in enumerate(times)]
    end=p['anchors'][-1]['time']
    beats=[O(time=end+i*.5,measure=1 if i==0 else 2 if i==4 else -1) for i in range(5)]
    song=O(title='Pickup',artist='Test',album='',song_length=end+3,beats=beats,
           arrangements=[O(path_bass=False,name='Lead',tuning=[0]*6,notes=notes,chords=[])])
    before=deepcopy(song)
    bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True,pickup_context=[p])
    gp=guitarpro.parse(BytesIO(base64.b64decode(bundle['gp5'])))
    voice=gp.tracks[0].measures[0].voices[0]
    assert [n.value for b in voice.beats for n in b.notes]==[i%12 for i in range(len(times))]
    assert sum(Fraction(b.duration.time,960) for b in voice.beats)==q
    assert gp.measureHeaders[0].timeSignature.numerator==4
    assert bundle['rhythm']['pickups']==[dict(bar=0,quarters=q)]
    assert bundle['rhythm']['clock'][0]==dict(time=.2,tick=0)
    assert any(a==dict(time=end,tick=round(q*960)) for a in bundle['rhythm']['clock'])
    assert song==before


def test_empty_pickup_and_tempo_break_use_same_exact_clock():
    p=row();p['anchors'].insert(1,dict(time=.45,quarter=1))
    beats=[O(time=.95+i*.5,measure=0 if i%4==0 else -1) for i in range(5)]
    m=pickup.measures(rs2gp._parse_measures(pickup.boundaries(beats,[p])),[p])[0]
    assert rhythm.quarter(.45,m)[0]==1
    assert rhythm.seconds(1.25,m)==.7
    assert rhythm.quarter(.7,m)[0]==1.25
    grid,slots=rhythm.layout([],m)
    assert sum(d.time for d in rhythm.durations(round(m['num_beats']*grid),grid))==1440


def test_repeated_pickup_splits_adjacent_bar_and_maps_cursor():
    rows=[row(1,0,.5),dict(row(1,2.5,3),occurrence=2)]
    beats=[O(time=t,measure=1 if t in (.5,3) else -1) for t in (.5,1,1.5,2,3,3.5,4,4.5,5)]
    m=pickup.measures(rs2gp._parse_measures(pickup.boundaries(beats,rows)),rows)
    assert [a['start_time'] for a in m[:4]]==[0,.5,2.5,3]
    assert [i for i,a in enumerate(m) if a.get('pickup')]==[0,2]
    assert dict(time=3,tick=5760) in pickup.cursor_clock(m)


@pytest.mark.parametrize('mutate', [lambda r:r.update(quarters=4),lambda r:r['anchors'][1].update(time=0),
    lambda r:r['anchors'][0].update(quarter=.1),lambda r:r['anchors'][1].update(time=float('nan'))])
def test_malformed_clock_rejected(mutate):
    p=row();mutate(p)
    with pytest.raises(ValueError):pickup.validate([p])


def test_receipt_is_bound_to_retained_source(tmp_path):
    raw=b'{"format":"songsterr"}';(tmp_path/'source.json').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest()
    data=dict(version=1,timeDomain='recording_seconds',sourceSha256=digest,measures=[row()])
    (tmp_path/'pickup.json').write_text(json.dumps(data))
    loaded=O(source_dir=tmp_path,manifest=dict(song_import=dict(sourceFile='source.json',scoreHash=digest,pickupTimelineFile='pickup.json')))
    assert pickup.load_context(loaded)==[row()]
    (tmp_path/'source.json').write_bytes(b'changed')
    with pytest.raises(ValueError):pickup.load_context(loaded)
