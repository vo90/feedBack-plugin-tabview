import base64
import hashlib
import io
from types import SimpleNamespace as Obj
import guitarpro
import rs2gp


def harmonic_song():
    notes=[]
    for index,(kind,policy) in enumerate([('pinch','harmonic'),('artificial','harmonic'),
        ('tapped','harmonic'),('semi','mixed'),('feedback','attack_either')]):
        notes.append(Obj(time=index*.5,string=index,fret=12,sustain=.5,ghost=True,
            harmonic_pinch=kind in ('pinch','semi'),
            harmonic_target={'kind':kind,'node':7,'interval':19,'policy':policy}))
    notes.append(Obj(time=2.5,string=2,fret=15,sustain=.5,ghost=True,harmonic=True,
                    harmonic_node=14.7,harmonic_pitch=34,harmonic_alias='songsterr-natural-15'))
    arr=Obj(path_bass=False,name='Guitar',tuning=[0]*6,notes=notes,chords=[])
    return Obj(title='Harmonic mapping fixture',artist='Synthetic',album='',song_length=4,
               arrangements=[arr],beats=[Obj(time=i*.5,measure=i//4 if i%4==0 else -1) for i in range(8)])


def test_mapping_uses_generated_addresses_not_time_or_fret_guesses():
    song=harmonic_song();bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    data=base64.b64decode(bundle['gp5'])
    assert bundle['sha256']==hashlib.sha256(data).hexdigest()
    assert data==rs2gp.arrangement_to_gp5(song)
    gp=guitarpro.parse(io.BytesIO(data));assert len(bundle['harmonics'])==6
    for e in bundle['harmonics']:
        beat=gp.tracks[e['track']].measures[e['bar']].voices[e['voice']].beats[e['beat']]
        n=next(n for n in beat.notes if n.string==e['gpString'])
        assert e['string']==len(gp.tracks[0].strings)+1-e['gpString']
        assert n.value==e['fret'] and n.effect.ghostNote
        assert e['sourceId'].startswith('note:')
    alias=bundle['harmonics'][-1]
    assert (alias['fret'],alias['naturalNode'],alias['naturalPitch'])==(15,14.7,34)
