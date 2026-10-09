"""Display-only beat boundaries for authored wah cues, including held notes."""
from bisect import bisect_left, bisect_right
from copy import deepcopy


def display_events(events, cues, measures):
    if not cues: return events
    result = deepcopy(events)
    anchors = sorted({e['time'] for e in events} | {m['start_time'] for m in measures})
    def boundary(t):
        i = bisect_left(anchors, t)
        near = anchors[max(0, i-1):i+1]
        n = min(near, key=lambda a:abs(a-t)) if near else t
        return n if abs(n-t) <= 1.1e-6 else round(t, 6)
    groups = {}
    for cue in cues:
        groups.setdefault(boundary(cue['t']), set()).add(cue['state'])
    result.extend({'time':t, 'type':'boundary', 'wah':sorted(states)} for t,states in groups.items())
    def members(e):
        return e.get('chord_notes', []) if e['type']=='chord' else [] if e['type']=='boundary' else [e]
    existing = {}
    for e in result:
        for n in members(e): existing.setdefault((round(e['time'],6), n['string']), []).append(n)
    roots = [(e,n) for e in result for n in members(e) if not n.get('display_tie') and not n.get('mute') and n.get('sustain',0)>0]
    times = sorted({e['time'] for e in result} | set(anchors) |
                   {boundary(n.get('performed_time',e['time'])+n['sustain']) for e,n in roots})
    for event,note in roots:
        onset = note.get('performed_time', event['time'])
        end = boundary(onset + note['sustain'])
        note['display_chain'] = True
        for t in times[bisect_right(times,event['time']+1e-7):bisect_left(times,end-1e-7)]:
            found = existing.get((round(t,6), note['string']), [])
            if any(not n.get('display_tie') for n in found): break
            if found:
                for n in found: n['display_chain'] = True
                continue
            continuation = deepcopy(note)
            continuation.update(type='note',time=t,performed_time=onset,display_tie=True,
                                hammer_on=False,pull_off=False,tap=False,accent=False,slide_to=-1,bend=0)
            continuation.pop('authored_strum',None)
            if continuation.get('tremolo'): continuation['picking_offset']=t-onset
            contact=continuation.get('contact_source')
            if contact and t>=contact['onset']+contact['event']['start']:
                continuation['harmonic_target']=deepcopy(contact['event']['target'])
            result.append(continuation)
        result.append({'time':end,'type':'boundary'})
    return sorted(result,key=lambda e:e['time'])
