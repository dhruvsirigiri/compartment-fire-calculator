"""Tests for running the whole model at once (fire_model/scenario.py).

These repeat CLAUDE.md check values through run_scenario(), to make sure the
steps are wired together correctly, and check that the summary numbers are
consistent with each other.
"""

import pytest

from fire_model.detection import (
    HEAT_DETECTOR_RTI,
    SPRINKLER_RATING_F,
    SPRINKLER_RTI,
    Device,
    detector_response,
    fahrenheit_to_celsius,
)
from fire_model.egress import OCCUPANT_PRESETS, REASON_SMOKE_LOW
from fire_model.flashover import effective_hrr
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


# ---- Fire protection: sprinklers and heat detectors ----

ORDINARY_C = fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"])
QUICK = Device("Quick response bulb", SPRINKLER_RTI["Quick response bulb"], ORDINARY_C, radial_distance=2.0)
HEAT_DETECTOR = Device("Heat detector", HEAT_DETECTOR_RTI[135.0][30], fahrenheit_to_celsius(135.0), radial_distance=2.0)
SOFA = FUEL_PEAK_HRR["Sofa"]


def test_no_fire_protection_changes_nothing(dorm):
    assert dorm.peak_hrr_used == SOFA
    assert dorm.sprinkler_time is None and dorm.heat_detector_time is None
    assert dorm.alarm_time == AWAKE.detection_time


def test_sprinkler_holds_the_fire_at_its_size_when_it_activates(dorm):
    protected = run_scenario(ALPHA_FAST, SOFA, DORM, GYPSUM, AWAKE, t_end=600, sprinkler=QUICK)
    t_act = protected.sprinkler_time
    assert t_act is not None

    # Activation is found in the unprotected fire (nothing has changed before it).
    expected, _ = detector_response(lambda t: effective_hrr(t, ALPHA_FAST, SOFA, DORM), DORM.height, QUICK, 600)
    assert t_act == expected

    # Before activation the fire is unchanged; afterwards it stays at its size then.
    assert protected.sprinkler_hrr == pytest.approx(effective_hrr(t_act, ALPHA_FAST, SOFA, DORM))
    for t in range(0, int(t_act)):
        assert protected.hrr[t] == pytest.approx(dorm.hrr[t])
    assert all(q == pytest.approx(protected.sprinkler_hrr) for q in protected.hrr[int(t_act) + 1:])
    assert max(protected.hrr) == pytest.approx(protected.sprinkler_hrr)

    # In this room a quick-response sprinkler keeps the fire below every
    # flashover threshold, but the smoke still reaches head height first.
    assert protected.flashover_range is None
    assert protected.aset == dorm.aset == 29


def test_sprinkler_element_heats_up_to_its_rating(dorm):
    protected = run_scenario(ALPHA_FAST, SOFA, DORM, GYPSUM, AWAKE, t_end=600, sprinkler=QUICK)
    temps = protected.sprinkler_temps
    assert len(temps) == 601
    assert temps[int(protected.sprinkler_time) - 1] < ORDINARY_C <= temps[int(protected.sprinkler_time) + 1]


def test_heat_detector_sets_the_alarm_time():
    result = run_scenario(ALPHA_FAST, SOFA, DORM, GYPSUM, AWAKE, t_end=600, heat_detector=HEAT_DETECTOR)
    assert result.alarm_time == result.heat_detector_time
    walking = AWAKE.walk_distance / AWAKE.walk_speed
    assert result.rset == pytest.approx(result.heat_detector_time + AWAKE.reaction_time + walking)
    assert result.heat_detector_time > AWAKE.detection_time  # slower than the smoke alarm preset


def test_heat_detector_that_never_activates_means_no_alarm():
    # A 100 kW wastebasket fire never heats a 196 °F detector 2 m away.
    slow_detector = Device("Heat detector", HEAT_DETECTOR_RTI[196.0][10], fahrenheit_to_celsius(196.0), 2.0)
    result = run_scenario(ALPHA_FAST, FUEL_PEAK_HRR["Wastebasket"], DORM, GYPSUM, AWAKE,
                          t_end=600, heat_detector=slow_detector)
    assert result.heat_detector_time is None
    assert result.rset is None and result.safety_margin is None
