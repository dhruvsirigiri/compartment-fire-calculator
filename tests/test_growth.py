"""Tests for Step 1: fire growth (fire_model/growth.py).

Check values come from the "Check values" section of CLAUDE.md. Each tolerance
is half of the last digit written there (e.g. "0.0469" -> +/- 0.00005), so a
test passes when our result rounds to the published number.
"""

import pytest

from fire_model.growth import (
    FUEL_PEAK_HRR,
    GROWTH_TIMES,
    REFERENCE_HRR,
    growth_coefficient,
    t_squared_hrr,
    time_to_reach,
)

ALPHA_FAST = growth_coefficient(GROWTH_TIMES["fast"])
SOFA = FUEL_PEAK_HRR["Sofa"]


def test_fast_growth_coefficient():
    # CLAUDE.md: fast fire, alpha = 0.0469 kW/s^2
    assert ALPHA_FAST == pytest.approx(0.0469, abs=0.00005)


@pytest.mark.parametrize("growth_class", ["slow", "medium", "fast", "ultrafast"])
def test_every_class_reaches_1055_kW_at_its_growth_time(growth_class):
    # This is the definition of the growth classes: Q(t_g) = 1055 kW.
    t_g = GROWTH_TIMES[growth_class]
    alpha = growth_coefficient(t_g)
    assert t_squared_hrr(t_g, alpha, peak_hrr=1e9) == pytest.approx(REFERENCE_HRR)


def test_fast_sofa_fire_is_1055_kW_at_150_s():
    # CLAUDE.md: "T_g at t = 150 s (Q = 1055 kW)"
    assert t_squared_hrr(150, ALPHA_FAST, SOFA) == pytest.approx(1055.0)


def test_fast_sofa_fire_is_capped_at_2500_kW_at_231_s():
    # CLAUDE.md: "At 231 s (Q = 2500 kW)". alpha * 231^2 is just over 2500,
    # so the fire is held at the sofa's peak HRR.
    assert t_squared_hrr(231, ALPHA_FAST, SOFA) == 2500.0


def test_fire_is_zero_at_ignition():
    assert t_squared_hrr(0, ALPHA_FAST, SOFA) == 0.0


def test_time_to_reach_is_the_inverse_of_the_growth_curve():
    t = time_to_reach(SOFA, ALPHA_FAST)
    assert t_squared_hrr(t, ALPHA_FAST, peak_hrr=1e9) == pytest.approx(SOFA)
    # ...and the sofa fire peaks between 230 and 231 s, consistent with the
    # check value above.
    assert 230 < t < 231
