"""Convert arrangement data to Guitar Pro 5 format."""

import io
import base64
import hashlib
from copy import deepcopy
import guitarpro
import rhythm
from whammy_map import build_mapping
from harmonic_contacts import display_events, build_mapping as contact_mapping
from song import arrangement_string_count

TICKS_PER_BEAT = 960
SUBDIV = 8  # 32nd notes per beat

# Standard open-string MIDI values: GP string 1 (highest) to N (lowest).
#
# Guitar: extended to cover 6/7/8-string instruments. Each extra lower string
# is a perfect fourth (5 semitones) below the previous one in standard tuning.
#   6-string standard: E4 B3 G3 D3 A2 E2
#   7-string adds:     B1  (standard low-B 7-string)
#   8-string adds:     F#1 (standard low-F# 8-string)
GUITAR_STANDARD = [64, 59, 55, 50, 45, 40, 35, 30]  # E4 B3 G3 D3 A2 E2 B1 F#1

# Bass: keyed by string count because a 6-string bass gains a *high* string
# (C3) relative to 4/5-string, shifting the whole table upward — not just
# appending a new low string. 4-string and 5-string share the same high
# string (G2=43), so they can share a contiguous prefix.
#   4-string standard: G2 D2 A1 E1
#   5-string adds low: B0
#   6-string adds low B0 AND high C3
BASS_STANDARD = {
    4: [43, 38, 33, 28],
    5: [43, 38, 33, 28, 23],
    6: [48, 43, 38, 33, 28, 23],
}


def arrangement_to_gp5(song, arrangement_index=0, include_harmonics=False):
    """Convert a Song arrangement to GP5 bytes."""
    arr = song.arrangements[arrangement_index]

    # path_bass is populated from existing arrangement data and is more reliable than
    # name-matching alone for official DLC (which can have localised or
    # abbreviated arrangement names). Name-match is the fallback for custom charts and
    # sloppaks that don't carry path flags.
    is_bass = bool(arr.path_bass) or "bass" in arr.name.lower()

    # arrangement_string_count() (song.py) handles the RS XML quirk where
    # arr.tuning is always length 6 regardless of instrument: it combines the
    # highest string index seen in notes/chords, a name-based fallback (4 for
    # bass, 6 for guitar), and len(arr.tuning) when it isn't the RS-XML
    # padded value of 6 (trustworthy for sloppak/GP-imported sources).
    num_strings = arrangement_string_count(arr)

    measures_info = _parse_measures(song.beats)
    if not measures_info:
        measures_info = [_fallback_measure(song.song_length)]

    events = display_events(_merge_events(arr),measures_info)

    # --- GP3/4/5 hard limit: writeTrack only writes 7 tuning slots, and
    # writeNotes packs note strings into an 8-bit stringFlags byte via
    # `1 << (7 - note.string)`, so note.string must be in 1..7. There is no
    # way to represent an 8-string instrument in this format — pyguitarpro
    # has no GP6+/.gpx writer that would lift this cap.
    #
    # Workaround for 8-string guitar: in practice most 8-string custom charts only
    # plays 7 distinct strings (the 8th exists in the tuning/instrument
    # definition but is never actually notated). If that's true for this
    # arrangement, drop the one *unused* string and shift the remaining 7
    # into GP strings 1-7 — this preserves every note. If all 8 strings are
    # genuinely used, fall back to dropping the lowest string (gp_str > 7),
    # which is the only option GP5 leaves us.
    #
    # TODO: the real fix is to stop going through pyguitarpro/GP5 for this
    # path and feed alphaTab (already used by screen.js for rendering) its
    # own score format directly, which has no string-count ceiling.
    remap = None
    if num_strings == 8:
        used = _used_string_indices(events)
        if len(used) <= 7:
            remaining = sorted(used)
            remap = {rs: len(remaining) - rank for rank, rs in enumerate(remaining)}
            num_strings = len(remaining)

    gp = guitarpro.Song()
    gp.title = song.title or "Untitled"
    gp.artist = song.artist or ""
    gp.album = song.album or ""
    gp.measureHeaders = []
    gp.tracks = []

    # Set initial tempo from first measure
    gp.tempo = max(30, min(300, round(measures_info[0]["bpm"])))

    track = guitarpro.Track(gp, number=1)
    track.name = arr.name or ("Bass" if is_bass else "Guitar")
    track.channel = guitarpro.MidiChannel(
        channel=1 if is_bass else 0,
        effectChannel=3 if is_bass else 2,
        instrument=33 if is_bass else 30,
    )
    track.strings = _make_strings(arr.tuning, is_bass, num_strings, remap)
    track.indicateTuning = True
    track.measures = []

    tick = TICKS_PER_BEAT
    prev_bpm = gp.tempo
    harmonic_notes = {}
    bar_notes = {}
    contact_notes = {}

    for i, m_info in enumerate(measures_info):
        header = guitarpro.MeasureHeader(number=i + 1, start=tick)
        header.timeSignature = guitarpro.TimeSignature()
        header.timeSignature.numerator = m_info["num_beats"]
        header.timeSignature.denominator = guitarpro.Duration(value=4)
        gp.measureHeaders.append(header)

        m_events = [
            e
            for e in events
            if m_info["start_time"] <= e["time"] < m_info["end_time"]
        ]

        measure = guitarpro.Measure(track, header)
        voice = measure.voices[0]
        try:
            voice.beats = _create_beats(m_events, m_info, voice, num_strings, remap, harmonic_notes, bar_notes, contact_notes)
        except rhythm.RhythmError as exc:
            raise rhythm.RhythmError(f'Measure {i + 1}: {exc}') from exc

        # Tempo change via MixTableChange on the first beat
        cur_bpm = max(30, min(300, round(m_info["bpm"])))
        if i > 0 and cur_bpm != prev_bpm and voice.beats:
            first_beat = voice.beats[0]
            first_beat.effect.mixTableChange = guitarpro.MixTableChange(
                tempo=guitarpro.MixTableItem(value=cur_bpm, duration=1, allTracks=True),
            )
        prev_bpm = cur_bpm

        track.measures.append(measure)
        tick += m_info["num_beats"] * TICKS_PER_BEAT

    gp.tracks = [track]

    buf = io.BytesIO()
    guitarpro.write(gp, buf)
    data = buf.getvalue()
    if not include_harmonics:
        return data
    # Addresses refer to the generated model, before serialization. Never
    # match by approximate time/fret after GP5 has quantized the rhythm.
    mapping = []
    for bar, measure in enumerate(track.measures):
        for vi, voice in enumerate(measure.voices):
            for bi, beat in enumerate(voice.beats):
                for note in beat.notes:
                    evidence = harmonic_notes.get(id(note))
                    if evidence:
                        mapping.append(dict(track=0, staff=0, bar=bar, voice=vi, beat=bi,
                            string=len(track.strings) + 1 - note.string,
                            gpString=note.string, fret=note.value, **evidence))
    # alphaTab 1.8.2's GP5 reader falls back to a quarter for value 128,
    # although its score model/renderer supports 128ths. Bind that missing
    # reader field to exact generated beat addresses in the hashed bundle.
    short_durations = []
    for bar, measure in enumerate(track.measures):
        for vi, voice in enumerate(measure.voices):
            for bi, beat in enumerate(voice.beats):
                if beat.duration.value == 128:
                    short_durations.append(dict(bar=bar, voice=vi, beat=bi, value=128,
                        notes=[dict(string=len(track.strings)+1-n.string, fret=n.value,
                                    dead=n.type==guitarpro.NoteType.dead) for n in beat.notes]))
    return {"version":1, "gp5":base64.b64encode(data).decode('ascii'),
            "sha256":hashlib.sha256(data).hexdigest(), "harmonics":mapping,
            "rhythm":{"version":1,"shortDurations":short_durations},
            "whammy":build_mapping(track,measures_info,bar_notes),
            "harmonicContacts":contact_mapping(track,contact_notes)}


# ---------------------------------------------------------------------------
# Measure parsing
# ---------------------------------------------------------------------------

def _parse_measures(beats):
    """Parse arrangement beats into measure info dicts."""
    if not beats:
        return []

    groups = []
    cur = []
    for b in beats:
        if b.measure >= 0 and cur:
            groups.append(cur)
            cur = []
        cur.append(b)
    if cur:
        groups.append(cur)

    result = []
    for i, grp in enumerate(groups):
        start = grp[0].time
        if i + 1 < len(groups):
            end = groups[i + 1][0].time
        else:
            if len(grp) > 1:
                avg = (grp[-1].time - grp[0].time) / (len(grp) - 1)
                end = grp[-1].time + avg
            elif result:
                end = start + (result[-1]["end_time"] - result[-1]["start_time"])
            else:
                end = start + 2.0

        n = len(grp)
        if n > 1:
            interval = (grp[-1].time - grp[0].time) / (n - 1)
            bpm = 60.0 / interval if interval > 0 else 120.0
        elif result:
            bpm = result[-1]["bpm"]
        else:
            bpm = 120.0

        result.append(
            {
                "start_time": start,
                "end_time": end,
                "num_beats": n,
                "beat_times": [b.time for b in grp],
                "bpm": bpm,
            }
        )
    return result


def _fallback_measure(length):
    length = length or 60.0
    return {
        "start_time": 0.0,
        "end_time": length,
        "num_beats": 4,
        "beat_times": [i * 0.5 for i in range(8)],
        "bpm": 120.0,
    }


# ---------------------------------------------------------------------------
# Event merging
# ---------------------------------------------------------------------------

_NOTE_FIELDS = [
    "slide_to",
    "bend",
    "hammer_on",
    "pull_off",
    "harmonic",
    "harmonic_pinch",
    "harmonic_target",
    "harmonic_changes",
    "whammy",
    "harmonic_node",
    "harmonic_pitch",
    "harmonic_alias",
    "ghost",
    "palm_mute",
    "mute",
    "tremolo",
    "accent",
    "tap",
    "pick_scrape_marks",
]


def _note_dict(n):
    d = {"string": n.string, "fret": n.fret, "sustain": n.sustain}
    for f in _NOTE_FIELDS:
        d[f] = getattr(n, f, False)
    return d


def _merge_events(arr):
    events = []
    for index, n in enumerate(arr.notes):
        ev = _note_dict(n)
        ev["time"] = n.time
        ev["type"] = "note"
        ev["source_id"] = f"note:{index}"
        events.append(ev)

    for index, ch in enumerate(arr.chords):
        if ch.high_density:
            continue
        events.append(
            {
                "time": ch.time,
                "type": "chord",
                "chord_notes": [dict(_note_dict(cn), source_id=f"chord:{index}:{ni}") for ni,cn in enumerate(ch.notes)],
            }
        )

    events.sort(key=lambda e: e["time"])
    return events


def _used_string_indices(events):
    """Set of RS string indices (0-based) actually played in this arrangement."""
    used = set()
    for ev in events:
        if ev["type"] == "chord":
            for nd in ev["chord_notes"]:
                used.add(nd["string"])
        else:
            used.add(ev["string"])
    return used


# ---------------------------------------------------------------------------
# String tuning helpers
# ---------------------------------------------------------------------------

def _make_strings(tuning, is_bass, num_strings, remap=None):
    """Build the GP GuitarString list for a track.

    For guitar, GUITAR_STANDARD covers 6–8 strings directly. For bass,
    BASS_STANDARD is keyed by count because 6-string bass adds a high C
    string (shifting the whole table up) rather than just appending a low
    string. Both tables are extended by perfect-fourth extrapolation for
    any count beyond the defined range, which should only occur for
    genuinely exotic instruments not currently in the custom-song corpus.

    `remap` (8-string guitar only): dict of {rs_string_index: gp_string_number}
    covering 7 of the 8 RS strings (one unused string dropped). When present,
    builds a 7-string GP track using the correct GUITAR_STANDARD entry and
    tuning offset for each remaining RS string, in its proper gp_str slot.
    """
    if is_bass:
        standard = BASS_STANDARD.get(num_strings)
        if standard is None:
            # Nearest defined key, then extend downward by perfect fourths.
            nearest_key = min(BASS_STANDARD.keys(), key=lambda k: abs(k - num_strings))
            base = list(BASS_STANDARD[nearest_key])
            while len(base) < num_strings:
                base.append(base[-1] - 5)
            standard = base[:num_strings]
    else:
        standard = GUITAR_STANDARD

    if remap is not None:
        # One slot per remapped RS string. `remap` values are gp string
        # numbers 1..len(remap) (== num_strings), so a fixed size of 7 would
        # leave trailing None slots when an 8-string arrangement uses ≤6
        # distinct strings — pyguitarpro's writeTrack then dereferences
        # None.value and 500s. Size to the actual number of filled slots.
        strings = [None] * len(remap)
        for rs_idx, gp_str in remap.items():
            gp_idx_8 = 7 - rs_idx  # this RS string's position in the original 8-string table
            if gp_idx_8 < len(standard):
                base_midi = standard[gp_idx_8]
            else:
                base_midi = standard[-1] - 5 * (gp_idx_8 - len(standard) + 1)
            midi_val = base_midi + (tuning[rs_idx] if rs_idx < len(tuning) else 0)
            strings[gp_str - 1] = guitarpro.GuitarString(number=gp_str, value=midi_val)
        return strings

    # GP3/4/5 can only represent 7 strings; for num_strings==8 without a
    # remap (all 8 strings genuinely used), gp_str > 7 notes are dropped in
    # _create_beats, so only build the 7 strings that can be represented.
    n = min(num_strings, 7)
    strings = []
    for gp_idx in range(n):
        rs_idx = num_strings - 1 - gp_idx
        if gp_idx < len(standard):
            base_midi = standard[gp_idx]
        else:
            # Extrapolate downward by perfect fourths beyond the table.
            base_midi = standard[-1] - 5 * (gp_idx - len(standard) + 1)
        midi_val = base_midi + (tuning[rs_idx] if rs_idx < len(tuning) else 0)
        strings.append(guitarpro.GuitarString(number=gp_idx + 1, value=midi_val))
    return strings


# ---------------------------------------------------------------------------
# Beat creation
# ---------------------------------------------------------------------------

def _quantize_sixteenth(event_time, beat_times, measure_end):
    """Return the nearest 32nd-note position index within a measure."""
    best, best_d = 0, float("inf")
    for i, bt in enumerate(beat_times):
        nxt = beat_times[i + 1] if i + 1 < len(beat_times) else measure_end
        dur = nxt - bt
        for sub in range(SUBDIV):
            t = bt + dur * sub / SUBDIV
            d = abs(event_time - t)
            if d < best_d:
                best_d = d
                best = i * SUBDIV + sub
    return best


def _decompose_sixteenths(count):
    """Break a 32nd-note count into a list of guitarpro.Duration objects."""
    if count <= 0:
        return [guitarpro.Duration(value=4)]
    durs = []
    rem = count
    while rem > 0:
        d = guitarpro.Duration()
        if rem >= 32:
            d.value = 1
            rem -= 32
        elif rem >= 24:
            d.value = 2
            d.isDotted = True
            rem -= 24
        elif rem >= 16:
            d.value = 2
            rem -= 16
        elif rem >= 12:
            d.value = 4
            d.isDotted = True
            rem -= 12
        elif rem >= 8:
            d.value = 4
            rem -= 8
        elif rem >= 6:
            d.value = 8
            d.isDotted = True
            rem -= 6
        elif rem >= 4:
            d.value = 8
            rem -= 4
        elif rem >= 3:
            d.value = 16
            d.isDotted = True
            rem -= 3
        elif rem >= 2:
            d.value = 16
            rem -= 2
        else:
            d.value = 32
            rem -= 1
        durs.append(d)
    return durs


def _dur_sixteenths(d):
    """Number of 32nd notes a Duration occupies."""
    base = {1: 32, 2: 16, 4: 8, 8: 4, 16: 2, 32: 1}
    v = base.get(d.value, 8)
    if d.isDotted:
        v = int(v * 1.5)
    return max(v, 1)


def _create_beats(events, m_info, voice, num_strings, remap=None, harmonic_notes=None, bar_notes=None, contact_notes=None):
    """Build GP Beat list for one measure."""
    if not events:
        return _rest_beats(m_info['num_beats'] * SUBDIV, voice)

    grid, onset_slots = rhythm.layout(events, m_info)
    total = m_info['num_beats'] * grid
    decompose = _decompose_sixteenths if grid == SUBDIV else lambda n: rhythm.durations(n, grid)
    duration_units = _dur_sixteenths if grid == SUBDIV else lambda d: rhythm.units(d, grid)

    slots = {}
    for ev in events:
        pos = onset_slots[ev['time']]
        slots.setdefault(pos, []).append(ev)

    positions = sorted(slots.keys())
    beats = []
    cursor = 0

    for i, pos in enumerate(positions):
        if pos > cursor:
            beats.extend(_rest_beats(pos - cursor, voice, grid))
            cursor = pos

        nxt = positions[i + 1] if i + 1 < len(positions) else total
        gap = max(1, nxt - pos)
        durations = decompose(gap)

        beat = guitarpro.Beat(voice, status=guitarpro.BeatStatus.normal)
        beat.duration = durations[0]

        seen = set()
        sounding_until = {}
        for ev in slots[pos]:
            note_dicts = (
                ev.get("chord_notes", []) if ev["type"] == "chord" else [] if ev["type"] == "boundary" else [ev]
            )
            for nd in note_dicts:
                if remap is not None:
                    gp_str = remap.get(nd["string"])
                    if gp_str is None:
                        # this is the one unused 8th string — nothing to drop here
                        continue
                else:
                    gp_str = num_strings - nd["string"]
                    if gp_str < 1 or gp_str > 7:
                        continue

                if gp_str in seen:
                    continue
                seen.add(gp_str)
                # FeedPak uses 127 + mute for an unpitched dead note. GP5 has
                # no such sentinel: alphaTab treats its numeric value as pitch
                # even for dead notes, producing ledger lines far above the
                # staff. Use GP5's neutral dead-note value and retain the X;
                # keep explicit frets on other muted notes unchanged.
                scrape = nd.get("pick_scrape_marks") if nd.get("mute") else None
                gp_fret = 0 if nd.get("mute") and (nd["fret"] == 127 or scrape) else nd["fret"]
                note = guitarpro.Note(
                    beat, value=gp_fret, string=gp_str,
                    velocity=guitarpro.Velocities.forte,
                    type=guitarpro.NoteType.normal,
                )
                if nd.get("mute"):
                    note.type = guitarpro.NoteType.dead
                if scrape:
                    # GP5 has no typed pick-scrape interval. Label the X on the
                    # correct string instead of fabricating pitched slide ends.
                    # Exact timing remains in the FeedPak; this is display export.
                    label = "PICK SCRAPE " + " then ".join(m["direction"] for m in scrape)
                    if label not in (beat.text or ""):
                        beat.text = ((beat.text or "") + "; " + label).strip("; ")
                _apply_effects(note, nd)
                sustain = nd.get('sustain') or 0
                sounding_until[id(note)] = ev['time'] + sustain if sustain > 0 else None
                if nd.get('display_tie'):note.type=guitarpro.NoteType.tie
                if contact_notes is not None and nd.get('contact_source'):
                    contact_notes[id(note)]={**nd['contact_source'],'tie':bool(nd.get('display_tie'))}
                    if nd.get('display_tie') and ev['time']>=nd['contact_source']['onset']+nd['contact_source']['event']['start']:
                        h=nd['contact_source']['event']['target']
                        beat.text=((beat.text or '')+f" AH {nd['fret']+h['node']:g}").strip()
                if bar_notes is not None and nd.get('whammy'):
                    bar_notes[id(note)]={'sourceId':nd['source_id'],'time':ev['time'],
                        'sustain':nd['sustain'],'expression':nd['whammy']}
                if harmonic_notes is not None and (nd.get('harmonic_target') or nd.get('harmonic_node')):
                    harmonic_notes[id(note)] = {
                        'sourceId':nd.get('source_id'), 'target':nd.get('harmonic_target') or None,
                        'naturalNode':nd.get('harmonic_node') or None,
                        'naturalPitch':nd.get('harmonic_pitch') or None,
                        'alias':nd.get('harmonic_alias') or None, 'ghost':bool(nd.get('ghost'))}
                beat.notes.append(note)

        if grid != SUBDIV:
            beats.extend(_adaptive_gap(beat, pos, nxt, grid, m_info, sounding_until,
                                       harmonic_notes, bar_notes, contact_notes))
            cursor = nxt
            continue
        if not beat.notes:beat.status=guitarpro.BeatStatus.rest
        beats.append(beat)
        cursor += duration_units(durations[0])

        for rd in durations[1:]:
            owned=[n for n in beat.notes if contact_notes is not None and id(n) in contact_notes]
            if owned:
                tied=guitarpro.Beat(voice,status=guitarpro.BeatStatus.normal);tied.duration=rd
                for original in owned:
                    note=guitarpro.Note(tied,value=original.value,string=original.string,type=guitarpro.NoteType.tie)
                    tied.notes.append(note)
                    contact_notes[id(note)]={**contact_notes[id(original)],'tie':True}
                beats.append(tied)
            else:beats.extend(_rest_beats(duration_units(rd), voice, grid))
            cursor += duration_units(rd)

    if cursor < total:
        beats.extend(_rest_beats(total - cursor, voice, grid))

    return beats


def _adaptive_gap(beat, start, end, grid, measure, sounding_until, harmonic_notes, bar_notes, contact_notes):
    """Fill one onset-to-onset interval without stretching notes over rests."""
    releases = {}
    for note in beat.notes:
        until = sounding_until[id(note)]
        if until is None or (contact_notes is not None and id(note) in contact_notes):
            # A zero sustain has no explicit release. Contact boundaries are
            # already supplied by display_events; retain their existing rule.
            releases[id(note)] = end
        else:
            q, _ = rhythm.quarter(until, measure)
            releases[id(note)] = max(start + 1, min(end, int(q * grid + .5)))
    edges = sorted({start, end, *releases.values()})
    result = []
    cursor = start
    for left, right in zip(edges, edges[1:]):
        for duration in rhythm.durations(right - left, grid):
            if cursor == start:
                current = beat
            else:
                current = guitarpro.Beat(beat.voice, status=guitarpro.BeatStatus.normal)
                for original in beat.notes:
                    if releases[id(original)] <= cursor:
                        continue
                    note = guitarpro.Note(current, value=original.value, string=original.string,
                                          type=guitarpro.NoteType.tie, velocity=original.velocity)
                    for effect in ('palmMute', 'vibrato', 'harmonic', 'ghostNote'):
                        setattr(note.effect, effect, deepcopy(getattr(original.effect, effect)))
                    current.notes.append(note)
                    for mapping in (harmonic_notes, bar_notes, contact_notes):
                        if mapping is not None and id(original) in mapping:
                            mapping[id(note)] = deepcopy(mapping[id(original)])
                            if mapping is contact_notes:
                                mapping[id(note)]['tie'] = True
            current.duration = duration
            if not current.notes:
                current.status = guitarpro.BeatStatus.rest
            result.append(current)
            cursor += rhythm.units(duration, grid)
    return result


def _rest_beats(sixteenths, voice, grid=SUBDIV):
    beats = []
    for d in (_decompose_sixteenths(sixteenths) if grid == SUBDIV else rhythm.durations(sixteenths, grid)):
        b = guitarpro.Beat(voice, status=guitarpro.BeatStatus.rest)
        b.duration = d
        beats.append(b)
    return beats


# ---------------------------------------------------------------------------
# Technique mapping
# ---------------------------------------------------------------------------

def _apply_effects(gp_note, nd):
    eff = gp_note.effect
    eff.ghostNote = bool(nd.get('ghost'))

    if nd.get("hammer_on") or nd.get("pull_off"):
        eff.hammer = True

    slide = nd.get("slide_to", -1)
    if isinstance(slide, int) and slide >= 0:
        eff.slides = [guitarpro.SlideType.shiftSlideTo]

    bend_val = nd.get("bend", 0)
    if bend_val and bend_val > 0:
        gp_val = int(bend_val * 2)  # RS semitones -> GP quarter-tones
        eff.bend = guitarpro.BendEffect(
            type=guitarpro.BendType.bend,
            value=gp_val,
            points=[
                guitarpro.BendPoint(position=0, value=0),
                guitarpro.BendPoint(position=6, value=gp_val),
                guitarpro.BendPoint(position=12, value=gp_val),
            ],
        )

    if nd.get("harmonic"):
        eff.harmonic = guitarpro.NaturalHarmonic()
    elif nd.get("harmonic_pinch"):
        eff.harmonic = guitarpro.PinchHarmonic()

    if nd.get("palm_mute"):
        eff.palmMute = True

    if nd.get("tremolo"):
        eff.tremoloPicking = guitarpro.TremoloPickingEffect(
            duration=guitarpro.Duration(value=8),
        )

    if nd.get("accent"):
        eff.accentuatedNote = True

    if nd.get("tap"):
        eff.hammer = True
