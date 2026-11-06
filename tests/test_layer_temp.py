"""Tests for Step 2: hot gas layer temperature (fire_model/layer_temp.py).

Check values from CLAUDE.md: bedroom 5 x 4 x 2.4 m, door 0.9 x 2.0 m,
fast fire, sofa peak 2500 kW, 16 mm gypsum board.
"""

from dataclasses import replace

import pytest

from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient, t_squared_hrr
from fire_model.layer_temp import (
    LININGS,
    T_AMBIENT,
    is_within_mqh_range,
    mqh_layer_temperature,
    temperature_history,
    thermal_penetration_time,
    wall_heat_transfer_coefficient,
)
from fire_model.room import Room

BEDROOM = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)
GYPSUM = LININGS["Gypsum board"]
CONCRETE = LININGS["Concrete"]
ALPHA_FAST = growth_coefficient(GROWTH_TIMES["fast"])
SOFA = FUEL_PEAK_HRR["Sofa"]


def test_gypsum_thermal_penetration_time():
    # CLAUDE.md: t_p ~ 398 s for 16 mm gypsum board
    assert GYPSUM.thickness == 0.016
    assert thermal_penetration_time(GYPSUM) == pytest.approx(398, abs=0.5)


def test_layer_temperature_at_150_s():
    # CLAUDE.md: T_g at t = 150 s (Q = 1055 kW) ~ 388 °C
    q = t_squared_hrr(150, ALPHA_FAST, SOFA)
    assert mqh_layer_temperature(150, q, BEDROOM, GYPSUM) == pytest.approx(388, abs=0.5)


def test_layer_temperature_at_231_s_is_out_of_mqh_range():
    # CLAUDE.md: at 231 s (Q = 2500 kW) ~ 723 °C, which is above the ~600 °C
    # range MQH was fitted to.
    q = t_squared_hrr(231, ALPHA_FAST, SOFA)
    temperature = mqh_layer_temperature(231, q, BEDROOM, GYPSUM)
    assert temperature == pytest.approx(723, abs=0.5)
    assert not is_within_mqh_range(temperature)


def test_layer_temperature_with_concrete_at_150_s():
    # CLAUDE.md: "With 150 mm concrete at 150 s: ~ 252 °C"
    # t_p for 150 mm concrete is ~6300 s, so at 150 s the wall still acts as a
    # very thick solid: h_k = sqrt(k rho c / t).
    assert CONCRETE.thickness == 0.150
    q = t_squared_hrr(150, ALPHA_FAST, SOFA)
    assert mqh_layer_temperature(150, q, BEDROOM, CONCRETE) == pytest.approx(252, abs=0.5)


def test_thin_concrete_at_150_s_explains_the_old_278_c_value():
    # CLAUDE.md once listed ~278 °C for this case. That is what concrete gives
    # when the thickness is left at gypsum's 16 mm: t_p is then only 72 s, so by
    # 150 s heat flows straight through the wall (h_k = k / delta = 0.1), the
    # wall absorbs less heat and the layer is hotter.
    thin_concrete = replace(CONCRETE, thickness=0.016)
    assert thermal_penetration_time(thin_concrete) == pytest.approx(72, abs=0.5)
    q = t_squared_hrr(150, ALPHA_FAST, SOFA)
    assert mqh_layer_temperature(150, q, BEDROOM, thin_concrete) == pytest.approx(278, abs=0.5)


def test_concrete_room_is_cooler_than_gypsum_room():
    # Physics sanity check: concrete has a much larger k*rho*c (thermal
    # inertia), so its walls absorb more heat and the layer stays cooler.
    q = 1055.0
    assert mqh_layer_temperature(150, q, BEDROOM, CONCRETE) < mqh_layer_temperature(
        150, q, BEDROOM, GYPSUM
    )


def test_h_k_switches_formula_at_penetration_time():
    t_p = thermal_penetration_time(GYPSUM)
    # Before t_p: sqrt(k rho c / t)
    early = wall_heat_transfer_coefficient(100, GYPSUM)
    assert early == pytest.approx((GYPSUM.k * GYPSUM.rho * GYPSUM.c / 100) ** 0.5)
    # After t_p: k / delta
    late = wall_heat_transfer_coefficient(t_p + 1, GYPSUM)
    assert late == pytest.approx(GYPSUM.k / GYPSUM.thickness)


def test_thicker_lining_takes_longer_to_heat_through():
    thick = replace(GYPSUM, thickness=0.032)
    # t_p grows with thickness squared: double the thickness, 4x the time.
    assert thermal_penetration_time(thick) == pytest.approx(4 * thermal_penetration_time(GYPSUM))


def test_room_is_at_ambient_before_ignition():
    assert mqh_layer_temperature(0, 0, BEDROOM, GYPSUM) == T_AMBIENT


def test_temperature_history_lines_up_with_time():
    # One fire size per second, t = 0 ... 150 s
    hrr = [t_squared_hrr(t, ALPHA_FAST, SOFA) for t in range(151)]
    temps = temperature_history(hrr, BEDROOM, GYPSUM)
    assert len(temps) == len(hrr)
    assert temps[0] == T_AMBIENT
    assert temps[150] == pytest.approx(388, abs=0.5)  # same check value as above
