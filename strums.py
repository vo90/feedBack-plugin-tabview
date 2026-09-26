"""Source-bound strum groups for the tab display; gameplay stays untouched."""
from copy import deepcopy
import hashlib
import json
import math
import re

TOLERANCE = 0.0000011
BEAT_ID = re.compile(r'^songsterr:(\d+):(\d+):(\d+):(\d+)$')


def _read(loaded, name):
    root = loaded.source_dir.resolve()
    if not isinstance(name,str): raise ValueError('Missing retained strum evidence')
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 80*1024*1024:
        raise ValueError('Invalid retained strum evidence path or size')
    return path.read_bytes()


def load_context(loaded, index):
    recipe = loaded.manifest.get('song_import', {})
    if recipe.get('source') != 'songsterr' or not recipe.get('strumsFile'):
        return None
    data = _read(loaded,recipe.get('sourceFile'))
    digest = hashlib.sha256(data).hexdigest()
    receipt = json.loads(_read(loaded,recipe['strumsFile']))
    if (digest != recipe.get('scoreHash') or receipt.get('sourceSha256') != digest
            or receipt.get('version') != 1 or receipt.get('timeDomain') != 'recording_seconds'):
        raise ValueError('Strum evidence does not match the retained source')
    source = json.loads(data)
    groups = receipt.get('groups')
    if not isinstance(groups,list) or len(groups)>100000: raise ValueError('Invalid strum groups')
    selected=[]
    for group in groups:
        if group['trackId'] != loaded.arrangement_ids[index]: continue
        match=BEAT_ID.fullmatch(group['sourceId'])
        if not match: raise ValueError('Invalid strum source identity')
        pi,mi,vi,bi=map(int,match.groups())
        if str(source['tracks'][pi].get('id',pi)) != group['trackId']:
            raise ValueError('Strum belongs to another source track')
        raw=source['parts'][pi]['measures'][mi]['voices'][vi]['beats'][bi]
        directions=[]
        for key in ('brushStroke','arpeggio'):
            if raw.get(key) is not None: directions.append(raw[key]['direction'])
        if not directions:
            for key,direction in [('upStroke','down'),('downStroke','up'),('upArpeggio','up'),('downArpeggio','down')]:
                if raw.get(key): directions.append(direction)
        if len(directions)!=1 or directions[0]!=group['direction'] or group['direction'] not in ('up','down'):
            raise ValueError('Strum direction differs from authored source')
        selected.append(group)
    return selected


def display_events(events, groups):
    if not groups: return events
    result=deepcopy(events)
    candidates={}
    for i,event in enumerate(result):
        if event['type']=='note' and not event.get('harmonic_changes'):
            candidates.setdefault((event['string'],event['fret']),[]).append(i)
    used=set();chords=[]
    for group in groups:
        notes=group.get('notes');time=group.get('time')
        if (group.get('direction') not in ('up','down') or type(time) not in (int,float)
                or not math.isfinite(time) or time<0 or not isinstance(notes,list)
                or not 2<=len(notes)<=8):
            raise ValueError('Invalid strum display group')
        if any(type(n.get('s')) is not int or type(n.get('f')) is not int
               or type(n.get('t')) not in (int,float) or not math.isfinite(n['t']) for n in notes):
            raise ValueError('Invalid strum member')
        if len({n['s'] for n in notes})!=len(notes): raise ValueError('Duplicate strum string')
        matched=[]
        for n in notes:
            choices=[i for i in candidates.get((n['s'],n['f']),[]) if i not in used
                     and abs(result[i]['time']-n['t'])<=TOLERANCE]
            if len(choices)!=1: break
            matched.append(choices[0])
        # Missing/ambiguous members (including declared high-fret omissions)
        # cannot turn a partial group into a different chord.
        if len(matched)!=len(notes): continue
        strings={n['s'] for n in notes}
        if any(i not in matched and abs(e['time']-time)<=TOLERANCE and
               any(n.get('string') in strings for n in (e.get('chord_notes',[]) if e['type']=='chord' else [e]))
               for i,e in enumerate(result)):
            continue
        members=[]
        for i in matched:
            n=deepcopy(result[i]);n['performed_time']=n['time'];members.append(n)
        chords.append({'time':time,'type':'chord','chord_notes':members,
                       'authored_strum':group['direction'],'strum_source_id':group['sourceId']})
        used.update(matched)
    return sorted([e for i,e in enumerate(result) if i not in used]+chords,key=lambda e:e['time'])
