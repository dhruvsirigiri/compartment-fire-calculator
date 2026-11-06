"""Tests for Step 4, smoke filling (fire_model/smoke_filling.py).

Check values from CLAUDE.md, 600 s simulation, 16 mm gypsum.
"""

import pytest

from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.smoke_filling import (
    door_outflow,
    gas_density,
    plume_mass_flow,
    smoke_layer_heights,
)
from fire_model.timeline import first_time_at_or_below

T_END = 600  # s
HEAD_HEIGHT = 1.8  # m
GYPSUM = LININGS["Gypsum board"]
ALPHA_FAST = growth_coefficient(GROWTH_TIMES["fast"])
ALPHA_SLOW = growth_coefficient(GROWTH_TIMES["slow"])
SOFA = FUEL_PEAK_HRR["Sofa"]
CHAIR = FUEL_PEAK_HRR["Office chair"]

BEDROOM = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)
DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
LIVING_ROOM = Room(length=7, width=6, height=2.4, door_width=1.8, door_height=2.1)


@pytest.fixture(scope="module")
def bedroom_z():
    """Bedroom, fast sofa fire: layer height at every second (computed once)."""
    return smoke_layer_heights(ALPHA_FAST, SOFA, BEDROOM, GYPSUM, T_END)


# ---- Bedroom ----

def test_bedroom_smoke_reaches_head_height_at_29_s(bedroom_z):
    # CLAUDE.md: smoke layer reaches 1.8 m at 29 s
    assert first_time_at_or_below(bedroom_z, HEAD_HEIGHT) == 29


@pytest.mark.parametrize("t, expected", [(60, 1.22), (120, 0.88), (300, 0.10)])
def test_bedroom_layer_height_over_time(bedroom_z, t, expected):
    # CLAUDE.md: z at 60 / 120 / 300 s ~ 1.22 / 0.88 / 0.10 m
    assert bedroom_z[t] == pytest.approx(expected, abs=0.005)


def test_one_height_per_second(bedroom_z):
    assert len(bedroom_z) == T_END + 1
    assert bedroom_z[0] == BEDROOM.height  # no smoke at ignition


# ---- Dorm example ----

def test_dorm_smoke_reaches_head_height_at_29_s():
    # CLAUDE.md: dorm example, 1.8 m at 29 s
    z = smoke_layer_heights(ALPHA_FAST, SOFA, DORM, GYPSUM, T_END)
    assert first_time_at_or_below(z, HEAD_HEIGHT) == 29


# ---- Living room ----

def test_living_room_slow_chair_fire():
    # CLAUDE.md: 1.8 m at 86 s; z at 600 s ~ 1.25 m
    z = smoke_layer_heights(ALPHA_SLOW, CHAIR, LIVING_ROOM, GYPSUM, T_END)
    assert first_time_at_or_below(z, HEAD_HEIGHT) == 86
    assert z[600] == pytest.approx(1.25, abs=0.005)


# ---- The pieces on their own ----

def test_gas_density_of_ambient_air():
    # 353 / 293.15 K ~ 1.20 kg/m^3, the familiar density of room-temperature air
    assert gas_density(293.15) == pytest.approx(1.20, abs=0.005)


def test_plume_carries_more_mass_when_it_rises_further():
    assert plume_mass_flow(1000, 2.0) > plume_mass_flow(1000, 1.0)
    assert plume_mass_flow(0, 2.0) == 0.0  # no fire, no plume


def test_no_door_outflow_until_smoke_is_below_the_door_top():
    assert door_outflow(BEDROOM, z=2.1, layer_temp_k=600) == 0.0  # above door top
    assert door_outflow(BEDROOM, z=1.5, layer_temp_k=600) > 0.0  # below door top
