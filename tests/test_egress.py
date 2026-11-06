"""Tests for Step 4, ASET and RSET (fire_model/egress.py)."""

import pytest

from fire_model.egress import (
    OCCUPANT_PRESETS,
    REASON_SMOKE_HOT,
    REASON_SMOKE_LOW,
    Occupant,
    aset,
    distance_left_to_walk,
    occupant_status,
    rset,
    safety_margin,
)
from fire_model.flashover import hrr_history
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS, temperature_history
from fire_model.room import Room
from fire_model.smoke_filling import smoke_layer_heights


# ---- RSET ----

def test_rset_awake_with_alarm():
    # CLAUDE.md: RSET for "awake with alarm" = 63.3 s  (30 + 30 + 4 / 1.2)
    assert rset(OCCUPANT_PRESETS["Awake, smoke alarm in room"]) == pytest.approx(63.3, abs=0.05)


def test_rset_is_detection_plus_reaction_plus_walking():
    person = OCCUPANT_PRESETS["Needs help to move"]  # 30 s, 90 s, 4 m at 0.5 m/s
    assert rset(person) == pytest.approx(30 + 90 + 4 / 0.5)


def test_zero_walking_speed_is_rejected():
    with pytest.raises(ValueError):
        rset(Occupant(30, 30, 4, 0))


# ---- ASET, with the bedroom check scenario ----

def test_bedroom_aset_is_set_by_smoke_reaching_head_height():
    # CLAUDE.md: bedroom smoke layer reaches 1.8 m at 29 s. At that point the
    # layer is still far below 200 °C, so smoke height sets ASET.
    room = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)
    gypsum = LININGS["Gypsum board"]
    alpha = growth_coefficient(GROWTH_TIMES["fast"])
    sofa = FUEL_PEAK_HRR["Sofa"]

    z = smoke_layer_heights(alpha, sofa, room, gypsum, 600)
    temps = temperature_history(hrr_history(alpha, sofa, room, 600), room, gypsum)

    assert aset(z, temps) == (29, REASON_SMOKE_LOW)


# ---- ASET logic, with simple made-up lists (not physics data) ----

def test_aset_hot_layer_first():
    heights = [2.4, 2.3, 2.2, 2.1]  # never reaches 1.8 m
    temps = [20, 100, 210, 300]  # reaches 200 °C at t = 2 s
    assert aset(heights, temps) == (2, REASON_SMOKE_HOT)


def test_aset_same_second_reports_smoke_height():
    heights = [2.4, 2.0, 1.7]
    temps = [20, 150, 250]
    assert aset(heights, temps) == (2, REASON_SMOKE_LOW)


def test_aset_room_stays_tenable():
    assert aset([2.4, 2.3, 2.2], [20, 50, 80]) == (None, None)


# ---- Safety margin ----

def test_safety_margin():
    assert safety_margin(100, 63.3) == pytest.approx(36.7)
    assert safety_margin(29, 63.3) == pytest.approx(-34.3)  # untenable before escape
    assert safety_margin(None, 63.3) is None


# ---- Where the occupant is (used by the 3D room view) ----

def test_occupant_timeline():
    person = OCCUPANT_PRESETS["Awake, smoke alarm in room"]  # 30 s, 30 s, 4 m at 1.2 m/s
    assert occupant_status(10, person) == "Alarm not yet sounding"
    assert occupant_status(45, person) == "Alarm sounding, occupant reacting"
    assert occupant_status(62, person) == "Occupant walking to door"
    assert occupant_status(64, person) == "Occupant is out"  # RSET = 63.3 s

    assert distance_left_to_walk(0, person) == 4  # hasn't moved yet
    assert distance_left_to_walk(61, person) == pytest.approx(4 - 1.2)  # 1 s of walking
    assert distance_left_to_walk(rset(person), person) == pytest.approx(0)
