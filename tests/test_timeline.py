"""Tests for the once-per-second helpers (fire_model/timeline.py).

These are logic tests with simple made-up lists, not physics data.
"""

from fire_model.timeline import first_time_at_or_above, first_time_at_or_below


def test_first_time_at_or_above():
    values = [0, 5, 10, 15, 20]  # value at t = 0, 1, 2, 3, 4 s
    assert first_time_at_or_above(values, 10) == 2  # exactly equal counts
    assert first_time_at_or_above(values, 11) == 3
    assert first_time_at_or_above(values, 99) is None


def test_first_time_at_or_below():
    heights = [2.4, 2.2, 1.9, 1.8, 1.5]
    assert first_time_at_or_below(heights, 1.8) == 3
    assert first_time_at_or_below(heights, 0.5) is None


def test_ignition_value_at_t0_is_ignored():
    # t = 0 is the starting state, so it is never reported as an event.
    assert first_time_at_or_above([100, 0, 0], 50) is None
