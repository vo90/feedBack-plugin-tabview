import base64
import hashlib
import io
from types import SimpleNamespace as Obj
import guitarpro
import rs2gp
from copy import deepcopy


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


def fallback_song():
    song=harmonic_song()
    song.arrangements[0].notes[1].harmonic_target={
        'kind':'artificial','node':None,'interval':24,'policy':'harmonic',
        'basis':'source-playback-fallback'}
    song.arrangements[0].notes[1].palm_mute=True
    return song


def test_playback_pitch_and_unknown_contact_survive_tab_bundle_without_extra_notes():
    song=fallback_song()
    before=deepcopy(song)
    bundle=rs2gp.arrangement_to_gp5(song,include_harmonics=True)
    target=song.arrangements[0].notes[1].harmonic_target
    entries=[e for e in bundle['harmonics'] if e['target']==target]
    assert len(entries)==1
    e=entries[0]
    gp=guitarpro.parse(io.BytesIO(base64.b64decode(bundle['gp5'])))
    n=next(n for n in gp.tracks[0].measures[e['bar']].voices[e['voice']].beats[e['beat']].notes
           if n.string==e['gpString'])
    assert n.value==12 and n.effect.palmMute
    assert n.effect.harmonic is None
    assert len(bundle['harmonics'])==6
    assert song==before
    e['target']['node']=5
    assert song.arrangements[0].notes[1].harmonic_target['node'] is None
