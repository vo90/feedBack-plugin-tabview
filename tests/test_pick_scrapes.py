import io
import guitarpro
import rs2gp


def test_scrapes_keep_strings_and_direction_as_dead_tab_with_no_fake_frets():
    gp = guitarpro.Song()
    voice = gp.tracks[0].measures[0].voices[0]
    source = {'string': 0, 'fret': 34, 'mute': True, 'pick_scrape_marks': [
        {'direction': 'down', 'start': 0, 'end': 1}, {'direction': 'up', 'start': 1, 'end': 2}]}
    voice.beats = rs2gp._create_beats([{'time': 0, 'type': 'chord', 'chord_notes': [
        source, {'string': 1, 'fret': 7}]}],
        {'num_beats': 4, 'beat_times': [0, .5, 1, 1.5], 'end_time': 2}, voice, 6)
    data = io.BytesIO(); guitarpro.write(gp, data); data.seek(0)
    beat = guitarpro.parse(data).tracks[0].measures[0].voices[0].beats[0]
    assert beat.text == 'PICK SCRAPE down then up'
    scrape = next(n for n in beat.notes if n.string == 6)
    pitched = next(n for n in beat.notes if n.string == 5)
    assert scrape.type == guitarpro.NoteType.dead and scrape.value == 0
    assert pitched.type == guitarpro.NoteType.normal and pitched.value == 7
    assert source['fret'] == 34
