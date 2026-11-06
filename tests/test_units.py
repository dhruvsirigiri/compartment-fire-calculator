"""Tests for the metric / US customary conversions (units.py)."""

import pytest

from units import SYSTEMS, Units

SI = Units(SYSTEMS[0])
US = Units(SYSTEMS[1])

KINDS = ["length", "thickness", "area", "opening_factor", "speed", "hrr", "alpha", "energy",
         "mass_flow", "density", "rti", "temperature_rise", "temperature", "time"]


def test_metric_shows_si_values_unchanged():
    assert SI.show("length", 4.5) == 4.5
    assert SI.to_si("temperature", 20) == 20
    assert SI.unit("hrr") == "kW"


@pytest.mark.parametrize("kind", KINDS)
def test_round_trip_back_to_si(kind):
    for value in (0.0, 1.0, 123.456):
        assert US.to_si(kind, US.show(kind, value)) == pytest.approx(value)


def test_known_conversions():
    assert US.show("length", 1.0) == pytest.approx(3.28084, rel=1e-6)
    assert US.show("temperature", 100) == pytest.approx(212)
    assert US.show("temperature", 20) == pytest.approx(68)
    assert US.show("temperature_rise", 500) == pytest.approx(900)
    assert US.show("thickness", 25.4) == pytest.approx(1.0)
    # The growth classes are defined at 1000 Btu/s = 1055 kW.
    assert US.show("hrr", 1055.05585262) == pytest.approx(1000)
    assert US.show("area", 1.0) == pytest.approx(10.7639, rel=1e-5)
    # Air at 1.2 kg/m³ is about 0.075 lb/ft³.
    assert US.show("density", 1.2) == pytest.approx(0.0749, abs=0.0001)


def test_formatting():
    assert US.fmt("length", 0.3048, 1) == "1.0 ft"
    assert SI.fmt("hrr", 2500) == "2,500 kW"
    assert US.fmt("hrr", None) == "—"


def test_unknown_system_is_rejected():
    with pytest.raises(ValueError):
        Units("imperial-ish")
