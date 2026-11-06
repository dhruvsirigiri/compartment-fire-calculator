"""Tests for the Streamlit app (app.py).

Streamlit's AppTest runs the app without a browser, lets the test change
inputs, and reads back what the page shows. These tests check that the page
displays the model's results (including CLAUDE.md check values), that presets
fill in the inputs, and that impossible rooms are caught.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# app.py is in the project folder, one level up from this tests/ folder.
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def metric(at, label_start):
    """The displayed value of the first metric whose label starts with label_start."""
    for m in at.metric:
        if m.label.startswith(label_start):
            return m.value
    raise AssertionError(f"No metric starting with {label_start!r}")


@pytest.fixture
def app():
    return run_app()


def test_learning_tool_statement_is_visible(app):
    assert any("learning tool, not a design tool" in box.value for box in app.info)


def test_default_dorm_verdict(app):
    # Default: dorm room, fast sofa fire, awake with alarm (prototype defaults).
    # CLAUDE.md: MQH flashover 182 s (the earliest method here); 1.8 m at 29 s;
    # RSET 63.3 s.
    assert metric(app, "Flashover").startswith("182–")
    assert metric(app, "Room untenable") == "29 s"
    assert metric(app, "Everyone is out") == "63 s"
    assert metric(app, "Safety margin") == "−34 s"  # 29 - 63.3
    assert any("untenable 34 s before" in box.value for box in app.error)


def test_dorm_readouts_match_check_values(app):
    assert metric(app, "Air supply limit") == "4,108 kW"
    assert metric(app, "Growth coefficient") == "0.0469 kW/s²"
    assert metric(app, "Smoke reaches 1.8 m") == "29 s"


def test_living_room_slow_chair_has_no_flashover(app):
    # CLAUDE.md: living room, slow fire, chair 750 kW: no flashover; 1.8 m at 86 s.
    app.selectbox(key="room_preset").set_value("Living room, wide opening")
    app.radio(key="growth").set_value("slow")
    app.selectbox(key="fuel").set_value("Office chair")
    app.run()
    assert not app.exception
    assert app.session_state.peak_hrr == 750  # the fuel preset set the peak HRR
    assert metric(app, "Flashover") == "None"
    assert metric(app, "Smoke reaches 1.8 m") == "86 s"
    assert metric(app, "Room untenable") == "86 s"
    assert any("get out with 23 s to spare" in box.value for box in app.success)


def test_bedroom_preset_fills_in_the_room(app):
    app.selectbox(key="room_preset").set_value("Bedroom").run()
    s = app.session_state
    assert (s.length, s.width, s.height, s.door_width, s.door_height) == (5.0, 4.0, 2.4, 0.9, 2.0)
    assert metric(app, "Opening factor") == "2.55 m⁵ᐟ²"  # check value 2.546


def test_concrete_preset_sets_lining_and_thickness(app):
    app.selectbox(key="room_preset").set_value("Concrete storage room").run()
    assert app.session_state.lining == "Concrete"
    assert app.session_state.thickness_mm == 150


def test_editing_a_dimension_switches_room_to_custom(app):
    app.number_input(key="length").set_value(6.0).run()
    assert app.session_state.room_preset == "Custom"


def test_door_taller_than_ceiling_is_caught(app):
    app.number_input(key="door_height").set_value(3.0).run()  # dorm ceiling is 2.6 m
    assert not app.exception
    assert any("taller than the ceiling" in box.value for box in app.error)
    assert len(app.metric) == 0  # no results shown for an impossible room


def test_occupant_preset_changes_rset(app):
    app.selectbox(key="occupant_preset").set_value("Asleep, smoke alarm in room").run()
    assert metric(app, "Everyone is out") == "154 s"  # 30 + 120 + 4 / 1.0


def test_all_four_charts_are_drawn(app):
    # 3D room view + heat release rate + temperature + smoke layer height
    assert len(app.get("plotly_chart")) == 4
