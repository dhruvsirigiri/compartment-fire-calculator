"""Tests for the Streamlit app (app.py).

Streamlit's AppTest runs the app without a browser, lets the test change
inputs, and reads back what the page shows. These tests check that the page
displays the model's results (including CLAUDE.md check values), that presets
fill in the inputs, that impossible rooms are caught, and that the app explains
the user's changes: "What your last change did", the "Try this" buttons, Undo
and moving between the step tabs.

Only the open tab is drawn, so a test opens a tab (open_tab) before reading
what is on it.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import guide

# app.py is in the project folder, one level up from this tests/ folder.
APP = str(Path(__file__).resolve().parent.parent / "app.py")
CHANGE_PANEL = "What your last change did"


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def open_tab(at, name):
    at.session_state["page"] = name
    at.run()
    assert not at.exception, at.exception
    return at


def metric(at, label_start):
    """The displayed value of the first metric whose label starts with label_start."""
    for m in at.metric:
        if m.label.startswith(label_start):
            return m.value
    raise AssertionError(f"No metric starting with {label_start!r}")


def button(at, label):
    """The button with this label."""
    return next(b for b in at.button if b.label == label)


def page_text(at):
    return " ".join(m.value for m in at.markdown)


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
    assert metric(open_tab(app, guide.TAB_FIRE), "Growth coefficient") == "0.0469 kW/s²"
    open_tab(app, guide.TAB_FLASHOVER)
    assert metric(app, "Air supply limit") == "4,108 kW"
    assert metric(app, "Babrauskas threshold") == "2,054 kW" and metric(app, "Thomas threshold") == "1,591 kW"
    assert metric(open_tab(app, guide.TAB_ESCAPE), "Smoke reaches 1.8 m") == "29 s"


def test_living_room_slow_chair_has_no_flashover(app):
    # CLAUDE.md: living room, slow fire, chair 750 kW: no flashover; 1.8 m at 86 s.
    app.selectbox(key="room_preset").set_value("Living room, wide opening")
    app.radio(key="growth").set_value("slow")
    app.selectbox(key="fuel").set_value("Office chair")
    app.run()
    assert not app.exception
    assert app.session_state.peak_hrr == 750  # the fuel preset set the peak HRR
    assert metric(app, "Flashover") == "None"
    assert metric(app, "Room untenable") == "86 s"
    assert any("get out with 23 s to spare" in box.value for box in app.success)
    assert metric(open_tab(app, guide.TAB_ESCAPE), "Smoke reaches 1.8 m") == "86 s"


def test_bedroom_preset_fills_in_the_room(app):
    app.selectbox(key="room_preset").set_value("Bedroom").run()
    s = app.session_state
    assert (s.length, s.width, s.height, s.door_width, s.door_height) == (5.0, 4.0, 2.4, 0.9, 2.0)
    assert metric(open_tab(app, guide.TAB_HEAT), "Opening factor") == "2.55 m⁵ᐟ²"  # check value 2.546


def test_concrete_preset_sets_lining_and_thickness(app):
    app.selectbox(key="room_preset").set_value("Concrete storage room").run()
    assert app.session_state.lining == "Concrete"
    assert app.session_state.thickness == 150


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


def test_each_tab_draws_its_charts(app):
    charts_per_tab = {guide.TAB_OVERVIEW: 0, guide.TAB_FIRE: 1, guide.TAB_HEAT: 1, guide.TAB_FLASHOVER: 1,
                      guide.TAB_ESCAPE: 1, guide.TAB_3D: 1}  # only the open tab is drawn
    for tab, count in charts_per_tab.items():
        assert len(open_tab(app, tab).get("plotly_chart")) == count, tab


def test_every_tab_shows_without_errors(app):
    app.selectbox(key="sprinkler_type").set_value("Quick response bulb").run()
    app.checkbox(key="use_heat_detector").check().run()
    for tab in guide.TABS:
        open_tab(app, tab)


# ---- Explaining changes ----

def test_no_change_panel_before_any_change(app):
    assert CHANGE_PANEL not in page_text(app)


def test_change_panel_explains_a_wider_door(app):
    app.number_input(key="door_width").set_value(1.8).run()
    text = page_text(app)
    assert f"{CHANGE_PANEL}** · Door width: 0.9 m → 1.8 m" in text
    assert "| Flashover | 182–210 s | 211 s |" in text  # a later flashover is better
    assert "opening factor went from 2.74 m⁵ᐟ² to 5.48 m⁵ᐟ²" in text


def test_undo_restores_the_inputs(app):
    app.number_input(key="door_width").set_value(1.8).run()
    button(app, "Undo this change").click().run()
    assert app.session_state.door_width == pytest.approx(0.9)
    assert app.session_state.room_preset == "Dorm room (example)"
    assert metric(app, "Flashover").startswith("182–")
    assert CHANGE_PANEL not in page_text(app)  # the undo itself is not explained as a new change
    app.number_input(key="length").set_value(6.0).run()  # the next change is explained as usual
    assert f"{CHANGE_PANEL}** · Room length: 4.5 m → 6.0 m" in page_text(app)


def test_try_this_button_changes_one_input(app):
    open_tab(app, guide.TAB_FLASHOVER)
    button(app, "Add a quick-response sprinkler").click().run()
    assert app.session_state.sprinkler_type == "Quick response bulb"
    assert metric(app, "Flashover") == "None"
    assert f"{CHANGE_PANEL}** · Sprinkler: none → Quick response bulb" in page_text(app)


def test_lining_try_this_is_explained_as_a_lining_change(app):
    open_tab(app, guide.TAB_HEAT)
    button(app, "Line the room with concrete").click().run()
    assert app.session_state.thickness == 150 and app.session_state.room_preset == "Custom"
    assert "Wall lining: Gypsum board → Concrete" in page_text(app)


def test_switching_units_is_not_a_change(app):
    app.radio(key="units").set_value("US customary").run()
    assert CHANGE_PANEL not in page_text(app)


def test_next_button_opens_the_next_step(app):
    open_tab(app, guide.TAB_FIRE)
    button(app, f"Next: {guide.TAB_HEAT}").click().run()
    assert app.session_state.page == guide.TAB_HEAT
    assert "Step 2 · How hot does the smoke get?" in [h.value for h in app.subheader]


def test_key_moment_opens_the_3d_view_at_that_time(app):
    next(b for b in app.button if b.key == "see_flashover").click().run()
    assert app.session_state.page == guide.TAB_3D
    assert app.session_state.moment_t == 182
    assert any(m.value.startswith("**At 182 s**") for m in app.markdown)


def test_3d_view_opens_when_the_room_becomes_untenable(app):
    open_tab(app, guide.TAB_3D)
    assert app.session_state.moment_key == "untenable" and app.session_state.moment_t == 29


def test_start_over_resets_the_inputs(app):
    app.number_input(key="length").set_value(6.0).run()
    button(app, "Start over with the example").click().run()
    assert app.session_state.length == 4.5 and app.session_state.room_preset == "Dorm room (example)"


def test_sidebar_notes_state_the_results(app):
    notes = " ".join(c.value for c in app.sidebar.caption)
    assert "peaks at 2,500 kW at 231 s" in notes and "= 63 s" in notes


# ---- Unit switch ----

def test_switching_to_us_units_converts_inputs_but_not_results(app):
    before = [m.value for m in app.metric[:4]]
    app.radio(key="units").set_value("US customary").run()
    assert not app.exception
    s = app.session_state
    assert s.length == pytest.approx(4.5 / 0.3048)  # 14.76 ft
    assert s.thickness == pytest.approx(16 / 25.4)  # 0.63 in
    assert s.peak_hrr == pytest.approx(2500 / 1.05505585262)  # 2,370 Btu/s
    assert [m.value for m in app.metric[:4]] == before  # the verdict is the same fire
    assert metric(open_tab(app, guide.TAB_FLASHOVER), "Air supply limit") == "3,894 Btu/s"  # 4,108 kW
    assert metric(open_tab(app, guide.TAB_ESCAPE), "Smoke reaches 5.9 ft") == "29 s"  # 1.8 m = 5.9 ft

    app.radio(key="units").set_value("Metric (SI)").run()
    assert app.session_state.length == pytest.approx(4.5)


def test_menu_labels_do_not_change_with_the_units(app):
    # Streamlit remembers a menu's choice by its label. If a label changed with the
    # unit switch (say "Sofa (≈2,500 kW)" to "Sofa (≈2,370 Btu/s)"), the browser would
    # send back the old label on the next click and the app would no longer
    # recognize the choice (this crashed the app once).
    app.selectbox(key="sprinkler_type").set_value("Quick response bulb").run()
    app.checkbox(key="use_heat_detector").check().run()

    def labels():
        return {w.key: list(w.options) for w in list(app.selectbox) + list(app.radio) if w.key != "units"}

    metric_labels = labels()
    app.radio(key="units").set_value("US customary").run()
    assert labels() == metric_labels


def test_presets_fill_in_us_values(app):
    app.radio(key="units").set_value("US customary").run()
    app.selectbox(key="room_preset").set_value("Bedroom").run()
    assert not app.exception
    assert app.session_state.length == pytest.approx(5 / 0.3048)
    assert app.session_state.door_height == pytest.approx(2.0 / 0.3048)
    # Same bedroom as in metric units, so the same check value: 1.8 m at 29 s.
    assert metric(open_tab(app, guide.TAB_ESCAPE), "Smoke reaches 5.9 ft") == "29 s"


# ---- Fire protection ----

def test_sprinkler_shows_activation_and_prevents_flashover(app):
    app.selectbox(key="sprinkler_type").set_value("Quick response bulb").run()
    assert not app.exception
    assert metric(app, "Flashover") == "None"
    open_tab(app, guide.TAB_PROTECTION)
    assert metric(app, "Sprinkler activates") == "109 s"  # 108.5 s, ordinary rating, 2 m away
    assert metric(app, "Flashover without") == "182–210 s → none"


def test_heat_detector_sets_the_alarm(app):
    app.checkbox(key="use_heat_detector").check().run()
    assert not app.exception
    assert app.number_input(key="detection").disabled
    assert metric(app, "Everyone is out") == "149 s"  # 115.5 + 30 + 4/1.2
    assert metric(open_tab(app, guide.TAB_PROTECTION), "Heat detector alarm") == "116 s"  # 115.5 s


# ---- Proof sections ----

def test_hand_calculation_and_validation_sections_are_shown(app):
    open_tab(app, guide.TAB_MATH)
    assert len(app.tabs) >= 4 + len(guide.TABS)  # the page's tabs, plus Step 1-4 hand calculations
    open_tab(app, guide.TAB_ABOUT)
    assert "comparisons agree" in page_text(app)
    assert "Is this calculator realistic" in " ".join(h.value for h in app.subheader)
