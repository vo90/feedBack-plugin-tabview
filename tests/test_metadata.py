"""Unicode survives the display bundle; GP5 remains a compatible byte stream."""
import base64
from copy import deepcopy
import hashlib
from io import BytesIO

import guitarpro
import pytest
import rs2gp
from test_adaptive_rhythm import song_at, attacks


@pytest.mark.parametrize('text', [
    '(pronounced ’lĕh-’nérd ’skin-’nérd)',
    'Björk — Beyoncé “live” €',
    'e\u0306 / A\u030a',
    '東京 / Привет / مرحبا / 🎸',
    'A' * 254 + 'ĕ🎸' + 'é' * 100,
    '<Lead & "Rhythm">',
])
def test_all_metadata_fields_roundtrip_without_changing_music_or_source(text):
    song = song_at([0, 1, 2, 3])
    reference = guitarpro.parse(BytesIO(rs2gp.arrangement_to_gp5(song)))
    song.title = song.artist = song.album = song.arrangements[0].name = text
    before = deepcopy(song)
    bundle = rs2gp.arrangement_to_gp5(song, include_harmonics=True)
    raw = base64.b64decode(bundle['gp5'])
    parsed = guitarpro.parse(BytesIO(raw), encoding='cp1252')
    assert bundle['metadata'] == dict(version=1, title=text, artist=text, album=text, trackName=text)
    assert bundle['sha256'] == hashlib.sha256(raw).hexdigest()
    assert parsed.title == parsed.artist == parsed.album == rs2gp._gp5_text(text, 255)
    assert parsed.tracks[0].name == rs2gp._gp5_text(text, 40)
    assert len(parsed.title.encode('cp1252')) <= 255
    assert len(parsed.tracks[0].name.encode('cp1252')) <= 40
    assert attacks(parsed) == attacks(reference)
    assert song == before
    # The non-bundle endpoint must also work for external GP5 consumers.
    assert rs2gp.arrangement_to_gp5(song) == raw


def test_supported_labels_are_unchanged_and_only_the_proxy_is_simplified():
    supported = 'Björk — Beyoncé “live” €'
    assert rs2gp._gp5_text(supported, 255) == supported
    assert rs2gp._gp5_text('lĕh / e\u0306 / 🎸', 255) == 'leh / e / ?'
    assert rs2gp._gp5_text('é' * 300, 255) == 'é' * 255
    assert rs2gp._gp5_text('a' * 39 + 'ﬀ', 40) == 'a' * 39 + 'f'


def test_absent_optional_song_metadata_retains_existing_defaults():
    song = song_at([0])
    song.title = song.album = song.artist = ''
    song.arrangements[0].name = ''
    bundle = rs2gp.arrangement_to_gp5(song, include_harmonics=True)
    assert bundle['metadata'] == dict(version=1, title='Untitled', album='', artist='', trackName='Guitar')
