"""Delayed contacts in the GP display bridge, separate from playable attacks."""
from copy import deepcopy


def display_events(events, measures):
    result=deepcopy(events)
    added=[]
    for event in result:
        notes=event.get('chord_notes',[]) if event['type']=='chord' else [event]
        for note in notes:
            changes=note.get('harmonic_changes')
            if not changes: continue
            if changes.get('version')!=1 or len(changes.get('events',[]))!=1:
                raise ValueError('Unsupported delayed harmonic contact')
            contact=changes['events'][0]
            start=event['time'];at=start+contact['start'];end=start+contact['end']
            if not start<at<end:raise ValueError('Invalid delayed harmonic interval')
            note['contact_chain']=True
            note['contact_source']={'onset':start,'heldFret':note['fret'],'gameString':note['string'],
                                    'event':deepcopy(contact)}
            times=sorted({at,*[m['start_time'] for m in measures if start<m['start_time']<end]})
            for t in times:
                continuation=deepcopy(note)
                continuation.update(time=t,type='note',display_tie=True,source_id=contact['source_id'])
                if t>=at:continuation['harmonic_target']=deepcopy(contact['target'])
                added.append(continuation)
            added.append({'time':end,'type':'boundary'})
    return sorted(result+added,key=lambda e:e['time'])


def build_mapping(track, notes):
    entries=[]
    for bi,bar in enumerate(track.measures):
        for vi,voice in enumerate(bar.voices):
            for ei,beat in enumerate(voice.beats):
                for note in beat.notes:
                    value=notes.get(id(note))
                    if value:
                        entries.append(dict(track=0,staff=0,bar=bi,voice=vi,beat=ei,
                            string=len(track.strings)+1-note.string,fret=note.value,**deepcopy(value)))
    return {'version':1,'notes':entries,'limitations':[
        'This tab view uses quantized display rhythm. Exact harmonic contact timing is retained in the song.'
    ] if entries else []}
