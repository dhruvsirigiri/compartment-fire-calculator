"""Tests for the plain-language explanations (guide.py).

The explanations must state the model's own numbers (here for the dorm
scenario, whose values are checked elsewhere against CLAUDE.md and the
prototype) and judge "better" and "worse" the right way round.
"""

import pytest

import guide
from fire_model.detection import SPRINKLER_RATING_F, SPRINKLER_RTI, Device, fahrenheit_to_celsius
from fire_model.egress import OCCUPANT_PRESETS
from fire_model.growth import growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.room import Room
from fire_model.scenario import run_scenario
from units import SYSTEMS, Units

SI, US = Units(SYSTEMS[0]), Units(SYSTEMS[1])
DORM = Room(4.5, 3.5, 2.6, 0.9, 2.1)
WIDE_DOOR = Room(4.5, 3.5, 2.6, 1.8, 2.1)
GYPSUM, CONCRETE = LININGS["Gypsum board"], LININGS["Concrete"]
AWAKE = OCCUPANT_PRESETS["Awake, smoke alarm in room"]
FAST = growth_coefficient(150)
SPRINKLER = Device("Quick response bulb", SPRINKLER_RTI["Quick response bulb"],
                   fahrenheit_to_celsius(SPRINKLER_RATING_F["Ordinary"]), 2.0)
# Every input, in SI, as the app passes them (the dorm example).
INPUTS = dict(growth="fast", fuel="Sofa", peak_hrr=2500.0, fire_diameter=1.0, t_end=600,
              room_preset="Dorm room (example)", length=4.5, width=3.5, height=2.6, door_width=0.9,
              door_height=2.1, lining="Gypsum board", thickness=16.0, sprinkler_type="None",
              sprinkler_rating="Ordinary", sprinkler_distance=2.0, use_heat_detector=False,
              detector_rating=135.0, detector_spacing=30, detector_distance=2.0,
              occupant_preset="Awake, smoke alarm in room", detection=30.0, reaction=30.0, distance=4.0, speed=1.2)


@pytest.fixture(scope="module")
def dorm():
    return run_scenario(FAST, 2500, DORM, GYPSUM, AWAKE, 600)


def joined(paragraphs):
    return " ".join(paragraphs)


def fmt(key, value):
    return f"{value:g}" if isinstance(value, float) else str(value)


def test_inputs_are_every_input_the_app_explains():
    assert set(INPUTS) == set(guide.INPUT_LABELS)


def test_fire_step_states_the_growth_and_peak(dorm):
    text = joined(guide.explain_fire("fast", 2500, DORM, dorm, SI))
    assert "grows fast" in text and "upholstered furniture or stacked boxes" in text
    assert "1,055 kW" in text and "150 s" in text  # reaches 1055 kW at t_g
    assert "2,500 kW" in text and "231 s" in text  # peak and when
    assert "an ultrafast fire would take 115 s" in text  # grammar and the comparison


def test_fire_step_follows_the_unit_switch(dorm):
    text = joined(guide.explain_fire("fast", 2500, DORM, dorm, US))
    assert "Btu/s" in text and " kW" not in text


def test_heat_step_explains_the_temperature(dorm):
    text = joined(guide.explain_heat(DORM, GYPSUM, dorm, SI, ("Concrete", CONCRETE)))
    assert "200 °C at 92 s" in text
    assert "k·ρ·c = 0.18, so it is insulating" in text
    assert "concrete walls instead" in text
    assert "t_p = 398 s" in text  # the step up after heat soaks through the gypsum


def test_flashover_step(dorm):
    text = joined(guide.explain_flashover(DORM, dorm, SI))
    assert "1,553–2,054 kW" in text
    assert "all 3 thresholds" in text and "the first (MQH) at 182 s" in text


def test_escape_step(dorm):
    text = joined(guide.explain_escape(DORM, AWAKE, dorm, SI, heat_detector_used=False))
    assert "untenable at 29 s" in text and "Escape takes 63 s" in text
    assert "waiting for the alarm and reacting" in text  # 60 of the 63 s


def test_protection_step_with_a_sprinkler(dorm):
    protected = run_scenario(FAST, 2500, DORM, GYPSUM, AWAKE, 600, sprinkler=SPRINKLER)
    text = joined(guide.explain_protection(DORM, protected, dorm, SPRINKLER, None, AWAKE, SI))
    assert "activates at 109 s" in text and "552 kW" in text
    assert "182–210 s → none" in text
    assert "already untenable when it activates" in text


def test_key_moments_in_time_order(dorm):
    moments = guide.key_moments(dorm, AWAKE, False, SI)
    times = {m.key: m.time for m in moments}
    assert times["start"] == 0 and times["untenable"] == 29 and times["alarm"] == 30
    assert times["out"] == 63 and times["flashover"] == 182 and times["end"] == 600
    assert [m.time for m in moments] == sorted(m.time for m in moments)


def test_key_moment_labels_follow_units(dorm):
    labels = [m.label for m in guide.key_moments(dorm, AWAKE, False, US)]
    assert "Smoke at 392 °F" in labels


def test_moment_descriptions(dorm):
    early = joined(guide.describe_moment(29, dorm, DORM, AWAKE, 2500, 1.0, SI))
    assert "At 29 s" in early and "head height" in early and "alarm has not sounded" in early
    late = joined(guide.describe_moment(250, dorm, DORM, AWAKE, 2500, 1.0, SI))
    assert "fills the whole room" in late and "glowing red" in late and "out of the room" in late


def test_describe_change_door_width(dorm):
    wider = run_scenario(FAST, 2500, WIDE_DOOR, GYPSUM, AWAKE, 600)
    change = guide.describe_change(INPUTS, dict(INPUTS, door_width=1.8), guide.summarize(dorm),
                                   guide.summarize(wider), SI, fmt)
    assert change.headline == "Door width: 0.9 → 1.8"
    assert change.step == guide.TAB_FLASHOVER
    effects = {name: (before, after, verdict) for name, before, after, verdict in change.effects}
    assert effects["Flashover"] == ("182–210 s", "211 s", "better")
    assert effects["Hottest smoke"][2] == "better"
    assert "opening factor went from 2.74 m⁵ᐟ² to 5.48 m⁵ᐟ²" in change.reasons[0]


def test_describe_change_uses_the_preset_as_the_explanation(dorm):
    bedroom = dict(INPUTS, room_preset="Bedroom", length=5.0, width=4.0, height=2.4, door_height=2.0)
    result = run_scenario(FAST, 2500, Room(5, 4, 2.4, 0.9, 2.0), GYPSUM, AWAKE, 600)
    change = guide.describe_change(INPUTS, bedroom, guide.summarize(dorm), guide.summarize(result), SI, fmt)
    assert change.headline.startswith("Room type: Dorm room (example) → Bedroom")
    assert change.reasons[0].startswith("**Room type.**")
    assert len(change.inputs) == 5  # preset, length, width, height, door height


def test_slower_escape_is_worse(dorm):
    slow = run_scenario(FAST, 2500, DORM, GYPSUM, OCCUPANT_PRESETS["Needs help to move"], 600)
    change = guide.describe_change(INPUTS, dict(INPUTS, reaction=90.0, speed=0.5), guide.summarize(dorm),
                                   guide.summarize(slow), SI, fmt)
    effects = {name: verdict for name, _, _, verdict in change.effects}
    assert effects["Everyone out (RSET)"] == "worse" and effects["Safety margin"] == "worse"


def test_no_change_gives_no_explanation(dorm):
    assert guide.describe_change(INPUTS, dict(INPUTS), guide.summarize(dorm), guide.summarize(dorm), SI, fmt) is None


def test_a_preset_switched_to_custom_is_not_the_cause(dorm):
    # Lining the room with concrete also sets the thickness and switches the room
    # type to Custom: the explanation must be about the lining.
    concrete = dict(INPUTS, lining="Concrete", thickness=150.0, room_preset="Custom")
    result = run_scenario(FAST, 2500, DORM, CONCRETE, AWAKE, 600)
    change = guide.describe_change(INPUTS, concrete, guide.summarize(dorm), guide.summarize(result), SI, fmt)
    assert change.headline == "Wall lining: Gypsum board → Concrete"  # the rest follows from the lining
    assert len(change.inputs) == 3  # lining, thickness, room type
    assert change.reasons[0].startswith("**Wall lining.**")
    assert change.step == guide.TAB_HEAT
    effects = {name: verdict for name, _, _, verdict in change.effects}
    assert effects["Hottest smoke"] == "better"


def test_try_this_offers_one_change_at_a_time():
    for step in (guide.TAB_FIRE, guide.TAB_HEAT, guide.TAB_FLASHOVER, guide.TAB_ESCAPE, guide.TAB_PROTECTION):
        suggestions = guide.try_this(step, INPUTS, SI)
        assert suggestions, step
        assert all(len(changes) == 1 for _, changes in suggestions)
    labels = [label for label, _ in guide.try_this(guide.TAB_FLASHOVER, INPUTS, SI)]
    assert "Make the door twice as wide" in labels and "Add a quick-response sprinkler" in labels


def test_try_this_never_offers_an_impossible_room():
    # A 1.8 m door in a 1.9 m wide, 1.0 m long room cannot be doubled.
    narrow = dict(INPUTS, length=1.0, width=1.9, door_width=1.8)
    labels = [label for label, _ in guide.try_this(guide.TAB_FLASHOVER, narrow, SI)]
    assert "Make the door twice as wide" not in labels and "Make the door half as wide" in labels


def test_try_this_labels_follow_units():
    labels = [label for label, _ in guide.try_this(guide.TAB_ESCAPE, INPUTS, US)]
    assert "Raise the ceiling by 3.3 ft" in labels


def test_sidebar_notes(dorm):
    notes = guide.sidebar_notes(dorm, AWAKE, SI)
    assert "peaks at 2,500 kW at 231 s" in notes["fire"] and "1,553–2,054 kW" in notes["fire"]
    assert "at most 4,108 kW" in notes["room"] and "beyond MQH's range" in notes["room"]  # hottest 1,010 °C
    assert notes["protection"].startswith("Nothing installed")
    assert "= 63 s" in notes["people"] and "untenable at 29 s" in notes["people"]


def test_sidebar_notes_with_a_sprinkler():
    protected = run_scenario(FAST, 2500, DORM, GYPSUM, AWAKE, 600, sprinkler=SPRINKLER)
    notes = guide.sidebar_notes(protected, AWAKE, SI, sprinkler=SPRINKLER)
    assert notes["protection"] == "Sprinkler activates at 109 s, holding the fire at 552 kW."


def test_step_headlines(dorm):
    lines = guide.step_headlines(dorm, SI)
    assert lines[guide.TAB_FLASHOVER] == "Predicted at 182–210 s."
    assert lines[guide.TAB_ESCAPE] == "Untenable at 29 s; everyone is out at 63 s."


def test_3d_reading_guide_follows_units():
    assert "977 °F" in guide.view_calculated(US)[0]  # the 525 °C Draper point


def test_moment_measures_flames_from_the_burning_surface():
    # Sprinkler holds the fire at 552 kW: Heskestad gives flames about 2.5 m tall.
    # From the 0.45 m seat that reaches the 2.6 m ceiling; from the floor it would not.
    protected = run_scenario(FAST, 2500, DORM, GYPSUM, AWAKE, 600, sprinkler=SPRINKLER)
    on_seat = joined(guide.describe_moment(150, protected, DORM, AWAKE, 2500, 1.0, SI, base=0.45))
    on_floor = joined(guide.describe_moment(150, protected, DORM, AWAKE, 2500, 1.0, SI))
    assert "flames about 2.5 m tall" in on_seat and "reach the ceiling" in on_seat
    assert "reach the ceiling" not in on_floor


def test_untenable_reason_follows_units(dorm):
    assert guide.untenable_reason(dorm, SI) == "Smoke reaches head height (1.8 m)"
    assert guide.untenable_reason(dorm, US) == "Smoke reaches head height (5.9 ft)"
    assert "5.9 ft" in joined(guide.explain_escape(DORM, AWAKE, dorm, US, heat_detector_used=False))
