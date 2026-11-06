"""Tests for the 3D room view (room_view.py).

The view only draws the model's results, so these tests check that what is
drawn matches the numbers: the smoke slab reaches down to the model's layer
height, the flames are Heskestad's flame height, the occupant is outside once
RSET has passed, and the sprinkler spray appears only after activation.
"""

import pytest

from charts import PALETTES
from fire_model.detection import SPRINKLER_RATING_F, SPRINKLER_RTI, Device, fahrenheit_to_celsius
from fire_model.egress import OCCUPANT_PRESETS
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, burning_diameter, growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.scenario import run_scenario
from fire_model.smoke_filling import flame_height
from room_view import MAX_FRAMES, room_3d_figure
from units import SYSTEMS, Units

COLORS = PALETTES["light"]
SI, US = Units(SYSTEMS[0]), Units(SYSTEMS[1])
DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]
ALPHA = growth_coefficient(GROWTH_TIMES["fast"])
SPRINKLER = Device("Quick response bulb", SPRINKLER_RTI["Quick response bulb"],
                   fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"]), 2.0)


def run(**devices):
    return run_scenario(ALPHA, FUEL_PEAK_HRR["Sofa"], DORM, LININGS["Gypsum board"], AWAKE, t_end=600, **devices)


@pytest.fixture(scope="module")
def view():
    result = run()
    return result, room_3d_figure(result, DORM, AWAKE, COLORS, SI, start_time=120)


def part(fig, t, name):
    """The trace called `name` in the animation frame for time t."""
    frame = next(f for f in fig.frames if f.name == str(t))
    return next(trace for trace in frame.data if trace.name == name)


def test_frame_count_is_limited(view):
    _, fig = view
    assert len(fig.frames) <= MAX_FRAMES + 1


def test_smoke_slab_reaches_down_to_the_model_layer_height(view):
    result, fig = view
    smoke = part(fig, 120, "Smoke layer")
    assert min(smoke.z) == pytest.approx(result.layer_height[120])
    assert max(smoke.z) == pytest.approx(DORM.height)  # slab hangs from the ceiling


def test_no_smoke_drawn_at_ignition(view):
    _, fig = view
    assert part(fig, 0, "Smoke layer").opacity == 0


def test_flames_are_heskestads_flame_height(view):
    # The burning diameter grows with the fire (sqrt of Q / peak), reaching the
    # 1.0 m full-size diameter at the 2500 kW peak.
    result, fig = view
    q = result.hrr[60]
    expected = min(flame_height(q, burning_diameter(q, 2500, 1.0)), DORM.height)
    assert max(part(fig, 60, "Flames").z) == pytest.approx(expected)
    assert expected > 1.0  # a 169 kW fire on a 0.26 m patch has tall flames


def test_occupant_is_inside_then_outside(view):
    _, fig = view
    assert max(part(fig, 0, "Occupant").x) <= DORM.length
    assert min(part(fig, 120, "Occupant").x) > DORM.length  # RSET is 63.3 s


def test_view_opens_at_the_start_time(view):
    # The caption must describe the moment drawn first, not the last frame.
    _, fig = view
    assert fig.layout.title.text.startswith("<b>t = 120 s</b>")


def test_sprinkler_spray_appears_only_after_activation():
    result = run(sprinkler=SPRINKLER)
    fig = room_3d_figure(result, DORM, AWAKE, COLORS, SI, start_time=0, sprinkler=SPRINKLER)
    before, after = 100, 115  # activation is at 108.5 s
    assert result.sprinkler_time == pytest.approx(108.5)
    assert part(fig, before, "Sprinkler spray").opacity == 0
    assert part(fig, after, "Sprinkler spray").opacity > 0


def test_us_units_scale_the_room_to_feet():
    result = run()
    fig = room_3d_figure(result, DORM, AWAKE, COLORS, US, start_time=120)
    smoke = part(fig, 120, "Smoke layer")
    assert max(smoke.z) == pytest.approx(DORM.height / 0.3048)
    assert "ft" in fig.layout.scene.zaxis.title.text
