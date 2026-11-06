"""Tests for Step 3: flashover and the air supply limit (fire_model/flashover.py).

Check values from CLAUDE.md. Times assume a 600 s simulation, the prototype's
default.
"""

import pytest

from fire_model.flashover import (
    babrauskas_flashover_hrr,
    effective_hrr,
    hrr_history,
    mqh_flashover_time,
    thomas_flashover_hrr,
    time_hrr_reaches,
    ventilation_limit,
)
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS, temperature_history
from fire_model.room import Room

T_END = 600  # s
GYPSUM = LININGS["Gypsum board"]
ALPHA_FAST = growth_coefficient(GROWTH_TIMES["fast"])
ALPHA_SLOW = growth_coefficient(GROWTH_TIMES["slow"])
SOFA = FUEL_PEAK_HRR["Sofa"]
CHAIR = FUEL_PEAK_HRR["Office chair"]

BEDROOM = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)
DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
LIVING_ROOM = Room(length=7, width=6, height=2.4, door_width=1.8, door_height=2.1)


def mqh_time(alpha, peak_hrr, room):
    """Run Steps 1-3 over time and return the MQH flashover time."""
    hrr = hrr_history(alpha, peak_hrr, room, T_END)
    return mqh_flashover_time(temperature_history(hrr, room, GYPSUM))


# ---- Bedroom ----

def test_bedroom_flashover_thresholds():
    # CLAUDE.md: Babrauskas 1909 kW; Thomas 1597 kW; Q_vent 3818 kW
    assert babrauskas_flashover_hrr(BEDROOM) == pytest.approx(1909, abs=0.5)
    assert thomas_flashover_hrr(BEDROOM) == pytest.approx(1597, abs=0.5)
    assert ventilation_limit(BEDROOM) == pytest.approx(3818, abs=0.5)


def test_bedroom_mqh_flashover_time():
    # CLAUDE.md: MQH flashover at 184 s
    assert mqh_time(ALPHA_FAST, SOFA, BEDROOM) == 184


# ---- Dorm example ----

def test_dorm_flashover_thresholds():
    # CLAUDE.md: Babrauskas 2054, Thomas 1591, Q_vent 4108 kW
    assert babrauskas_flashover_hrr(DORM) == pytest.approx(2054, abs=0.5)
    assert thomas_flashover_hrr(DORM) == pytest.approx(1591, abs=0.5)
    assert ventilation_limit(DORM) == pytest.approx(4108, abs=0.5)


def test_dorm_mqh_flashover_time():
    # CLAUDE.md: MQH flashover 182 s
    assert mqh_time(ALPHA_FAST, SOFA, DORM) == 182


# ---- Living room ----

def test_living_room_slow_chair_fire_has_no_flashover():
    # CLAUDE.md: slow fire, chair 750 kW: no flashover by any method.
    hrr = hrr_history(ALPHA_SLOW, CHAIR, LIVING_ROOM, T_END)
    assert time_hrr_reaches(hrr, babrauskas_flashover_hrr(LIVING_ROOM)) is None
    assert time_hrr_reaches(hrr, thomas_flashover_hrr(LIVING_ROOM)) is None
    assert mqh_time(ALPHA_SLOW, CHAIR, LIVING_ROOM) is None


# ---- The air supply limit ----

def test_fire_is_capped_by_the_air_supply():
    # A small window-sized opening that can only feed a small fire.
    # Logic test with a made-up room: Q_vent = 1500 * 0.5 * 1.0 * sqrt(1.0) = 750 kW
    small_opening = Room(length=5, width=4, height=2.4, door_width=0.5, door_height=1.0)
    assert ventilation_limit(small_opening) == pytest.approx(750)
    # At 300 s a fast sofa fire "wants" 2500 kW but can only get 750 kW of air.
    assert effective_hrr(300, ALPHA_FAST, SOFA, small_opening) == pytest.approx(750)


def test_bedroom_fire_reaches_the_flashover_thresholds_in_time_order():
    # Thomas (1597 kW) is the lowest threshold, so the fire reaches it first.
    hrr = hrr_history(ALPHA_FAST, SOFA, BEDROOM, T_END)
    t_thomas = time_hrr_reaches(hrr, thomas_flashover_hrr(BEDROOM))
    t_babrauskas = time_hrr_reaches(hrr, babrauskas_flashover_hrr(BEDROOM))
    assert t_thomas < t_babrauskas
