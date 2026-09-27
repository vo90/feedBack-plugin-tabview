from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
import strums
from hybrid_sources import includes, load_lineage


def fixture(tmp_path):
    def write(name, value):
        data = json.dumps(value, separators=(',', ':')).encode()
        (tmp_path / name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    source = {'tracks': [{'id': 0}, {'id': 1}], 'parts': [
        {'measures': [{'voices': [{'beats': [{'notes': []}]}]}]},
        {'measures': [{'voices': [{'beats': [{'brushStroke': {'direction': 'down'}}]}]}]},
    ]}
    digest = write('source.json', source)
    base = {'name': 'Lead', 'tuning': [0]*6, 'capo': 0, 'notes': [{'t': 0, 's': 0, 'f': 3, 'sus': 1}], 'chords': [], 'templates': []}
    donor = {**deepcopy(base), 'name': 'Clean', 'notes': [{'t': 2, 's': 0, 'f': 5, 'sus': 1}, {'t': 2.03, 's': 1, 'f': 7, 'sus': .97}]}
    derived = {**deepcopy(base), 'name': 'Hybrid Lead', 'notes': base['notes'] + donor['notes']}
    hashes = {key: write(key+'.json', value) for key, value in [('main', base), ('donor', donor), ('hybrid', derived)]}
    options = {'enabled': True, 'mainTrackId': '0', 'sourceSha256': digest}
    passage = {'trackId': '1', 'recordingStart': 2, 'recordingEnd': 3, 'events': [
        {'kind': 'notes', 'index': i, 'sourceIds': [f'songsterr:1:0:0:0:{i}'], 'occurrences': [1]} for i in range(2)]}
    receipt = {'version': 1, 'policy': 'hybrid-lead-v1', 'arrangementId': 'hybrid', 'sourceSha256': digest,
        'audioSha256': 'audio', 'options': options, 'mainTrackId': '0', 'passages': [passage], 'chartSha256': hashes['hybrid'],
        'sources': [{'trackId': tid, 'arrangementId': tid, 'file': key+'.json', 'chartSha256': hashes[key]} for tid, key in [('0','main'),('1','donor')]]}
    (tmp_path / 'import').mkdir()
    write('import/hybrid-lead.json', receipt)
    group = {'trackId': '1', 'sourceId': 'songsterr:1:0:0:0', 'occurrence': 1, 'time': 2, 'direction': 'down',
        'notes': [{k: n[k] for k in ('t', 's', 'f')} for n in donor['notes']]}
    unused = deepcopy(group);unused['time'] = 6
    for n in unused['notes']: n['t'] += 4
    write('strums.json', {'version': 1, 'timeDomain': 'recording_seconds', 'sourceSha256': digest, 'groups': [group, unused]})
    loaded = SimpleNamespace(source_dir=tmp_path, arrangement_ids=['0', '1', 'hybrid'], manifest={
        'arrangements': [{'id': tid, 'type': 'lead', 'file': key+'.json'} for tid, key in [('0','main'),('1','donor')]] +
            [{'id': 'hybrid', 'type': 'lead', 'file': 'hybrid.json', 'derived': {'kind': 'hybrid-lead-v1', 'receipt': 'import/hybrid-lead.json'}}],
        'song_import': {'source': 'songsterr', 'scoreHash': digest, 'audioHash': 'audio', 'sourceFile': 'source.json',
            'strumsFile': 'strums.json', 'hybridLeadFile': 'import/hybrid-lead.json', 'preservationContract': 32, 'hybridLead': options}})
    return loaded, receipt, group, write


def test_only_selected_source_strums_and_harmonic_occurrences_are_projected(tmp_path):
    loaded, receipt, group, _ = fixture(tmp_path)
    assert load_lineage(loaded, 2) == receipt
    assert strums.load_context(loaded, 2) == [group]
    assert includes(receipt, {'trackId': '0', 'sourceId': 'main', 'occurrence': 99})
    assert includes(receipt, {'trackId': '1', 'sourceId': 'songsterr:1:0:0:0:0', 'occurrence': 1})
    assert not includes(receipt, {'trackId': '1', 'sourceId': 'songsterr:1:0:0:0:0', 'occurrence': 2})


@pytest.mark.parametrize('fault', ['source', 'chart', 'rehashed_chart', 'donor', 'duplicate', 'tail', 'voice'])
def test_tampered_or_partial_projection_is_rejected(tmp_path, fault):
    loaded, receipt, group, write = fixture(tmp_path)
    if fault == 'source': write('source.json', {})
    if fault in ('chart', 'rehashed_chart'):
        chart = json.loads((tmp_path/'hybrid.json').read_text());chart['notes'][0]['f'] = 9
        changed = write('hybrid.json', chart)
        if fault == 'rehashed_chart': receipt['chartSha256'] = changed
    if fault == 'donor': write('donor.json', {})
    if fault == 'duplicate': receipt['passages'][0]['events'].append(receipt['passages'][0]['events'][0])
    if fault == 'tail': receipt['passages'][0]['recordingEnd'] = 2.5
    if fault == 'voice':
        group['sourceId'] = 'songsterr:0:0:0:0'
        write('strums.json', {'version': 1, 'timeDomain': 'recording_seconds', 'sourceSha256': receipt['sourceSha256'], 'groups': [group]})
    write('import/hybrid-lead.json', receipt)
    with pytest.raises(ValueError): strums.load_context(loaded, 2)
