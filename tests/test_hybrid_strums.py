"""Hybrid display groups must come from complete selected source attacks."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace as Obj

import pytest
import strums


class Package:
    def __init__(self, root):
        self.root = root
        self.source = {'tracks': [{'id': 0}, {'id': 1}], 'parts': [
            {'measures': [{'voices': [{'beats': [{'brushStroke': {'direction': direction}}]}]}]}
            for direction in ('down', 'up')]}
        self.charts = {}
        self.groups = []
        self.refs = {}
        for track in ('0', '1'):
            notes = [{'t': int(track)*2+i/96, 's': i, 'f': 3+i, 'sus': .5-i/96}
                     for i in range(3)]
            notes[1]['ghost'] = True
            self.charts[track] = {'notes': notes, 'chords': []}
            source_id = f'songsterr:{track}:0:0:0'
            self.groups.append({'trackId': track, 'sourceId': source_id, 'occurrence': 1,
                'time': int(track)*2., 'direction': 'down' if track=='0' else 'up',
                'notes': [{k: n[k] for k in ('t', 's', 'f')} for n in notes]})
            self.refs[track] = [{'kind': 'notes', 'index': i,
                'sourceIds': [source_id+':'+str(i)], 'occurrences': [1]} for i in range(3)]
        self.charts['hybrid'] = {'notes': deepcopy(self.charts['0']['notes']+self.charts['1']['notes']), 'chords': []}
        self.report = {'version': 3, 'policy': 'hybrid-lead-v3', 'arrangementId': 'hybrid',
            'mainTrackId': '0', 'mainEvents': self.refs['0'],
            'passages': [{'trackId': '1', 'events': self.refs['1']}]}
        self.manifest = {'arrangements': [{'id': ident, 'file': ident+'.json'} for ident in self.charts],
            'song_import': {'source': 'songsterr', 'sourceFile': 'source.json', 'strumsFile': 'strums.json',
                            'hybridLeadFile': 'hybrid-report.json'}}
        self.manifest['arrangements'][-1]['derived'] = {'kind': 'hybrid-lead-v3', 'receipt': 'hybrid-report.json'}

    def write(self, name, value):
        raw = json.dumps(value, sort_keys=True).encode()
        (self.root/name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def save(self):
        digest = self.write('source.json', self.source)
        self.manifest['song_import']['scoreHash'] = digest
        self.report['sourceSha256'] = digest
        self.report['sources'] = [{'trackId': track, 'arrangementId': track, 'file': track+'.json',
            'chartSha256': self.write(track+'.json', chart)} for track, chart in self.charts.items() if track!='hybrid']
        self.report['chartSha256'] = self.write('hybrid.json', self.charts['hybrid'])
        self.write('hybrid-report.json', self.report)
        self.write('strums.json', {'version': 1, 'timeDomain': 'recording_seconds',
            'sourceSha256': digest, 'groups': self.groups})
        return Obj(source_dir=self.root, arrangement_ids=[a['id'] for a in self.manifest['arrangements']], manifest=self.manifest)

    def load(self):
        return strums.load_context(self.save(), 2)


def events(notes):
    return [dict(type='note', time=n['t'], string=n['s'], fret=n['f'], sustain=n['sus'],
                 ghost=n.get('ghost',False)) for n in notes]


def test_main_and_donor_strums_retain_every_note_effect_and_performed_time(tmp_path):
    package = Package(tmp_path)
    groups = package.load()
    before = events(package.charts['hybrid']['notes'])
    unchanged = deepcopy(before)
    shown = strums.display_events(before, groups)
    assert [e['authored_strum'] for e in shown] == ['down', 'up']
    restored = []
    for chord in shown:
        for note in chord['chord_notes']:
            note = deepcopy(note)
            assert note.pop('performed_time') == note['time']
            restored.append(note)
    assert restored == before == unchanged


def test_partial_selection_keeps_the_remaining_attacks_separate(tmp_path):
    package = Package(tmp_path)
    package.report['mainEvents'].pop()
    package.charts['hybrid']['notes'].pop(2)
    groups = package.load()
    assert [g['trackId'] for g in groups] == ['1']
    shown = strums.display_events(events(package.charts['hybrid']['notes']), groups)
    assert [e['type'] for e in shown] == ['note', 'note', 'chord']


def test_identical_unselected_source_cannot_supply_the_strum_direction(tmp_path):
    package = Package(tmp_path)
    package.report['mainEvents'] = []
    package.charts['1']['notes'] = deepcopy(package.charts['0']['notes'])
    package.charts['hybrid']['notes'] = deepcopy(package.charts['1']['notes'])
    package.groups[1].update(time=0., notes=deepcopy(package.groups[0]['notes']))
    groups = package.load()
    assert len(groups)==1 and groups[0]['trackId']=='1' and groups[0]['direction']=='up'


def test_repeat_occurrence_and_selection_are_bound_independently(tmp_path):
    package = Package(tmp_path)
    repeated = deepcopy(package.groups[0]); repeated.update(time=4., occurrence=2)
    for n in repeated['notes']: n['t']+=4
    package.groups.append(repeated)
    notes = deepcopy(package.charts['0']['notes'])
    for n in notes:n['t']+=4
    package.charts['0']['notes'].extend(notes)
    package.charts['hybrid']['notes'].extend(deepcopy(notes))
    package.report['mainEvents'].extend([{**deepcopy(r),'index':r['index']+3,'occurrences':[2]} for r in package.refs['0'][:3]])
    assert len(package.load())==3
    package.report['mainEvents'][-1]['occurrences']=[1]
    assert len(package.load())==2


def test_ambiguous_original_member_is_not_resolved_by_selection(tmp_path):
    package = Package(tmp_path)
    package.charts['0']['notes'].append(deepcopy(package.charts['0']['notes'][0]))
    assert [g['trackId'] for g in package.load()]==['1']


@pytest.mark.parametrize('fault', ['hybrid-hash','source-chart-hash','source-hash','receipt-path',
    'direction','missing-main','unknown-donor','negative-index','boolean-index','duplicate-index',
    'changed-note','extra-note','source-id'])
def test_mismatched_evidence_cannot_group_hybrid_notes(tmp_path, fault):
    package = Package(tmp_path)
    if fault=='missing-main':package.report.pop('mainEvents')
    if fault=='unknown-donor':package.report['passages'][0]['trackId']='other'
    if fault=='negative-index':package.refs['0'][0]['index']=-1
    if fault=='boolean-index':package.refs['0'][0]['index']=True
    if fault=='duplicate-index':package.report['mainEvents'].append(deepcopy(package.refs['0'][0]))
    if fault=='changed-note':package.charts['hybrid']['notes'][0]['sus']+=.1
    if fault=='extra-note':package.charts['hybrid']['notes'].append(deepcopy(package.charts['hybrid']['notes'][0]))
    if fault=='source-id':package.refs['0'][0]['sourceIds']=['songsterr:0:9:0:0:0']
    loaded=package.save()
    if fault=='hybrid-hash':(tmp_path/'hybrid.json').write_text('{}')
    if fault=='source-chart-hash':(tmp_path/'0.json').write_text('{}')
    if fault=='source-hash':(tmp_path/'source.json').write_text('{}')
    if fault=='receipt-path':package.manifest['arrangements'][-1]['derived']['receipt']='../elsewhere.json'
    if fault=='direction':
        package.groups[0]['direction']='up'
        package.write('strums.json',{'version':1,'timeDomain':'recording_seconds',
            'sourceSha256':package.report['sourceSha256'],'groups':package.groups})
    if fault=='source-id':
        assert [g['trackId'] for g in strums.load_context(loaded,2)]==['1']
    else:
        with pytest.raises(ValueError):strums.load_context(loaded,2)


def test_split_voice_source_remains_bound_to_its_authored_voice(tmp_path):
    package=Package(tmp_path)
    ident='voice-'+hashlib.sha256(b'0').hexdigest()[:20]+'-1'
    package.charts[ident]=package.charts.pop('0')
    package.manifest['arrangements'][0].update(id=ident,file=ident+'.json')
    package.groups[0]['trackId']=ident
    package.report['mainTrackId']=ident
    package.manifest['song_import']['voicesFile']='voices.json'
    loaded=package.save()
    projection={'version':1,'policy':'source-voices-v1','timeDomain':'score_seconds',
        'sourceSha256':package.report['sourceSha256'],'tracks':[{'sourceTrackId':'0','mode':'split',
        'arrangements':[{'id':ident,'voices':[0]}]}]}
    package.write('voices.json',projection)
    assert len(strums.load_context(loaded,2))==2
    projection['tracks'][0]['arrangements'][0]['voices']=[1]
    package.write('voices.json',projection)
    with pytest.raises(ValueError,match='voice'):strums.load_context(loaded,2)


def ringing_package(root):
    package = Package(root)
    package.manifest['duration'] = 10
    package.manifest['song_import']['preservationContract'] = 110
    package.report['passages'][0].update(recordingStart=2, recordingEnd=3)
    for track in ('0', '1'):
        for note in package.charts[track]['notes']:
            note['lr'] = True
            note['let_ring_sus'] = 5
    package.charts['hybrid']['notes'] = deepcopy(package.charts['0']['notes'] + package.charts['1']['notes'])
    for note in package.charts['hybrid']['notes']:
        edge = 2 if note['t'] < 2 else 3
        note['let_ring_sus'] = round(edge - note['t'], 6)
    return package


def test_hybrid_ringing_limits_preserve_complete_strums_and_source(tmp_path):
    package = ringing_package(tmp_path)
    before = deepcopy(package.charts)
    assert len(package.load()) == 2
    assert package.charts == before


@pytest.mark.parametrize('fault', ['longer', 'shorter', 'missing', 'pitch', 'timing', 'scored-duration', 'legacy'])
def test_hybrid_ringing_does_not_weaken_note_validation(tmp_path, fault):
    package = ringing_package(tmp_path)
    note = package.charts['hybrid']['notes'][0]
    if fault == 'longer': note['let_ring_sus'] += .1
    if fault == 'shorter': note['let_ring_sus'] -= .1
    if fault == 'missing': note.pop('let_ring_sus')
    if fault == 'pitch': note['f'] += 1
    if fault == 'timing': note['t'] += .1
    if fault == 'scored-duration': note['sus'] += .1
    if fault == 'legacy': package.manifest['song_import']['preservationContract'] = 109
    with pytest.raises(ValueError, match='absent or changed'):
        package.load()


def test_next_selected_attack_can_remove_ringing_extension(tmp_path):
    package = ringing_package(tmp_path)
    # A selected source chord replaces the donor's ringing at its written end.
    chord = {'t': 2.5, 'notes': [{'s': 0, 'f': 8, 'sus': .2}]}
    package.charts['1']['chords'] = [chord]
    package.charts['hybrid']['chords'] = [deepcopy(chord)]
    package.report['passages'][0]['events'].append({'kind': 'chords', 'index': 0})
    package.charts['hybrid']['notes'][3].pop('let_ring_sus')
    assert len(package.load()) == 2
