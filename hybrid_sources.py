"""Read verified Hybrid Lead copy lineage for source-aware display adapters.

Composition remains entirely in FeedForge. Consumers only select existing
source evidence, after checking the original and derived chart membership.
"""
from copy import deepcopy
import hashlib
import json


def load_lineage(loaded, index):
    recipe = loaded.manifest.get('song_import', {})
    ident = loaded.arrangement_ids[index]
    entries = loaded.manifest.get('arrangements', [])
    entry = next((a for a in entries if a.get('id') == ident), {})
    if not entry.get('derived'):
        return None
    policy = entry['derived'].get('kind')
    version = {'hybrid-lead-v1': 1, 'hybrid-lead-v2': 2, 'hybrid-lead-v3': 3}.get(policy)
    from strums import _read
    if (not version or entry['derived'] != {'kind': policy, 'receipt': 'import/hybrid-lead.json'}
            or recipe.get('hybridLeadFile') != 'import/hybrid-lead.json' or recipe.get('preservationContract', 0) < 31 + (version or 0)):
        raise ValueError('Unsupported derived arrangement identity')
    receipt = json.loads(_read(loaded, recipe['hybridLeadFile']))
    digest = hashlib.sha256(_read(loaded, recipe.get('sourceFile'))).hexdigest()
    if (receipt.get('version') != version or receipt.get('policy') != policy
            or receipt.get('arrangementId') != ident or receipt.get('sourceSha256') != digest
            or recipe.get('scoreHash') != digest or receipt.get('options') != recipe.get('hybridLead')
            or receipt.get('audioSha256') != recipe.get('audioHash')):
        raise ValueError('Hybrid Lead evidence does not match the source')
    raw = _read(loaded, entry.get('file'))
    if hashlib.sha256(raw).hexdigest() != receipt.get('chartSha256'):
        raise ValueError('Hybrid Lead chart differs from its receipt')
    charts = {}
    for row in receipt.get('sources', []):
        original = next((a for a in entries if a.get('id') == row.get('arrangementId')), None)
        if not original or original.get('derived') or original.get('file') != row.get('file') or original.get('type') not in ('guitar', 'lead', 'rhythm'):
            raise ValueError('Invalid Hybrid Lead source arrangement')
        data = _read(loaded, row['file'])
        if hashlib.sha256(data).hexdigest() != row.get('chartSha256') or row['trackId'] in charts:
            raise ValueError('Hybrid Lead source chart changed')
        charts[row['trackId']] = json.loads(data)
    main_id = receipt['mainTrackId']
    if main_id != recipe['hybridLead'].get('mainTrackId') or main_id not in charts:
        raise ValueError('Hybrid Lead main guitar changed')
    expected = deepcopy(charts[main_id])
    expected['name'] = 'Hybrid Lead'
    expected.pop('phrases', None)
    expected.pop('ext', None)
    if version >= 2:
        allowed_coverage = {'complete', 'limited'} if version == 3 else {'complete'}
        if recipe['hybridLead'].get('policy') != policy or receipt.get('coverage', {}).get('status') not in allowed_coverage:
            raise ValueError('Hybrid Lead lacks verified primary coverage')
        refs = receipt.get('mainEvents', [])
        if any(r.get('kind') not in ('notes','chords') or not r.get('sourceIds') or not r.get('occurrences') for r in refs):
            raise ValueError('Invalid Hybrid Lead main lineage')
        if len({(r['kind'],r['index']) for r in refs}) != len(refs):
            raise ValueError('Duplicate Hybrid Lead main event')
        for kind in ('notes', 'chords'):
            indices = {r['index'] for r in refs if r['kind'] == kind}
            if any(type(i) is not int or i < 0 or i >= len(expected[kind]) for i in indices):
                raise ValueError('Invalid Hybrid Lead main event')
            expected[kind] = [e for i,e in enumerate(expected[kind]) if i in indices]
    offsets, used = {main_id: 0}, set()
    previous = None
    for passage in receipt.get('passages', []):
        tid = passage['trackId']
        if tid not in charts or tid == main_id or passage['recordingEnd'] <= passage['recordingStart']:
            raise ValueError('Invalid Hybrid Lead passage')
        if previous and previous['recordingEnd'] > passage['recordingStart'] + 1.1e-6:
            raise ValueError('Overlapping Hybrid Lead passages')
        previous = passage
        donor = charts[tid]
        if donor['tuning'] != expected['tuning'] or donor.get('capo', 0) != expected.get('capo', 0):
            raise ValueError('Incompatible Hybrid Lead guitar')
        if tid not in offsets:
            offsets[tid] = len(expected['templates'])
            expected['templates'].extend(deepcopy(donor['templates']))
        for ref in passage['events']:
            key = (tid, ref['kind'], ref['index'])
            if key in used or ref['kind'] not in ('notes', 'chords') or type(ref['index']) is not int or ref['index'] < 0:
                raise ValueError('Invalid Hybrid Lead event reference')
            used.add(key)
            event = deepcopy(donor[ref['kind']][ref['index']])
            notes = [event] if ref['kind'] == 'notes' else [{'t': event['t'], **n} for n in event['notes']]
            if any(n['t'] < passage['recordingStart'] - 1.1e-6 or n['t'] + n.get('sus', 0) > passage['recordingEnd'] + 1.1e-6 for n in notes):
                raise ValueError('Hybrid Lead passage cuts a source event')
            if ref['kind'] == 'chords':
                event['id'] += offsets[tid]
            expected[ref['kind']].append(event)
    for kind in ('notes', 'chords'):
        expected[kind].sort(key=lambda e: e['t'])
    if version >= 2:
        used_templates = {c['id'] for c in expected['chords']}
        kept = [i for i,t in enumerate(expected['templates']) if i in used_templates or 127 not in t['frets']]
        ids = {old:new for new,old in enumerate(kept)}
        expected['templates'] = [expected['templates'][i] for i in kept]
        for chord in expected['chords']:
            chord['id'] = ids[chord['id']]
    actual = {k: v for k, v in json.loads(raw).items() if k not in ('phrases', 'ext')}
    if expected != actual:
        raise ValueError('Hybrid Lead does not copy its declared original events')
    return receipt


def includes(receipt, group, *, recording_time=False):
    if group.get('trackId') == receipt['mainTrackId']:
        if receipt.get('version') == 1:
            return True
        source_id = group.get('sourceId', '')
        return any(group.get('occurrence') in r['occurrences'] and any(
            sid == source_id or recording_time and sid.startswith(source_id + ':') for sid in r['sourceIds'])
            for r in receipt.get('mainEvents', []))
    for passage in receipt['passages']:
        if passage['trackId'] != group.get('trackId'):
            continue
        if recording_time:
            times = [n['t'] for n in group.get('notes', [])] or [group['time']]
            if min(times) >= passage['recordingStart'] - 1.1e-6 and max(times) < passage['recordingEnd'] + 1.1e-6:
                if receipt.get('version', 1) >= 3:
                    source_id = group.get('sourceId', '')
                    if not any(group.get('occurrence') in ref['occurrences'] and any(
                            sid == source_id or sid.startswith(source_id + ':') for sid in ref['sourceIds'])
                            for ref in passage['events']):
                        continue
                return True
        elif any(group.get('sourceId') in ref['sourceIds'] and group.get('occurrence') in ref['occurrences'] for ref in passage['events']):
            return True
    return False
