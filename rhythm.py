"""Bounded display rhythm for GP5, independent of gameplay/scoring timing."""
from bisect import bisect_right
from fractions import Fraction
from functools import lru_cache
from math import isfinite, lcm

import guitarpro

LEGACY_GRID = 8
# Binary durations through 128ths and GP5's supported tuplet ratios.
GRIDS = (8, 12, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 44, 48, 52, 56)
TUPLETS = ((1, 1), (3, 2), (5, 4), (7, 4), (9, 8), (11, 8), (13, 8))
MAX_GRID = 1536
MAX_UNITS = 16384
FIT_SECONDS = 0.0011  # accommodates the game's existing millisecond wire rounding


class RhythmError(ValueError):
    """The display bridge cannot represent this passage without losing notes."""


def quarter(time, measure):
    times = measure['beat_times'][:measure['num_beats']]
    index = max(0, min(len(times) - 1, bisect_right(times, time) - 1))
    end = times[index + 1] if index + 1 < len(times) else measure['end_time']
    interval = end - times[index]
    if interval <= 0 or not isfinite(time):
        raise RhythmError('Tab timing contains an invalid beat interval.')
    return index + (time - times[index]) / interval, interval


def seconds(position, measure):
    times = measure['beat_times'][:measure['num_beats']]
    index = max(0, min(len(times) - 1, int(position)))
    end = times[index + 1] if index + 1 < len(times) else measure['end_time']
    return times[index] + (position - index) * (end - times[index])


@lru_cache(maxsize=128)
def _options(grid):
    options = []
    for value in (1, 2, 4, 8, 16, 32, 64, 128):
        for dotted in (False, True):
            for enters, times in TUPLETS:
                units = Fraction(4 * grid * times, value * enters)
                if dotted:
                    units *= Fraction(3, 2)
                if units.denominator == 1:
                    options.append((int(units), value, dotted, enters, times))
    return tuple(sorted(options, key=lambda o: (-o[0], o[3] != 1, o[2], o[1])))


@lru_cache(maxsize=8192)
def _parts(count, grid):
    if not 0 < count <= MAX_UNITS:
        raise RhythmError('Tab rhythm exceeds the supported display resolution.')
    # A short exact decomposition, preferring ordinary durations over tuplets.
    best = [None] * (count + 1)
    best[0] = ((0, 0), ())
    options = _options(grid)
    for remaining in range(1, count + 1):
        for option in options:
            length, _, _, enters, _ = option
            if length > remaining or best[remaining - length] is None:
                continue
            score, previous = best[remaining - length]
            score = (score[0] + 1, score[1] + (enters != 1))
            if best[remaining] is None or score < best[remaining][0]:
                best[remaining] = (score, (option,) + previous)
    if best[count] is None:
        raise RhythmError('This passage is too closely spaced for faithful tab notation.')
    return best[count][1]


def durations(count, grid):
    return [guitarpro.Duration(value=value, isDotted=dotted,
                tuplet=guitarpro.Tuplet(enters=enters, times=times))
            for _, value, dotted, enters, times in _parts(count, grid)]


def units(duration, grid):
    result = Fraction(duration.time, guitarpro.Duration.quarterTime) * grid
    if result.denominator != 1:
        raise RhythmError('Tab duration does not fit the selected display rhythm.')
    return int(result)


def layout(events, measure):
    """Choose the coarsest faithful grid; preserve old off-grid rounding if safe.

    Separate onsets must never share a slot, even when on different strings.
    True simultaneous events still form chords. Tuplets are selected only when
    they fit within wire precision, not invented to approximate arbitrary time.
    """
    onsets = sorted({event['time'] for event in events})
    positions = [quarter(time, measure) for time in onsets]
    beats = measure['num_beats']

    def attempt(grid, require_fit):
        if grid > MAX_GRID or beats * grid > MAX_UNITS:
            return None
        slots = [max(0, min(beats * grid - 1, int(q * grid + .5))) for q, _ in positions]
        if len(slots) != len(set(slots)):
            return None
        if require_fit and any(abs(q - slot / grid) * span > FIT_SECONDS
                               for (q, span), slot in zip(positions, slots)):
            return None
        edges = sorted({0, beats * grid, *slots})
        try:
            for left, right in zip(edges, edges[1:]):
                _parts(right - left, grid)
        except RhythmError:
            return None
        return grid, dict(zip(onsets, slots))

    for grid in GRIDS:
        result = attempt(grid, True)
        if result:
            return result

    # Mixed binary/tuplet measures may need a common grid. Actual durations
    # still have to be serializable: a tiny common-grid unit is not itself a
    # license to emit an unsupported note value.
    mixed = LEGACY_GRID
    for q, span in positions:
        matching = next((g for g in GRIDS if abs(q - round(q * g) / g) * span <= FIT_SECONDS), None)
        if matching is None:
            break
        mixed = lcm(mixed, matching)
    else:
        result = attempt(mixed, True)
        if result:
            return result

    for grid in (8, 16, 32):
        result = attempt(grid, False)
        if result:
            return result
    raise RhythmError('This passage is too closely spaced for faithful tab notation; the highway retains every note.')
