"""Tests for sprinkler and heat detector activation (fire_model/detection.py).

The NRC worked examples are checked in test_nureg1805.py. These tests cover the
behaviour around them: which branch of Alpert's correlation is used, no fire,
a device that never activates, and growing fires.
"""

import pytest

from fire_model.detection import (
    HEAT_DETECTOR_RTI,
    SPRINKLER_RATING_F,
    SPRINKLER_RTI,
    Device,
    activation_time_steady,
    ceiling_jet_temperature_rise,
    ceiling_jet_velocity,
    detector_response,
    fahrenheit_to_celsius,
)
from fire_model.growth import growth_coefficient
from fire_model.smoke_filling import flame_height

QUICK = Device("Quick response bulb", rti=SPRINKLER_RTI["Quick response bulb"],
               activation_temp=fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"]), radial_distance=2.0)


def test_fahrenheit_conversion():
    assert fahrenheit_to_celsius(212) == pytest.approx(100)
    assert fahrenheit_to_celsius(165) == pytest.approx(73.89, abs=0.01)


def test_alpert_switches_branch_at_r_over_h():
    # Directly above the fire (r/H <= 0.18 for temperature, 0.15 for velocity)
    # the result does not depend on r.
    assert ceiling_jet_temperature_rise(500, 3.0, 0.1) == ceiling_jet_temperature_rise(500, 3.0, 0.5)
    assert ceiling_jet_velocity(500, 3.0, 0.1) == ceiling_jet_velocity(500, 3.0, 0.4)
    # Further out, the jet is cooler and slower the further you go.
    assert ceiling_jet_temperature_rise(500, 3.0, 4.0) < ceiling_jet_temperature_rise(500, 3.0, 2.0)
    assert ceiling_jet_velocity(500, 3.0, 4.0) < ceiling_jet_velocity(500, 3.0, 2.0)


def test_no_fire_no_ceiling_jet():
    assert ceiling_jet_temperature_rise(0, 3.0, 2.0) == 0
    assert ceiling_jet_velocity(0, 3.0, 2.0) == 0


def test_small_fire_never_activates_a_sprinkler():
    # A 20 kW fire under a 3 m ceiling never heats the jet to 74 °C.
    assert activation_time_steady(20, 3.0, QUICK) is None
    activation, temps = detector_response(lambda t: 20.0, 3.0, QUICK, t_end=600)
    assert activation is None
    assert len(temps) == 601 and max(temps) < QUICK.activation_temp


def test_time_stepping_matches_the_exact_steady_formula():
    exact = activation_time_steady(800, 2.6, QUICK)
    stepped, _ = detector_response(lambda t: 800.0, 2.6, QUICK, t_end=600)
    assert stepped == pytest.approx(exact, rel=0.01)


def test_quick_response_beats_standard_response_in_a_growing_fire():
    alpha = growth_coefficient(150)  # fast t-squared fire
    standard = Device("Standard response bulb", rti=SPRINKLER_RTI["Standard response bulb"],
                      activation_temp=QUICK.activation_temp, radial_distance=2.0)
    t_quick, _ = detector_response(lambda t: alpha * t**2, 2.6, QUICK, t_end=600)
    t_standard, _ = detector_response(lambda t: alpha * t**2, 2.6, standard, t_end=600)
    assert t_quick < t_standard


def test_heat_detector_table_matches_the_source_pattern():
    # A guard against typing mistakes when copying the NFPA 72 table: within each
    # rating, RTI falls as the UL listed spacing grows (a detector listed for wider
    # spacing must respond faster). The source table has one exception, kept as
    # published: 128 °F goes from 306 at 15 ft to 325 at 20 ft.
    for rating, by_spacing in HEAT_DETECTOR_RTI.items():
        spacings = sorted(by_spacing)
        for smaller, larger in zip(spacings, spacings[1:]):
            if (rating, smaller) == (128.0, 15):
                assert by_spacing[larger] == 325 and by_spacing[smaller] == 306
                continue
            assert by_spacing[larger] < by_spacing[smaller], (rating, smaller, larger)
    assert HEAT_DETECTOR_RTI[135.0][30] == 98


def test_flame_height_is_never_negative():
    assert flame_height(10, 2.0) == 0.0  # small fire, wide area
    assert flame_height(0, 1.0) == 0.0
    assert flame_height(1055, 1.0) > 0
