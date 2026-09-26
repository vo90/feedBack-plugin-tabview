# slopsmith-plugin-tabview

A [feedBack](https://github.com/got-feedback/feedback) plugin that renders custom-song arrangements as traditional guitar tablature using [alphaTab](https://www.alphatab.net/).

## Features

- Converts arrangement XML to Guitar Pro 5 format on the fly
- Renders scrolling tablature notation via alphaTab in the browser
- Cursor syncs to the existing audio playback
- Supports guitar and bass arrangements
- Preserves techniques: bends, slides, hammer-ons, pull-offs, harmonics, palm mutes, tremolo picking
- Handles custom tunings and capo
- Per-measure tempo changes
- Adaptive display rhythm keeps closely spaced notes separate, including 64th/128th notes and supported tuplets

The display export chooses a suitable rhythm for each measure. Ordinary
32nd-note-grid passages keep their existing layout; denser or clearly tuplet
passages use finer divisions. Split sustained durations use ties, preserving
one attack. Notes are never merged merely because the display grid is too
coarse. If GP5 cannot represent the spacing, Tab View reports the measure and
keeps the highway available. This changes neither song data nor scoring.
The display bundle also restores 128th-note values missed by the pinned
alphaTab GP5 reader. Cursor timing accumulates tuplet durations before
rounding, avoiding drift across a measure or skipped short-note seeks.

## Installation

Copy (or symlink) this directory into your feedBack `plugins/` folder:

```bash
cd /path/to/feedBack/plugins
git clone https://github.com/got-feedback/feedback-plugin-tabview.git tabview
```

Restart feedBack. The plugin loads automatically.

## Usage

1. Open any song in the player
2. Click the **Tab View** button in the player controls bar
3. The highway canvas is replaced with scrolling tablature notation
4. The cursor follows the audio playback
5. Click **Highway** to switch back to the note highway

## Dependencies

- **Server**: `pyguitarpro` (already included in feedBack's requirements)
- **Client**: alphaTab is loaded from CDN on first use

## How it works

1. **routes.py** exposes `GET /api/plugins/tabview/gp5/{filename}?arrangement=N`
2. **rs2gp.py** converts the arrangement (notes, chords, beats, tuning, techniques) into a Guitar Pro 5 file using `pyguitarpro`
3. **screen.js** loads alphaTab from CDN, fetches the GP5 file, renders it, and syncs the cursor to `audio.currentTime` using the beat timing data from the highway

## Files

| File | Purpose |
|------|---------|
| `plugin.json` | Plugin manifest |
| `routes.py` | FastAPI endpoint serving GP5 files |
| `rs2gp.py` | arrangement → Guitar Pro 5 converter |
| `screen.js` | Frontend: alphaTab integration, cursor sync, UI |

Exact bar expressions retain their original pitch/time mapping. For mapped
curves, the pinned alphaTab renderer reserves their vertical space and formats
interpolated depths compactly (whole-tone units; `≈` marks rounded display text).
Only collinear rendering samples are omitted. Notes, model points, source values
and normal GP bends remain unchanged. These charts use the local renderer so
the scoped formatting also applies when workers are otherwise enabled.

Songsterr strummed chords use `song_import.strumsFile` when FeedForge includes
the source-bound display groups (preservation contract 26). TabView validates
the original source hash and authored direction, then matches every group member
by string, fret and exact mapped onset before drawing one chord and its stroke
mark. Original gameplay attacks, scoring, durations and pitch curves stay intact.
Repeated/shifted strokes and tempo mapping use the retained performed times.
Missing or ambiguous members are not guessed or combined into partial chords.
Older imports without these groups keep their existing display behavior; import
again with the updated FeedForge to add the metadata.
