"""Tests for the hand-calculation section (worked_example.py).

The worked example must show the same numbers as the model, so a reader who
redoes it with a calculator gets the app's results.
"""

from fire_model.detection import SPRINKLER_RATING_F, SPRINKLER_RTI, Device, fahrenheit_to_celsius
from fire_model.egress import OCCUPANT_PRESETS
from fire_model.growth import GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.scenario import run_scenario
from worked_example import build_worked_example

BEDROOM = Room(length=5, width=4, height=2.4, door_width=0.9, door_height=2.0)
GYPSUM = LININGS["Gypsum board"]
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]
T_G = GROWTH_TIMES["fast"]


def text_of(sections):
    return " ".join(f"{e} {latex}" for _, lines in sections for e, latex in lines)


def test_bedroom_at_150_s_shows_the_check_values():
    result = run_scenario(growth_coefficient(T_G), 2500, BEDROOM, GYPSUM, AWAKE)
    text = text_of(build_worked_example(150, T_G, 2500, BEDROOM, GYPSUM, AWAKE, result))
    # CLAUDE.md: Q = 1055 kW, opening factor 2.546, A_T 81.4, t_p 398 s, T_g 388 °C,
    # Babrauskas 1909, Thomas 1597, Q_vent 3818 kW, RSET 63.3 s.
    for expected in ["1{,}055.0", "2.546", "81.40", "398", "388.2", "1{,}909", "1{,}597", "3{,}818", "63.3"]:
        assert expected in text, expected


def test_sections_cover_every_step():
    result = run_scenario(growth_coefficient(T_G), 2500, BEDROOM, GYPSUM, AWAKE)
    titles = [title for title, _ in build_worked_example(60, T_G, 2500, BEDROOM, GYPSUM, AWAKE, result)]
    assert [t.split(":")[0] for t in titles] == ["Step 1", "Step 2", "Step 3", "Step 4"]


def test_sprinkler_section_appears_when_installed():
    sprinkler = Device("Quick response bulb", SPRINKLER_RTI["Quick response bulb"],
                       fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"]), 2.0)
    result = run_scenario(growth_coefficient(T_G), 2500, BEDROOM, GYPSUM, AWAKE, sprinkler=sprinkler)
    sections = build_worked_example(90, T_G, 2500, BEDROOM, GYPSUM, AWAKE, result, sprinkler=sprinkler)
    assert sections[-1][0].startswith("Sprinkler")
    # Later than activation, step 1 explains why the fire stopped growing.
    later = text_of(build_worked_example(300, T_G, 2500, BEDROOM, GYPSUM, AWAKE, result, sprinkler=sprinkler))
    assert "sprinkler activated" in later
