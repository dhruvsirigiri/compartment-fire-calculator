"""Tests for running the whole model at once (fire_model/scenario.py).

These repeat CLAUDE.md check values through run_scenario(), to make sure the
steps are wired together correctly, and check that the summary numbers are
consistent with each other.
"""

import pytest

from fire_model.egress import OCCUPANT_PRESETS, REASON_SMOKE_LOW
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient, time_to_reach
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.scenario import run_scenario

GYPSUM = LININGS["Gypsum board"]
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]
ALPHA_FAST = growth_coefficient(GROWTH_TIMES["fast"])
ALPHA_SLOW = growth_coefficient(GROWTH_TIMES["slow"])

DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
LIVING_ROOM = Room(length=7, width=6, height=2.4, door_width=1.8, door_height=2.1)


@pytest.fixture(scope="module")
def dorm():
    """The prototype's default: dorm room, fast sofa fire, awake with alarm, 600 s."""
    return run_scenario(ALPHA_FAST, FUEL_PEAK_HRR["Sofa"], DORM, GYPSUM, AWAKE, t_end=600)


def test_dorm_check_values(dorm):
    # CLAUDE.md dorm example: Babrauskas 2054, Thomas 1591, Q_vent 4108 kW;
    # MQH flashover 182 s; 1.8 m at 29 s.  RSET (awake with alarm) 63.3 s.
    babrauskas, thomas, mqh = dorm.flashover
    assert babrauskas.threshold_hrr == pytest.approx(2054, abs=0.5)
    assert thomas.threshold_hrr == pytest.approx(1591, abs=0.5)
    assert dorm.ventilation_limit == pytest.approx(4108, abs=0.5)
    assert mqh.time == 182
    assert dorm.time_smoke_at_head_height == 29
    assert dorm.rset == pytest.approx(63.3, abs=0.05)


def test_dorm_verdict_is_consistent(dorm):
    # ASET is set by the smoke reaching 1.8 m, and the margin is ASET - RSET.
    assert dorm.aset == 29
    assert dorm.aset_reason == REASON_SMOKE_LOW
    assert dorm.safety_margin == pytest.approx(dorm.aset - dorm.rset)
    assert dorm.safety_margin < 0  # untenable before the occupant is out

    # The flashover range spans the earliest and latest method.
    times = [m.time for m in dorm.flashover]
    assert dorm.flashover_range == (min(times), max(times))


def test_dorm_series_have_one_value_per_second(dorm):
    assert len(dorm.hrr) == len(dorm.layer_temp) == len(dorm.layer_height) == 601


def test_living_room_has_no_flashover():
    # CLAUDE.md: living room, slow fire, chair 750 kW: no flashover; 1.8 m at 86 s
    result = run_scenario(ALPHA_SLOW, FUEL_PEAK_HRR["Office chair"], LIVING_ROOM, GYPSUM, AWAKE)
    assert result.flashover_range is None
    assert all(m.time is None for m in result.flashover)
    assert result.time_smoke_at_head_height == 86


def test_air_supply_limits_a_large_fire():
    # Concrete storage room (prototype preset) with an ultrafast 5000 kW fire:
    # Q_vent (~4108 kW) is below the fuel's peak, so the air supply caps the fire.
    store = Room(length=5, width=5, height=3, door_width=0.9, door_height=2.1)
    alpha = growth_coefficient(GROWTH_TIMES["ultrafast"])
    result = run_scenario(alpha, 5000, store, LININGS["Concrete"], AWAKE)
    assert result.vent_limited
    assert max(result.hrr) == pytest.approx(result.ventilation_limit)
    assert result.time_to_peak == pytest.approx(time_to_reach(result.ventilation_limit, alpha))


def test_energy_released_matches_the_integral_of_alpha_t_squared():
    # Logic check: while the fire is still growing, the energy released is the
    # integral of alpha t^2 dt = alpha t^3 / 3. Over 100 s (fire still well
    # below its caps) the trapezoid rule should agree to within 0.1%.
    result = run_scenario(ALPHA_FAST, 1e6, DORM, GYPSUM, AWAKE, t_end=100)
    exact_mj = ALPHA_FAST * 100**3 / 3 / 1000
    assert result.energy_released == pytest.approx(exact_mj, rel=1e-3)
