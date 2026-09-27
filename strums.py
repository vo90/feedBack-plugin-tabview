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
    projection = None
    if recipe.get('voicesFile'):
        projection = json.loads(_read(loaded,recipe['voicesFile']))
        if (projection.get('version')!=1 or projection.get('policy')!='source-voices-v1'
                or projection.get('timeDomain')!='score_seconds'
                or projection.get('sourceSha256')!=digest):
            raise ValueError('Voice projection does not match the retained source')
    selected=[]
    from hybrid_sources import load_lineage, includes
    hybrid = load_lineage(loaded, index)
    for group in groups:
        if hybrid:
            if not includes(hybrid, group, recording_time=True): continue
        elif group['trackId'] != loaded.arrangement_ids[index]: continue
        match=BEAT_ID.fullmatch(group['sourceId'])
        if not match: raise ValueError('Invalid strum source identity')
        pi,mi,vi,bi=map(int,match.groups())
        original_id = str(source['tracks'][pi].get('id',pi))
        if projection is not None:
            matches=[(row,arr) for row in projection['tracks'] for arr in row['arrangements']
                     if arr['id']==group['trackId']]
            if matches:
                if len(matches)!=1:raise ValueError('Ambiguous voice arrangement identity')
                row,arr=matches[0]
                if row['mode'] not in ('split','combined'):raise ValueError('Invalid voice projection mode')
                expected_id=(('voice-'+hashlib.sha256(row['sourceTrackId'].encode()).hexdigest()[:20]+'-'+str(vi+1))
                             if row['mode']=='split' else row['sourceTrackId'])
                if (row['sourceTrackId']!=original_id or vi not in arr['voices']
                        or expected_id!=group['trackId']):
                    raise ValueError('Strum belongs to another source voice')
                original_id=group['trackId']
        if original_id != group['trackId']:
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
