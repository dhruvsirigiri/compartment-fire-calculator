"""Tests for the 3D room view (room_view.py).

The view only draws the model's results, so these tests check that what is
drawn matches the numbers: the smoke slab reaches down to the model's layer
height, and the occupant is outside the room once RSET has passed.
"""

import pytest

from fire_model.egress import OCCUPANT_PRESETS
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.scenario import run_scenario
from room_view import MAX_FRAMES, room_3d_figure

COLORS = dict(fire="#C2410C", heat="#B91C1C", air="#1D4ED8", smoke="#4B5563",
              reference="#8A94A6", text="#5A6475", safe="#15803D")
DORM = Room(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1)
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]


@pytest.fixture(scope="module")
def view():
    result = run_scenario(growth_coefficient(GROWTH_TIMES["fast"]), FUEL_PEAK_HRR["Sofa"],
                          DORM, LININGS["Gypsum board"], AWAKE, t_end=600)
    return result, room_3d_figure(result, DORM, AWAKE, COLORS)


def frame(fig, t):
    return next(f for f in fig.frames if f.name == str(t))


def test_frame_count_is_limited(view):
    _, fig = view
    assert len(fig.frames) <= MAX_FRAMES + 1


def test_smoke_slab_reaches_down_to_the_model_layer_height(view):
    result, fig = view
    smoke = frame(fig, 120).data[0]  # traces 4-6 are smoke, fire, occupant
    assert min(smoke.z) == pytest.approx(result.layer_height[120])
    assert max(smoke.z) == pytest.approx(DORM.height)  # slab hangs from the ceiling


def test_no_smoke_drawn_at_ignition(view):
    _, fig = view
    assert frame(fig, 0).data[0].opacity == 0


def test_occupant_is_inside_then_outside(view):
    _, fig = view
    inside = frame(fig, 0).data[2]
    outside = frame(fig, 120).data[2]  # RSET is 63.3 s
    assert max(inside.x) <= DORM.length
    assert min(outside.x) > DORM.length


def test_view_opens_at_the_start_time(view):
    # The title must describe the moment that is drawn first (t = 120 s here),
    # not the last animation frame.
    _, fig = view
    assert fig.layout.title.text.startswith("<b>t = 120 s</b>")
