"""Tests for the 3D room view (room_view.py).

The view only draws the model's results, so these tests check that what is
drawn matches the numbers: the smoke slab reaches down to the model's layer
height, the flames are Heskestad's flame height above the burning surface, the
occupant is outside once RSET has passed, the sprinkler water appears only after
activation, and the labels state the model's values. Coordinates are rounded to
about a millimetre to keep the page small, hence abs=1e-3.
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
from room_view import DRAPER_POINT, FURNITURE, MAX_FRAMES, room_3d_figure, smoke_color
from units import SYSTEMS, Units

COLORS = PALETTES["light"]
SI, US = Units(SYSTEMS[0]), Units(SYSTEMS[1])
DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]
ALPHA = growth_coefficient(GROWTH_TIMES["fast"])
SPRINKLER = Device("Quick response bulb", SPRINKLER_RTI["Quick response bulb"],
                   fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"]), 2.0)
SOFA_SEAT = FURNITURE["Sofa"][1]  # flames start on the seat, 0.45 m up


def run(**devices):
    return run_scenario(ALPHA, FUEL_PEAK_HRR["Sofa"], DORM, LININGS["Gypsum board"], AWAKE, t_end=600, **devices)


@pytest.fixture(scope="module")
def view():
    result = run()
    return result, room_3d_figure(result, DORM, AWAKE, COLORS, SI, start_time=120, fuel="Sofa")


def frame(fig, t):
    return next(f for f in fig.frames if f.name == str(t))


def part(fig, t, name):
    """The trace called `name` in the animation frame for time t."""
    return next(trace for trace in frame(fig, t).data if trace.name == name)


def labels(fig, t):
    """The label texts shown at time t."""
    return [a.text for a in frame(fig, t).layout.scene.annotations]


def test_frame_count_is_limited(view):
    _, fig = view
    assert len(fig.frames) <= MAX_FRAMES + 1


def test_smoke_slab_reaches_down_to_the_model_layer_height(view):
    result, fig = view
    smoke = part(fig, 120, "Smoke layer")
    assert min(smoke.z) == pytest.approx(result.layer_height[120], abs=1e-3)
    assert max(smoke.z) == pytest.approx(DORM.height)  # slab hangs from the ceiling


def test_no_smoke_drawn_at_ignition(view):
    _, fig = view
    assert part(fig, 0, "Smoke layer").opacity == 0


def test_flames_are_heskestads_flame_height_above_the_seat(view):
    # The burning diameter grows with the fire (sqrt of Q / peak), reaching the
    # 1.0 m full-size diameter at the 2500 kW peak. The flames start on the seat.
    result, fig = view
    q = result.hrr[60]
    flames = flame_height(q, burning_diameter(q, 2500, 1.0))
    drawn = part(fig, 60, "Flames")
    assert min(drawn.z) == pytest.approx(SOFA_SEAT, abs=1e-3)
    assert max(drawn.z) == pytest.approx(min(SOFA_SEAT + flames, DORM.height), abs=1e-3)
    assert flames > 1.0  # a 169 kW fire on a 0.26 m patch has tall flames


def test_flames_taller_than_the_room_spread_under_the_ceiling(view):
    result, fig = view
    assert SOFA_SEAT + flame_height(result.hrr[200], 1.0 * (result.hrr[200] / 2500) ** 0.5) > DORM.height
    assert part(fig, 200, "Flames under the ceiling").opacity > 0
    assert part(fig, 60, "Flames under the ceiling").opacity == 0
    assert any("hit the ceiling" in text for text in labels(fig, 200))


def test_occupant_is_inside_then_outside(view):
    _, fig = view
    xs = lambda t: [x for x in part(fig, t, "Occupant").x if x is not None]  # None separates the limbs
    assert max(xs(0)) <= DORM.length
    assert min(xs(120)) > DORM.length  # RSET is 63.3 s


def test_view_opens_at_the_start_time(view):
    # The caption and labels must describe the moment drawn first, not the last frame.
    result, fig = view
    assert fig.layout.title.text.startswith("<b>t = 120 s</b>")
    assert [a.text for a in fig.layout.scene.annotations] == labels(fig, 120)


def test_labels_state_the_model_values(view):
    result, fig = view
    assert f"Hot smoke · {result.layer_temp[120]:.0f} °C" in labels(fig, 120)
    # "Clear air" is labelled while there is room for it under the smoke (over 0.45 m).
    for t in (20, 120, 300):
        assert ("Clear air" in labels(fig, t)) == (result.layer_height[t] > 0.45)
    assert result.layer_height[300] < 0.45
    assert "Smoke out" in labels(fig, 120) and "Door" in labels(fig, 10)  # spills once below the door top


def test_smoke_above_600_C_is_flagged_as_beyond_mqh(view):
    result, fig = view
    assert result.layer_temp[300] > 600
    assert any("beyond MQH's range" in text for text in labels(fig, 300))
    assert not any("beyond" in text for text in labels(fig, 120))


def test_smoke_color_glows_only_above_the_draper_point():
    thick = COLORS["smoke_thick"].lower()
    assert smoke_color(DRAPER_POINT - 5, COLORS) == thick  # hot, dark soot, not yet glowing
    assert smoke_color(DRAPER_POINT + 100, COLORS) != thick
    assert smoke_color(20, COLORS) == COLORS["smoke_thin"].lower()  # cool, thin smoke


def test_sprinkler_water_appears_only_after_activation():
    result = run(sprinkler=SPRINKLER)
    fig = room_3d_figure(result, DORM, AWAKE, COLORS, SI, start_time=0, sprinkler=SPRINKLER)
    before, after = 100, 115  # activation is at 108.5 s
    assert result.sprinkler_time == pytest.approx(108.5)
    assert part(fig, before, "Sprinkler water").marker.opacity == 0
    assert part(fig, after, "Sprinkler water").marker.opacity > 0
    assert "Sprinkler: activated" in labels(fig, after)


def test_us_units_scale_the_room_to_feet():
    result = run()
    fig = room_3d_figure(result, DORM, AWAKE, COLORS, US, start_time=120)
    smoke = part(fig, 120, "Smoke layer")
    assert max(smoke.z) == pytest.approx(DORM.height / 0.3048, abs=1e-3)
    assert "ft" in fig.layout.scene.zaxis.title.text
    assert any(text.endswith("°F") for text in labels(fig, 120))
