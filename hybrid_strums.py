"""Project complete authored strums through a verified Hybrid Lead selection.

This reads existing package evidence only. It never changes the arrangement,
selects new passages, or infers a chord from nearby attacks.
"""
from collections import Counter, defaultdict
from bisect import bisect_right
from copy import deepcopy
import hashlib
import json


def _key(note):
    return json.dumps(note, sort_keys=True, separators=(',', ':'), allow_nan=False)


def selected_sources(loaded, index, source_hash):
    from strums import _read
    ident = loaded.arrangement_ids[index]
    entries = loaded.manifest.get('arrangements', [])
    matches = [a for a in entries if a.get('id') == ident]
    if len(matches) != 1:
        raise ValueError('Ambiguous strum arrangement identity')
    target = matches[0]
    derived = target.get('derived', {})
    if derived.get('kind') != 'hybrid-lead-v3':
        return None
    recipe = loaded.manifest['song_import']
    if derived.get('receipt') != recipe.get('hybridLeadFile'):
        raise ValueError('Hybrid strum selection receipt differs')
    report = json.loads(_read(loaded, derived.get('receipt')))
    if (report.get('version') != 3 or report.get('policy') != 'hybrid-lead-v3'
            or report.get('arrangementId') != ident or report.get('sourceSha256') != source_hash):
        raise ValueError('Hybrid strum selection does not match the source')

    def chart(entry, digest):
        raw = _read(loaded, entry.get('file'))
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Hybrid strum chart hash differs')
        return json.loads(raw)

    hybrid = chart(target, report.get('chartSha256'))
    available = Counter(_key(n) for n in hybrid.get('notes', []))
    sources = {}
    for row in report.get('sources', []):
        track = row['trackId']
        originals = [a for a in entries if a.get('id') == row.get('arrangementId')]
        if (track in sources or len(originals) != 1 or originals[0].get('derived')
                or row['arrangementId'] != track or originals[0].get('file') != row.get('file')):
            raise ValueError('Invalid Hybrid strum source arrangement')
        original = chart(originals[0], row.get('chartSha256'))
        by_string = defaultdict(list)
        for i, note in enumerate(original.get('notes', [])):
            by_string[(note['s'], note['f'])].append((i, note))
        sources[track] = {'chart': original, 'notes': by_string, 'selected': {}}
    main = report.get('mainTrackId')
    if main not in sources or not isinstance(report.get('mainEvents'), list):
        raise ValueError('Missing Hybrid strum main selection')
    selections = [(main, report['mainEvents'], None)]
    selections.extend((p['trackId'], p['events'], p) for p in report.get('passages', []))
    seen = set()
    selected = []
    for track, refs, passage in selections:
        if track not in sources:
            raise ValueError('Unknown Hybrid strum selected source')
        original = sources[track]['chart']
        for ref in refs:
            kind, i = ref.get('kind'), ref.get('index')
            if (kind not in ('notes', 'chords') or type(i) is not int
                    or not 0 <= i < len(original.get(kind, [])) or (track, kind, i) in seen):
                raise ValueError('Invalid Hybrid strum event selection')
            seen.add((track, kind, i))
            selected.append((track, kind, i, ref, original[kind][i], passage))

    # Ringing is visual-only and may end at a guitar handover or a later
    # same-string attack. Reconstruct those limits from the selected source
    # events; keep every other field in the strict identity comparison.
    ringing = recipe.get('preservationContract', 0) >= 110
    attacks = defaultdict(set)
    for _, kind, _, _, event, _ in selected:
        for note in event['notes'] if kind == 'chords' else [event]:
            attacks[note['s']].add(note.get('t', event['t']))
    attacks = {s: sorted(times) for s, times in attacks.items()}
    for track, kind, i, ref, event, passage in selected:
        if kind != 'notes':
            continue
        note = deepcopy(event)
        if ringing and 'let_ring_sus' in note:
            t = note['t']
            edge = (passage['recordingEnd'] if passage is not None else
                    min((p['recordingStart'] for p in report.get('passages', [])
                         if p['recordingStart'] > t), default=loaded.manifest['duration']))
            times = attacks[note['s']]
            next_index = bisect_right(times, t + 1e-8)
            if next_index < len(times):
                edge = min(edge, times[next_index])
            span = min(note['let_ring_sus'], round(edge - t, 6))
            if span <= note.get('sus', 0) + 1.1e-6:
                del note['let_ring_sus']
            else:
                note['let_ring_sus'] = span
        key = _key(note)
        if not available[key]:
            raise ValueError('Selected Hybrid strum note is absent or changed')
        available[key] -= 1
        sources[track]['selected'][i] = ref
    if any(available.values()):
        raise ValueError('Hybrid notes are not fully described by the selection')
    return sources


def retains_group(group, source):
    from strums import TOLERANCE
    if source is None:
        return False
    for note in group.get('notes', []):
        candidates = [(i, n) for i, n in source['notes'].get((note['s'], note['f']), [])
                      if abs(n['t'] - note['t']) <= TOLERANCE]
        # Resolve against all original notes before looking at selection, so
        # an ambiguous original cannot become unambiguous by dropping a note.
        if len(candidates) != 1:
            return False
        ref = source['selected'].get(candidates[0][0])
        if ref is None:
            return False
        if (group.get('occurrence') not in ref.get('occurrences', [])
                or not any(s.startswith(group['sourceId'] + ':') for s in ref.get('sourceIds', []))):
            return False
    return bool(group.get('notes'))
