"""Retained pickup clocks for display export; never change gameplay beats."""
from copy import deepcopy
import hashlib
import json
import math
from types import SimpleNamespace

from strums import _read


def load_context(loaded):
    recipe = loaded.manifest.get('song_import', {})
    name = recipe.get('pickupTimelineFile')
    if not name:
        return None
    data = json.loads(_read(loaded, name))
    digest = hashlib.sha256(_read(loaded, recipe.get('sourceFile'))).hexdigest()
    if (data.get('version') != 1 or data.get('timeDomain') != 'recording_seconds'
            or digest != recipe.get('scoreHash') or data.get('sourceSha256') != digest):
        raise ValueError('Pickup clock does not match retained source')
    validate(data.get('measures'))
    return data['measures']


def validate(rows):
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError('Invalid pickup clock')
    previous = -math.inf
    for row in rows:
        signature, quarters, anchors = row.get('signature'), row.get('quarters'), row.get('anchors')
        if (not isinstance(signature, list) or len(signature) != 2
                or any(type(n) is not int or n <= 0 for n in signature)
                or signature[1] not in (1,2,4,8,16,32)
                or type(quarters) not in (float,int) or not math.isfinite(quarters)
                or not 0 < quarters < 4*signature[0]/signature[1]
                or not isinstance(anchors,list) or not 2 <= len(anchors) <= 10000):
            raise ValueError('Invalid pickup extent')
        for a in anchors:
            if not isinstance(a,dict) or any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) for k in ('time','quarter')):
                raise ValueError('Invalid pickup anchor')
        if (abs(anchors[0]['quarter']) > 1e-8 or abs(anchors[-1]['quarter']-quarters) > 1e-8
                or anchors[0]['time'] < previous
                or any(b['time'] <= a['time'] or b['quarter'] <= a['quarter'] for a,b in zip(anchors,anchors[1:]))):
            raise ValueError('Non-monotonic pickup clock')
        previous = anchors[-1]['time']


def boundaries(beats, rows):
    if not rows:
        return beats
    validate(rows)
    result = list(beats)
    for row in rows:
        left, right = row['anchors'][0]['time'], row['anchors'][-1]['time']
        # Synthetic boundaries are local to GP5 display, never the game's
        # metronome/scoring beat grid. Short pickups may have no actual tick.
        result = [b for b in result if not left-1e-6 <= b.time < right-1e-6]
        result.append(SimpleNamespace(time=left, measure=0))
        if not any(abs(b.time-right) <= 1e-6 and b.measure >= 0 for b in result):
            result.append(SimpleNamespace(time=right, measure=0))
    return sorted(result, key=lambda b:b.time)


def measures(parsed, rows):
    if not rows:
        return parsed
    result = deepcopy(parsed)
    for row in rows:
        match = [m for m in result if abs(m['start_time']-row['anchors'][0]['time']) < 1e-6]
        if len(match) != 1 or abs(match[0]['end_time']-row['anchors'][-1]['time']) > 1e-6:
            raise ValueError('Pickup clock does not match display boundaries')
        m = match[0]
        m.update(num_beats=row['quarters'], quarter_anchors=row['anchors'], signature=row['signature'], pickup=True,
                 bpm=60*row['quarters']/(m['end_time']-m['start_time']))
    return result


def cursor_clock(measures):
    result, tick = [], 0
    for m in measures:
        anchors = m.get('quarter_anchors') or [dict(time=t,quarter=i) for i,t in enumerate(m['beat_times'])]
        for a in anchors:
            row = dict(time=a['time'], tick=round(tick+a['quarter']*960))
            if result and abs(result[-1]['time']-row['time']) < 1e-6:
                if result[-1]['tick'] != row['tick']: raise ValueError('Conflicting display clock boundary')
            else: result.append(row)
        tick += m['num_beats']*960
    last = dict(time=measures[-1]['end_time'], tick=round(tick))
    if last['time'] > result[-1]['time']: result.append(last)
    return result
