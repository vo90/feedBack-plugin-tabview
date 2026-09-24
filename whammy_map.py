"""Map exact chart expression onto the existing, quantized GP display beats.

The GP bridge is a display export. Keep exact source timing in the bundle;
never round the chart or pretend that GP5 supplies the source coordinates.
"""
from bisect import bisect_right
from copy import deepcopy


def pitch(curve, t):
    if not curve:
        return 0.
    if t <= curve[0]['t']:
        return curve[0]['v']
    for a, b in zip(curve, curve[1:]):
        if t <= b['t']:
            return a['v']+(b['v']-a['v'])*(t-a['t'])/(b['t']-a['t'])
    return curve[-1]['v']


def build_mapping(track, measures, notes):
    # These identities were recorded while constructing the GP model. They
    # refer to its exact addresses, not a later nearest-note search.
    entries=[]
    for bi, bar in enumerate(track.measures):
        for vi, voice in enumerate(bar.voices):
            for ei, beat in enumerate(voice.beats):
                for note in beat.notes:
                    value=notes.get(id(note))
                    if value:
                        entries.append(dict(track=0,staff=0,bar=bi,voice=vi,beat=ei,
                            string=len(track.strings)+1-note.string,fret=note.value,**deepcopy(value)))
    beats=[];limitations=[]
    for bi, (bar, info) in enumerate(zip(track.measures,measures)):
        times=info['beat_times']+[info['end_time']]
        def at(q):
            i=min(len(times)-2,max(0,int(q)))
            return times[i]+(q-i)*(times[i+1]-times[i])
        def quarter(t):
            i=min(len(times)-2,max(0,bisect_right(times,t)-1))
            return i+(t-times[i])/(times[i+1]-times[i])
        q=0.
        for ei, beat in enumerate(bar.voices[0].beats):
            length=beat.duration.time/960
            left,right=at(q),at(q+length)
            groups={}
            for entry in entries:
                for segment in entry['expression']['segments']:
                    start=entry['time']+segment['start'];end=entry['time']+segment['end']
                    if start >= right-1e-8 or end <= left+1e-8:continue
                    # Scope includes only recorded owning notes, even when a
                    # long tie spans display beats without another attack.
                    record=groups.setdefault(segment['group'],{'members':[], 'segments':[]})
                    record['members'].append(entry['sourceId'])
                    record['segments'].append((entry,segment,start,end))
            if groups:
                address=dict(track=0,staff=0,bar=bi,voice=0,beat=ei)
                shapes=[];vibratos=set();members=[];partial_vibrato=False
                for group in groups.values():
                    members.extend(group['members'])
                    for entry,segment,start,end in group['segments']:
                        a=max(start,left);b=min(end,right)
                        if segment.get('vibrato'):
                            vibratos.add(segment['vibrato'])
                            partial_vibrato |= a > left+1e-8 or b < right-1e-8
                        if not segment['curve']:continue
                        knots=sorted({a,b,*[entry['time']+p['t'] for p in segment['curve'] if a<entry['time']+p['t']<b],
                                      *[t for t in times if a<t<b]})
                        points=[{'position':(quarter(t)-q)/length*60,
                                 'semitones':pitch(segment['curve'],t-entry['time'])} for t in knots]
                        shapes.append(points)
                unique=[]
                for shape in shapes:
                    if shape not in unique:unique.append(shape)
                # AlphaTab's bar curve is beat-wide. Different simultaneous
                # instructions must not overwrite each other in that field.
                limitation=None
                if len(unique)>1 or len(vibratos)>1:
                    limitation='Multiple bar gestures share this GP display beat; exact gestures are retained in the source mapping.'
                elif partial_vibrato or (unique and (abs(unique[0][0]['position'])>1e-6 or abs(unique[0][-1]['position']-60)>1e-6)):
                    limitation='The bar gesture occupies part of this GP display beat; exact timing is retained in the source mapping.'
                if limitation:
                    limitations.append(dict(**address,reason=limitation,members=sorted(set(members))))
                beats.append(dict(**address,points=unique[0] if len(unique)==1 and not limitation else [],
                    vibrato=next(iter(vibratos)) if len(vibratos)==1 and not limitation else None,
                    members=sorted(set(members)),sourceStart=left,sourceEnd=right,limitation=limitation))
            q+=length
    return {'version':1,'notes':entries,'beats':beats,'limitations':limitations}
