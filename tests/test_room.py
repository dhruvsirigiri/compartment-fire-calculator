"""Tests for room geometry (fire_model/room.py), using the CLAUDE.md check values."""

import pytest

from fire_model.room import (
    Room,
    door_area,
    floor_area,
    interior_surface_area,
    opening_factor,
    room_problems,
)

BEDROOM = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)


def test_bedroom_opening_factor():
    # CLAUDE.md: opening factor 2.546  (= 0.9 * 2.0 * sqrt(2.0))
    assert opening_factor(BEDROOM) == pytest.approx(2.546, abs=0.0005)


def test_bedroom_interior_surface_area():
    # CLAUDE.md: A_T 81.4 m^2  (= 2(20 + 12 + 9.6) - 1.8)
    assert interior_surface_area(BEDROOM) == pytest.approx(81.4, abs=0.05)


def test_bedroom_door_and_floor_area():
    assert door_area(BEDROOM) == pytest.approx(1.8)
    assert floor_area(BEDROOM) == pytest.approx(20.0)


def test_room_is_frozen():
    # A Room can't be changed by accident after it is created.
    with pytest.raises(Exception):
        BEDROOM.length = 10


def test_check_values_rooms_are_valid():
    assert room_problems(BEDROOM) == []


def test_impossible_rooms_are_reported():
    too_tall = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.6)
    too_wide = Room(length=3, width=2, height=2.4, door_width=3.5, door_height=2.0)
    assert any("taller than the ceiling" in p for p in room_problems(too_tall))
    assert any("wider than every wall" in p for p in room_problems(too_wide))
