"""Picking instructions in display rhythm; never generate picked attacks."""
from bisect import bisect_right, bisect_left
from copy import deepcopy
from fractions import Fraction


def display_events(events, measures):
    events=deepcopy(events)
    def members(event):
        return event.get('chord_notes',[]) if event['type']=='chord' else [] if event['type']=='boundary' else [event]
    roots=[]
    existing={}
    times={e['time'] for e in events}
    times.update(m['start_time'] for m in measures)
    for event in events:
        for note in members(event):
            existing.setdefault((round(event['time'],6),note['string']),[]).append(note)
            if note.get('tremolo') and not note.get('display_tie'):
                onset=note.get('performed_time',event['time'])
                end=onset+note.get('sustain',0)
                if end<=onset:continue
                roots.append((event,note,onset,end))
                times.add(end)
                for m in note.get('tremolo_marks') or []:
                    times.update((onset+m['start'],onset+m['end']))
    times=sorted(times)
    added=[]
    for event,note,onset,end in roots:
        note['picking_chain']=True
        note['picking_offset']=max(0,event['time']-onset)
        for t in times[bisect_right(times,event['time']+1e-7):bisect_left(times,end-1e-7)]:
            found=existing.get((round(t,6),note['string']),[])
            if found:
                # A real reattack owns its string. Harmonic display ties keep
                # their own contact information and receive only picking context.
                if any(not current.get('display_tie') for current in found):break
                for current in found:
                    if current.get('display_tie'):
                        current.update(picking_chain=True,picking_offset=t-onset,
                                       tremolo_marks=deepcopy(note.get('tremolo_marks')),tremolo=True,
                                       performed_time=onset,sustain=note['sustain'])
                continue
            continuation=deepcopy(note)
            continuation.update(type='note',time=t,performed_time=onset,sustain=note['sustain'],
                                display_tie=True,picking_offset=t-onset,
                                hammer_on=False,pull_off=False,tap=False,accent=False,slide_to=-1,bend=0)
            contact=continuation.get('contact_source')
            if contact and t>=contact['onset']+contact['event']['start']:
                continuation['harmonic_target']=deepcopy(contact['event']['target'])
            continuation.pop('authored_strum',None)
            added.append(continuation)
        added.append({'time':end,'type':'boundary'})
    return sorted(events+added,key=lambda e:e['time'])


def instruction(note):
    """(active, GP duration or None). None never asserts a rhythmic speed."""
    if not note.get('tremolo'):return False,None
    marks=note.get('tremolo_marks')
    if marks is None:return True,None
    offset=note.get('picking_offset',0)
    m=next((m for m in marks if m['start']-1e-7<=offset<m['end']-1e-7),None)
    if m is None:return False,None
    if m['mode']=='specified':
        rate=Fraction(*m['rate'])
        if rate.numerator==1 and rate.denominator in (8,16,32):return True,rate.denominator
    return True,None
