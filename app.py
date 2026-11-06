"""
Compartment Fire Calculator: the Streamlit web app.

Run it with:    streamlit run app.py

All of the physics lives in the fire_model/ package. This file only
  1. collects the inputs in the sidebar (in metric or US customary units),
  2. calls fire_model.scenario.run_scenario() with SI values,
  3. shows the verdict, and explains what the user's last change did, and
  4. shows one tab per step, each explaining its result for these inputs.
The sentences come from guide.py (explanations that follow the inputs) and
explanations.py (the methods), the charts from charts.py and room_view.py, and
the hand calculations from worked_example.py.

How Streamlit works, in one paragraph: every time you change an input,
Streamlit re-runs this whole file from top to bottom and redraws the page.
Values that must survive between runs (like "which room preset is selected",
or the inputs of the previous run, to explain a change) live in
st.session_state, a dictionary Streamlit keeps for each visitor.

This is a learning tool, not a design tool.
"""

import math
import sys
from dataclasses import replace
from pathlib import Path

import streamlit as st

# -----------------------------------------------------------------------------
# Load the current version of this project's own code.
#
# Streamlit Community Cloud keeps the app's Python process running when new code
# is pushed to GitHub, and Python loads each module only once. So after an
# update, modules imported earlier (fire_model/..., charts.py, ...) can stay at
# their OLD version in memory while app.py itself is re-read, and the mix breaks
# (for example an ImportError for a function that only the new version has).
# Whenever any of the project's .py files has changed since the code was loaded,
# forget the project's modules so that the imports below load them fresh.
# -----------------------------------------------------------------------------
PROJECT_FOLDERS = (Path(__file__).resolve().parent, Path(__file__).resolve().parent / "fire_model")


def code_fingerprint():
    """When each of the project's Python files was last changed."""
    return tuple((str(f), f.stat().st_mtime) for folder in PROJECT_FOLDERS for f in sorted(folder.glob("*.py")))


@st.cache_resource
def loaded_code():
    """Which version of the code this running server has loaded (shared by all visitors)."""
    return {"fingerprint": None}


def load_current_code():
    loaded = loaded_code()
    current = code_fingerprint()
    if loaded["fingerprint"] != current:
        for name, module in list(sys.modules.items()):
            path = getattr(module, "__file__", None)
            # Only this project's own modules; never Streamlit, Plotly or Python's.
            if name != "__main__" and path and Path(path).resolve().parent in PROJECT_FOLDERS:
                del sys.modules[name]
        loaded["fingerprint"] = current


load_current_code()

# The project's own modules are imported only now, after the check above.
import charts  # noqa: E402
import explanations  # noqa: E402
import guide  # noqa: E402
from charts import PALETTES, round_half_up, seconds  # noqa: E402
from fire_model.detection import HEAT_DETECTOR_RTI, SPRINKLER_RATING_F, SPRINKLER_RTI, Device, fahrenheit_to_celsius  # noqa: E402
from fire_model.egress import OCCUPANT_PRESETS, Occupant  # noqa: E402
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, REFERENCE_HRR, burning_diameter, growth_coefficient  # noqa: E402
from fire_model.layer_temp import LININGS  # noqa: E402
from fire_model.room import Room, room_problems  # noqa: E402
from fire_model.scenario import run_scenario  # noqa: E402
from fire_model.smoke_filling import flame_height  # noqa: E402
from guide import CUSTOM, NO_SPRINKLER  # noqa: E402
from room_view import burning_surface_height, room_3d_figure  # noqa: E402
from units import SYSTEMS, Units  # noqa: E402
from worked_example import build_worked_example  # noqa: E402

st.set_page_config(page_title="Compartment Fire Calculator", page_icon="🔥", layout="wide")


# =============================================================================
# A. Display data: labels and presets (rounded, generic examples)
# =============================================================================

GROWTH_LABELS = guide.GROWTH_LABELS

# Room presets. Dimensions in m.
ROOM_PRESETS = {
    "Dorm room (example)": dict(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Bedroom": dict(length=5.0, width=4.0, height=2.4, door_width=0.9, door_height=2.0, lining="Gypsum board"),
    "Small office": dict(length=4.0, width=3.0, height=2.7, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Living room, wide opening": dict(length=7.0, width=6.0, height=2.4, door_width=1.8, door_height=2.1, lining="Gypsum board"),
    "Concrete storage room": dict(length=5.0, width=5.0, height=3.0, door_width=0.9, door_height=2.1, lining="Concrete"),
}
ROOM_KEYS = ("length", "width", "height", "door_width", "door_height")
OCCUPANT_KEYS = ("detection", "reaction", "distance", "speed")

# Every input that has a unit: (kind of quantity, SI minimum, SI maximum,
# SI step, US step, SI number format, US number format). The input boxes hold
# values in the units on screen; get_si() converts them back for the physics.
UNIT_INPUTS = {
    "peak_hrr": ("hrr", 50.0, 5000.0, 50.0, 50.0, None, None),
    "fire_diameter": ("length", 0.2, 5.0, 0.1, 0.5, "%.1f", "%.1f"),
    "length": ("length", 1.0, 30.0, 0.1, 0.5, "%.1f", "%.1f"),
    "width": ("length", 1.0, 30.0, 0.1, 0.5, "%.1f", "%.1f"),
    "height": ("length", 2.0, 10.0, 0.1, 0.5, "%.1f", "%.1f"),
    "door_width": ("length", 0.2, 10.0, 0.1, 0.5, "%.1f", "%.1f"),
    "door_height": ("length", 0.3, 10.0, 0.1, 0.5, "%.1f", "%.1f"),
    "thickness": ("thickness", 3.0, 500.0, 1.0, 0.125, "%.0f", "%.2f"),
    "sprinkler_distance": ("length", 0.0, 10.0, 0.1, 0.5, "%.1f", "%.1f"),
    "detector_distance": ("length", 0.0, 10.0, 0.1, 0.5, "%.1f", "%.1f"),
    "distance": ("length", 0.0, 100.0, 0.5, 1.0, "%.1f", "%.1f"),
    "speed": ("speed", 0.2, 2.0, 0.1, 0.25, "%.1f", "%.2f"),
}

# The question each step answers (shown on the overview).
STEP_QUESTIONS = {
    guide.TAB_FIRE: "How big is the fire?",
    guide.TAB_HEAT: "How hot does the smoke get?",
    guide.TAB_FLASHOVER: "Does the room flash over?",
    guide.TAB_ESCAPE: "Do people get out in time?",
}


def lining_thickness_mm(lining_name):
    """Default thickness of a lining preset, in mm (the model itself uses m)."""
    return round(LININGS[lining_name].thickness * 1000, 3)


# =============================================================================
# B. Remembering inputs between re-runs (st.session_state), units and presets
# =============================================================================

DEFAULTS = {  # all in SI, the starting unit system
    "units": SYSTEMS[0],
    "growth": "fast",
    "fuel": "Sofa",
    "peak_hrr": 2500.0,
    "fire_diameter": 1.0,
    "t_end": 600,
    "room_preset": "Dorm room (example)",
    "length": 4.5, "width": 3.5, "height": 2.6, "door_width": 0.9, "door_height": 2.1,
    "lining": "Gypsum board",
    "thickness": lining_thickness_mm("Gypsum board"),
    "sprinkler_type": NO_SPRINKLER,
    "sprinkler_rating": "Ordinary",
    "sprinkler_distance": 2.0,
    "use_heat_detector": False,
    "detector_rating": 135.0,
    "detector_spacing": 30,
    "detector_distance": 2.0,
    "occupant_preset": "Awake, smoke alarm in room",
    "detection": 30.0, "reaction": 30.0, "distance": 4.0, "speed": 1.2,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)  # only sets it on the first run

INPUT_KEYS = list(guide.INPUT_LABELS)  # every input of the model (compared run to run)


def units():
    """The unit system currently selected."""
    return Units(st.session_state.units)


def get_si(key):
    """An input's value converted to SI for the physics."""
    return units().to_si(UNIT_INPUTS[key][0], st.session_state[key])


def set_si(key, si_value):
    """Put an SI value into an input box, converted to the units on screen."""
    st.session_state[key] = units().show(UNIT_INPUTS[key][0], si_value)


def model_inputs():
    """Every input as the model sees it (SI). Rounded, so that switching units back
    and forth (which converts the numbers) doesn't count as a change."""
    values = {}
    for key in INPUT_KEYS:
        value = get_si(key) if key in UNIT_INPUTS else st.session_state[key]
        values[key] = round(value, 9) if isinstance(value, float) else value
    return values


# These "callbacks" run when an input changes, just before the page re-runs.

def convert_units():
    """The unit switch changed: convert every input box to the new units."""
    new = units()
    old = Units(SYSTEMS[0] if new.us else SYSTEMS[1])
    for key, (kind, si_min, si_max, *_) in UNIT_INPUTS.items():
        si = old.to_si(kind, st.session_state[key])
        si = min(max(si, si_min), si_max)  # guard against rounding just outside the limits
        st.session_state[key] = new.show(kind, si)


def apply_fuel():
    if st.session_state.fuel != CUSTOM:
        set_si("peak_hrr", FUEL_PEAK_HRR[st.session_state.fuel])


def mark_fuel_custom():
    st.session_state.fuel = CUSTOM


def apply_room_preset():
    preset = ROOM_PRESETS.get(st.session_state.room_preset)
    if preset is None:  # "Custom": keep the current numbers
        return
    for key in ROOM_KEYS:
        set_si(key, preset[key])
    st.session_state.lining = preset["lining"]
    set_si("thickness", lining_thickness_mm(preset["lining"]))


def apply_lining():
    set_si("thickness", lining_thickness_mm(st.session_state.lining))
    st.session_state.room_preset = CUSTOM


def mark_room_custom():
    st.session_state.room_preset = CUSTOM


def apply_detector_rating():
    """Not every rating is listed for every spacing: pick the closest one that is."""
    available = list(HEAT_DETECTOR_RTI[st.session_state.detector_rating])
    if st.session_state.detector_spacing not in available:
        st.session_state.detector_spacing = min(available, key=lambda sp: abs(sp - st.session_state.detector_spacing))


def apply_occupant_preset():
    preset = OCCUPANT_PRESETS.get(st.session_state.occupant_preset)
    if preset is None:
        return
    st.session_state.detection = float(preset.detection_time)
    st.session_state.reaction = float(preset.reaction_time)
    set_si("distance", preset.walk_distance)
    set_si("speed", preset.walk_speed)


def mark_occupant_custom():
    st.session_state.occupant_preset = CUSTOM


def apply_inputs(values):
    """Set inputs to the given SI values: a "Try this" button, Undo or Start over.

    A preset given without its numbers fills them in (as choosing it in the
    sidebar does); numbers given without their preset switch it to Custom.
    """
    for key, value in values.items():
        if key in UNIT_INPUTS:
            set_si(key, value)
        else:
            st.session_state[key] = value
    given = set(values)
    if "fuel" in given and "peak_hrr" not in given:
        apply_fuel()
    elif "peak_hrr" in given and "fuel" not in given:
        mark_fuel_custom()
    if "room_preset" in given and not given & set(ROOM_KEYS):
        apply_room_preset()
    elif given & set(ROOM_KEYS) and "room_preset" not in given:
        mark_room_custom()
    if "lining" in given and "thickness" not in given:
        apply_lining()
    if "occupant_preset" in given and not given & set(OCCUPANT_KEYS):
        apply_occupant_preset()
    elif given & set(OCCUPANT_KEYS) and "occupant_preset" not in given:
        mark_occupant_custom()
    if "detector_rating" in given:
        apply_detector_rating()


def undo_last_change():
    """Put the inputs back as they were before the last change, and stop explaining it."""
    before, _ = st.session_state.change_record
    apply_inputs(before["inputs"])
    st.session_state.previous_run = before  # so the restored inputs don't count as a new change
    st.session_state.change_record = None
    st.session_state.undone = True


def start_over():
    apply_inputs({key: DEFAULTS[key] for key in INPUT_KEYS})


def dismiss_change():
    st.session_state.change_record = None


def go_to(page):
    """Open a tab (the tabs widget has key "page")."""
    st.session_state.page = page


def show_moment(key, t):
    """Open the 3D view at a key moment."""
    st.session_state.moment_key = key
    st.session_state.moment_t = t
    go_to(guide.TAB_3D)


def pick_moment(times):
    """A key-moment button in the 3D tab was picked (or unpicked)."""
    t = times.get(st.session_state.moment_key)
    if t is not None:
        st.session_state.moment_t = t


def pick_time():
    """The time slider in the 3D tab moved: no key moment is picked any more."""
    st.session_state.moment_key = None


def format_input(key, value):
    """An input value (SI) as text, for "What your last change did"."""
    u = units()
    if key in UNIT_INPUTS:
        kind = UNIT_INPUTS[key][0]
        if kind == "thickness":
            return u.fmt("thickness", value, 2 if u.us else 0)
        return u.fmt(kind, value, 0 if kind == "hrr" else 2 if kind == "speed" and u.us else 1)
    if key == "growth":
        return GROWTH_LABELS[value][0]
    if key == "sprinkler_type":
        return "none" if value == NO_SPRINKLER else value
    if key == "use_heat_detector":
        return "on" if value else "off"
    if key == "detector_rating":
        return u.fmt("temperature", fahrenheit_to_celsius(value))
    if key == "detector_spacing":
        return f"{value} ft"
    if key in ("detection", "reaction", "t_end"):
        return f"{value:g} s"
    return str(value)


def unit_number(container, text, key, on_change=None, disabled=False, help=None):
    """A number box whose unit, limits and step follow the unit switch."""
    kind, si_min, si_max, si_step, us_step, si_format, us_format = UNIT_INPUTS[key]
    u = units()
    container.number_input(
        f"{text} ({u.unit(kind)})", u.show(kind, si_min), u.show(kind, si_max),
        step=us_step if u.us else si_step, format=us_format if u.us else si_format,
        key=key, on_change=on_change, disabled=disabled, help=help or guide.WHY.get(key),
    )


# =============================================================================
# C. Inputs (sidebar). Under each group, a short note says what the inputs
#    currently give; the notes are filled in once the model has run.
# =============================================================================

notes = {}
with st.sidebar:
    st.radio("Units", SYSTEMS, key="units", horizontal=True, on_change=convert_units)
    u = units()

    st.subheader("Step 1 · The fire")
    st.radio(
        "Fire growth rate",
        options=list(GROWTH_TIMES),
        format_func=lambda g: GROWTH_LABELS[g][0],
        captions=[f"α = {u.show('alpha', growth_coefficient(t_g)):.4f} {u.unit('alpha')}" for t_g in GROWTH_TIMES.values()],
        key="growth",
        help=guide.WHY["growth"],
    )
    st.caption(
        f"Reaches {u.fmt('hrr', REFERENCE_HRR)} in {GROWTH_TIMES[st.session_state.growth]:.0f} s. "
        f"Typical fuel: {GROWTH_LABELS[st.session_state.growth][1].lower()}."
    )
    # Menu labels must not change with the unit switch: Streamlit remembers a menu's
    # choice by its label, so a label that changed would no longer match. Numbers that
    # depend on the units go in the slider or a caption instead.
    st.selectbox(
        "What's burning (sets the peak size)",
        options=list(FUEL_PEAK_HRR) + [CUSTOM],
        key="fuel",
        on_change=apply_fuel,
        help=guide.WHY["fuel"] + " The peak sizes are rounded, generic examples.",
    )
    _, hrr_min, hrr_max, hrr_step, hrr_us_step, *_ = UNIT_INPUTS["peak_hrr"]
    st.slider(f"Peak heat release rate ({u.unit('hrr')})", u.show("hrr", hrr_min), u.show("hrr", hrr_max),
              step=hrr_us_step if u.us else hrr_step, format="%.0f", key="peak_hrr", on_change=mark_fuel_custom,
              help=guide.WHY["peak_hrr"])
    unit_number(st, "Fire diameter at full size", "fire_diameter",
                help="Width of the burning area when the fire reaches its peak. While it grows, the burning "
                     "area grows with it (diameter ∝ √Q, as a t-squared fire spreads). Only used for the "
                     "flame height (Heskestad) in the 3D view and the check of where the flames reach. "
                     "An assumed value: set it to match the fuel.")
    st.slider("Time to simulate (s)", 60, 1200, step=30, key="t_end", help=guide.WHY["t_end"])
    t_end = st.session_state.t_end
    st.caption(f"{t_end} s = {t_end // 60}:{t_end % 60:02d} min")
    notes["fire"] = st.empty()

    st.divider()
    st.subheader("Step 2 · The room")
    st.selectbox("Room type", options=list(ROOM_PRESETS) + [CUSTOM], key="room_preset", on_change=apply_room_preset,
                 help=guide.WHY["room_preset"])
    col1, col2, col3 = st.columns(3)
    unit_number(col1, "Length", "length", on_change=mark_room_custom)
    unit_number(col2, "Width", "width", on_change=mark_room_custom)
    unit_number(col3, "Height", "height", on_change=mark_room_custom)
    col1, col2 = st.columns(2)
    unit_number(col1, "Door width", "door_width", on_change=mark_room_custom)
    unit_number(col2, "Door height", "door_height", on_change=mark_room_custom)
    st.selectbox("Wall and ceiling lining", options=list(LININGS), key="lining", on_change=apply_lining,
                 help=guide.WHY["lining"])
    unit_number(st, "Lining thickness", "thickness", on_change=mark_room_custom)
    notes["room"] = st.empty()

    st.divider()
    st.subheader("Fire protection")
    st.selectbox(
        "Sprinkler",
        options=[NO_SPRINKLER] + list(SPRINKLER_RTI),
        format_func=lambda k: "No sprinkler" if k == NO_SPRINKLER else k,
        key="sprinkler_type",
        help=guide.WHY["sprinkler_type"] + " RTI values: Madrzykowski (1995), as tabulated in NUREG-1805 Ch. 10.",
    )
    if st.session_state.sprinkler_type != NO_SPRINKLER:
        st.caption(f"RTI {u.show('rti', SPRINKLER_RTI[st.session_state.sprinkler_type]):.0f} {u.unit('rti')} "
                   "(Madrzykowski 1995, via NUREG-1805).")
        st.selectbox(
            "Sprinkler temperature rating",
            options=list(SPRINKLER_RATING_F),
            format_func=lambda k: f"{k} ({SPRINKLER_RATING_F[k]:g} °F / {fahrenheit_to_celsius(SPRINKLER_RATING_F[k]):.0f} °C)",
            key="sprinkler_rating",
            help=guide.WHY["sprinkler_rating"] + " Generic ratings from the NFPA Automatic Sprinkler Systems "
                                                 "Handbook, via NUREG-1805 Ch. 10.",
        )
        unit_number(st, "Sprinkler distance from the fire", "sprinkler_distance",
                    help="Horizontal distance from the fire's centreline to the sprinkler on the ceiling. "
                         + guide.WHY["sprinkler_distance"])
    st.checkbox("Alarm from a heat detector (instead of a smoke alarm)", key="use_heat_detector",
                help=guide.WHY["use_heat_detector"])
    if st.session_state.use_heat_detector:
        col1, col2 = st.columns(2)
        col1.selectbox("Rating", options=list(HEAT_DETECTOR_RTI), key="detector_rating", on_change=apply_detector_rating,
                       format_func=lambda r: f"{r:g} °F / {fahrenheit_to_celsius(r):.0f} °C",
                       help=guide.WHY["detector_rating"])
        col2.selectbox("UL listed spacing", options=list(HEAT_DETECTOR_RTI[st.session_state.detector_rating]),
                       key="detector_spacing", format_func=lambda sp: f"{sp} ft ({sp * 0.3048:.1f} m)",
                       help=guide.WHY["detector_spacing"])
        rti_detector = HEAT_DETECTOR_RTI[st.session_state.detector_rating][st.session_state.detector_spacing]
        st.caption(f"RTI {u.show('rti', rti_detector):.0f} {u.unit('rti')} (NFPA 72 Table B-3.2.5.1, via NUREG-1805).")
        unit_number(st, "Detector distance from the fire", "detector_distance")
    notes["protection"] = st.empty()

    st.divider()
    st.subheader("Step 4 · The people")
    st.selectbox("Occupant scenario", options=list(OCCUPANT_PRESETS) + [CUSTOM], key="occupant_preset",
                 on_change=apply_occupant_preset, help=guide.WHY["occupant_preset"])
    col1, col2 = st.columns(2)
    col1.number_input("Detection (s)", 0.0, 900.0, step=5.0, format="%.0f", key="detection",
                      on_change=mark_occupant_custom, disabled=st.session_state.use_heat_detector,
                      help=("Set by the heat detector while it is switched on." if st.session_state.use_heat_detector
                            else guide.WHY["detection"]))
    col2.number_input("Reaction (s)", 0.0, 1800.0, step=5.0, format="%.0f", key="reaction", on_change=mark_occupant_custom,
                      help=guide.WHY["reaction"])
    unit_number(col1, "Walk to door", "distance", on_change=mark_occupant_custom)
    unit_number(col2, "Walk speed", "speed", on_change=mark_occupant_custom)
    st.caption("Detection is when the alarm sounds. Reaction is how long people take to notice, decide and start moving.")
    notes["people"] = st.empty()

    st.divider()
    st.button("Start over with the example", icon=":material/restart_alt:", on_click=start_over, width="stretch",
              help="Puts every input back to the dorm room example (keeps the units you chose).")


# =============================================================================
# D. Build the model inputs (in SI) and run the model
# =============================================================================

s = st.session_state
alpha = growth_coefficient(GROWTH_TIMES[s.growth])
peak_hrr = get_si("peak_hrr")
fire_diameter = get_si("fire_diameter")
room = Room(*(get_si(key) for key in ROOM_KEYS))
lining = replace(LININGS[s.lining], thickness=get_si("thickness") / 1000)  # mm -> m
occupant = Occupant(s.detection, s.reaction, get_si("distance"), get_si("speed"))
sprinkler = None
if s.sprinkler_type != NO_SPRINKLER:
    sprinkler = Device(s.sprinkler_type, SPRINKLER_RTI[s.sprinkler_type],
                       fahrenheit_to_celsius(SPRINKLER_RATING_F[s.sprinkler_rating]), get_si("sprinkler_distance"))
heat_detector = None
if s.use_heat_detector:
    heat_detector = Device(f"Heat detector {s.detector_rating:g} °F, {s.detector_spacing} ft",
                           HEAT_DETECTOR_RTI[s.detector_rating][s.detector_spacing],
                           fahrenheit_to_celsius(s.detector_rating), get_si("detector_distance"))

colors = PALETTES.get(st.context.theme.type, PALETTES["light"])  # light if unknown


# =============================================================================
# E. Header, verdict and "What your last change did"
# =============================================================================

st.caption("FIRE PROTECTION ENGINEERING · LEARNING TOOL")
st.title("Compartment Fire Calculator")
st.markdown(
    "Predicts how a fire in a single room grows, how hot the smoke gets, whether the room "
    "reaches flashover, whether a sprinkler or detector activates, and whether the people "
    "inside get out in time. Every result comes from a standard hand-calculation method in "
    "fire dynamics, checked against the U.S. NRC's Fire Dynamics Tools. **Change any input in the "
    "sidebar**: the box under the verdict explains what your change did and why, and each tab "
    "explains one step for your inputs."
)
st.info(
    "**This is a learning tool, not a design tool.** It uses simplified hand-calculation "
    "methods with real limits (listed in the Methods & validation tab). Don't use its results "
    "for real design decisions.",
    icon=":material/school:",
)

problems = room_problems(room)
if problems:
    for problem in problems:
        st.error(f"**Check the room inputs.** {problem}", icon=":material/error:")
    st.stop()  # don't show results for a room that can't exist

result = run_scenario(alpha, peak_hrr, room, lining, occupant, t_end, sprinkler=sprinkler, heat_detector=heat_detector)
# With a sprinkler, also run the same fire without it, to show what it changed.
unprotected = (run_scenario(alpha, peak_hrr, room, lining, occupant, t_end, heat_detector=heat_detector)
               if sprinkler is not None else None)

# Notes under each group of inputs in the sidebar.
for name, text in guide.sidebar_notes(result, occupant, u, sprinkler, heat_detector).items():
    notes[name].caption(f":material/arrow_right_alt: {text}")

room_diagonal = math.hypot(room.length, room.width)
for device, name in ((sprinkler, "sprinkler"), (heat_detector, "heat detector")):
    if device is not None and device.radial_distance > room_diagonal:
        st.warning(f"The {name} is set farther from the fire ({u.fmt('length', device.radial_distance, 1)}) "
                   f"than the room's diagonal ({u.fmt('length', room_diagonal, 1)}).", icon=":material/warning:")

with st.container(border=True):
    v1, v2, v3, v4 = st.columns(4)
    if result.flashover_range is not None:
        first, last = result.flashover_range
        n_methods = sum(m.time is not None for m in result.flashover)
        v1.metric("Flashover", f"{first} s" if first == last else f"{first}–{last} s",
                  help="When the fire is big enough for flashover by each of the 3 methods (Step 3).")
        v1.caption(f"{n_methods} of 3 methods predict it")
    else:
        v1.metric("Flashover", "None", help="When the fire is big enough for flashover by each of the 3 methods (Step 3).")
        v1.caption("The fire stays below every flashover threshold")

    v2.metric("Room untenable (ASET)", seconds(result.aset, missing="—"),
              help="Available safe egress time: when the smoke reaches head height or 200 °C (Step 4).")
    v2.caption(guide.untenable_reason(result, u) or f"Not within {t_end} s: smoke stays above head height and below "
                                      f"{u.fmt('temperature', 200)}")

    rset_help = "Required safe egress time: detection + reaction + walking (Step 4)."
    if result.rset is None:
        v3.metric("Everyone is out (RSET)", "—", help=rset_help)
        v3.caption("No alarm: the heat detector does not activate")
    else:
        v3.metric("Everyone is out (RSET)", seconds(result.rset), help=rset_help)
        walk = occupant.walk_distance / occupant.walk_speed
        source = "heat detector" if heat_detector is not None else "detect"
        v3.caption(f"{round_half_up(result.alarm_time)} {source} + {occupant.reaction_time:g} react + "
                   f"{round_half_up(walk)} walk")

    margin_help = "ASET − RSET: positive means everyone is out before the room becomes untenable."
    if result.rset is None:
        v4.metric("Safety margin", "—", help=margin_help)
    elif result.safety_margin is None:
        v4.metric("Safety margin", f"> {round_half_up(t_end - result.rset)} s", help=margin_help)
    else:
        sign = "+" if result.safety_margin >= 0 else "−"
        v4.metric("Safety margin", f"{sign}{abs(round_half_up(result.safety_margin))} s", help=margin_help)
    v4.caption("Untenable time minus escape time")

    if result.rset is None:
        st.error(f"**No alarm sounds.** The heat detector does not activate within the {t_end} s simulated, "
                 "so the occupant is never warned. A smoke alarm would respond much sooner.",
                 icon=":material/warning:")
    elif result.safety_margin is None:
        st.success(f"**Occupants get out.** The room stays tenable for the whole {t_end} s simulated, "
                   f"and escape takes {seconds(result.rset)}.", icon=":material/check_circle:")
    elif result.safety_margin >= 0:
        st.success(f"**Occupants get out with {round_half_up(result.safety_margin)} s to spare.** Real "
                   "designs add a safety factor, so a thin margin would still need improvement.",
                   icon=":material/check_circle:")
    else:
        st.error(f"**The room becomes untenable {abs(round_half_up(result.safety_margin))} s before "
                 "the occupant is out.** Faster detection, a sprinkler, a slower-growing fuel or a "
                 "larger room would all help. Try changing one.", icon=":material/warning:")

# Compare this run with the previous one: if an input changed, explain the change.
inputs_now = model_inputs()
this_run = {"inputs": inputs_now, "summary": guide.summarize(result)}
previous_run = s.get("previous_run")
new_change = previous_run is not None and previous_run["inputs"] != inputs_now
if new_change:
    s.change_record = (previous_run, this_run)
s.previous_run = this_run

if s.pop("undone", False):
    st.toast("Undone: the inputs are back as they were.", icon=":material/undo:")
record = s.get("change_record")
change = (guide.describe_change(record[0]["inputs"], record[1]["inputs"], record[0]["summary"], record[1]["summary"],
                                u, format_input) if record else None)
if change is not None:
    if new_change:
        st.toast(change.toast, icon=":material/tune:")
    with st.container(border=True):
        st.markdown(f"**:material/tune: What your last change did** · {change.headline}")
        if len(change.inputs) > 1:
            st.caption("Changed: " + " · ".join(change.inputs))
        if change.effects:
            verdicts = {"better": ":green[:material/thumb_up: better]", "worse": ":red[:material/thumb_down: worse]"}
            rows = ["| Result | Before | After | For the people inside |", "|---|---:|---:|---|"]
            rows += [f"| {name} | {before} | {after} | {verdicts.get(verdict, '')} |"
                     for name, before, after, verdict in change.effects]
            st.markdown("\n".join(rows))
        for reason in change.reasons:
            st.markdown(reason)
        b1, b2, b3 = st.columns(3)
        b1.button("Undo this change", icon=":material/undo:", on_click=undo_last_change, width="stretch")
        if s.get("page", guide.TAB_OVERVIEW) != change.step:
            b2.button(f"See it in “{change.step}”", icon=":material/arrow_forward:", on_click=go_to,
                      args=(change.step,), width="stretch")
        b3.button("Dismiss", icon=":material/close:", on_click=dismiss_change, width="stretch")


# =============================================================================
# F. One tab per step. Only the open tab is drawn, so the page stays quick.
# =============================================================================

kit = charts.ChartKit(colors, t_end)


def show(fig):
    st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displaylogo": False})


def readouts(items):
    """A row of small numbers above a chart: (label, value, help text)."""
    for col, (name, value, help_text) in zip(st.columns(len(items)), items):
        col.metric(name, value, help=help_text)


def step_intro(step, paragraphs, where):
    """A step's explanation for these inputs, next to "Try this" buttons that change one input."""
    text, side = st.columns([2, 1], gap="large")
    with text:
        for paragraph in paragraphs:
            st.markdown(paragraph)
    with side.container(border=True):
        st.markdown("**:material/science: Try this**")
        for n, (label, changes) in enumerate(guide.try_this(step, inputs_now, u)):
            st.button(label, key=f"try_{step}_{n}", on_click=apply_inputs, args=(changes,), width="stretch")
        st.caption(f"Each button changes one input; the box at the top then explains the effect. "
                   f"Or change the inputs yourself in the sidebar under **{where}**.")


def method(show_method, label="How this step works: the method and its equations"):
    with st.expander(label, icon=":material/function:"):
        show_method()


def step_nav(step):
    """Back and Next buttons through the steps (the guided tour)."""
    i = guide.TOUR.index(step)
    back, _, forward = st.columns([1, 1, 1])
    if i > 0:
        back.button(f"Back: {guide.TOUR[i - 1]}", icon=":material/arrow_back:", key=f"back_{step}",
                    on_click=go_to, args=(guide.TOUR[i - 1],), width="stretch")
    if i < len(guide.TOUR) - 1:
        forward.button(f"Next: {guide.TOUR[i + 1]}", icon=":material/arrow_forward:", icon_position="right",
                       key=f"next_{step}", type="primary", on_click=go_to, args=(guide.TOUR[i + 1],), width="stretch")


def overview_tab():
    st.subheader("Your scenario, step by step")
    st.markdown(
        "The calculator follows the fire through four steps, each building on the one before. Each "
        "step has a tab that explains its result for **your** inputs, with buttons to try changes."
    )
    headlines = guide.step_headlines(result, u)
    for col, (step, question) in zip(st.columns(4), STEP_QUESTIONS.items()):
        with col.container(border=True, height="stretch"):
            st.caption(f"STEP {step.upper()}")
            st.markdown(f"**{question}**")
            st.markdown(headlines[step])
            st.button("Open this step", key=f"open_{step}", on_click=go_to, args=(step,), width="stretch")
    st.button("Start the guided tour at Step 1", type="primary", icon=":material/play_arrow:",
              on_click=go_to, args=(guide.TAB_FIRE,))

    st.markdown("#### What happens, in order")
    for m in guide.key_moments(result, occupant, heat_detector is not None, u):
        when, what, see = st.columns([1, 6, 2], vertical_alignment="center")
        when.markdown(f"**{m.time} s**")
        what.markdown(f"**{m.label}.** {m.text}")
        see.button("See it in 3D", key=f"see_{m.key}", icon=":material/view_in_ar:", on_click=show_moment,
                   args=(m.key, m.time), width="stretch")


def fire_tab():
    st.subheader("Step 1 · How big is the fire?")
    step_intro(guide.TAB_FIRE, guide.explain_fire(s.growth, peak_hrr, room, result, u), "Step 1 · The fire")
    time_to_peak = seconds(result.time_to_peak) if result.time_to_peak <= t_end else f"> {t_end} s"
    readouts([
        ("Growth coefficient α", f"{u.show('alpha', alpha):.4f} {u.unit('alpha')}", "α = 1055 / t_g², the t-squared growth rate (in kW/s²)"),
        ("Time to peak", time_to_peak, "When the fire stops growing: at its peak HRR, the air supply limit, or sprinkler activation"),
        ("Biggest fire", u.fmt("hrr", max(result.hrr)), "The largest heat release rate reached in the simulated time"),
        ("Energy released", u.fmt("energy", result.energy_released), "Area under the HRR curve over the simulated time"),
    ])
    show(charts.hrr_chart(kit, result, u, s.growth, peak_hrr, unprotected, show_flashover=False))
    st.caption("The dashed gray curves are the other growth rates, for comparison. The flashover thresholds "
               "are added to this chart in Step 3.")
    method(explanations.show_fire_method)
    step_nav(guide.TAB_FIRE)


def heat_tab():
    st.subheader("Step 2 · How hot does the smoke get?")
    other = "Gypsum board" if s.lining == "Concrete" else "Concrete"
    step_intro(guide.TAB_HEAT, guide.explain_heat(room, lining, result, u, (other, LININGS[other])), "Step 2 · The room")
    readouts([
        ("Opening factor Aₒ√Hₒ", u.fmt("opening_factor", result.opening_factor, 2), "Door area times the square root of door height"),
        ("Wall heat-soak time tₚ", seconds(result.penetration_time), "tₚ = (ρc/k)(δ/2)²: time for heat to reach the back of the lining"),
        (f"Layer reaches {u.fmt('temperature', 200)}", seconds(result.time_layer_200c), "Painful radiant heat for anyone below the layer"),
        (f"Layer reaches {u.fmt('temperature', 600)}", seconds(result.time_layer_600c), "Flashover likely; above this MQH is outside its fitted range"),
    ])
    show(charts.temperature_chart(kit, result, u))
    method(explanations.show_heat_method)
    step_nav(guide.TAB_HEAT)


def flashover_tab():
    st.subheader("Step 3 · Does the room flash over?")
    step_intro(guide.TAB_FLASHOVER, guide.explain_flashover(room, result, u), "Step 2 · The room (the door)")
    bab, tho, mqh = result.flashover
    readouts([
        ("Babrauskas threshold", u.fmt("hrr", bab.threshold_hrr), "750 × the opening factor"),
        ("Thomas threshold", u.fmt("hrr", tho.threshold_hrr), "7.8 × A_T + 378 × the opening factor"),
        (f"MQH (smoke at {u.fmt('temperature', 520)})", u.fmt("hrr", mqh.threshold_hrr),
         "The fire size when the Step 2 smoke temperature reaches 520 °C (— if it never does)"),
        ("Air supply limit", u.fmt("hrr", result.ventilation_limit), "1500 × the opening factor: the largest fire the door's air supply can feed"),
    ])
    show(charts.hrr_chart(kit, result, u, s.growth, peak_hrr, unprotected))
    rows = ["| Flashover method | Minimum fire size | Your fire reaches it at |", "|---|---:|---:|"]
    for m in result.flashover:
        name = f"MQH (smoke at {u.fmt('temperature', 520)})" if m.name.startswith("MQH") else m.name
        rows.append(f"| {name} | {u.fmt('hrr', m.threshold_hrr)} | {seconds(m.time)} |")
    vent_time = result.time_vent_limited
    rows.append(f"| Fire limited by air supply | {u.fmt('hrr', result.ventilation_limit)} | "
                f"{seconds(vent_time if vent_time is not None and vent_time <= t_end else None)} |")
    st.markdown("\n".join(rows))
    method(explanations.show_flashover_method)
    step_nav(guide.TAB_FLASHOVER)


def escape_tab():
    st.subheader("Step 4 · Do people get out in time?")
    step_intro(guide.TAB_ESCAPE, guide.explain_escape(room, occupant, result, u, heat_detector is not None),
               "Step 4 · The people")
    readouts([
        ("Floor area", u.fmt("area", result.floor_area, 1), "The smoke layer spreads over this area as it fills the room"),
        ("Smoke reaches door top", seconds(result.time_smoke_at_door_top), "From here on, smoke flows out through the top of the door"),
        (f"Smoke reaches {u.fmt('length', 1.8, 1)}", seconds(result.time_smoke_at_head_height), "Head height: people would be breathing smoke"),
        ("Height at end", u.fmt("length", result.layer_height[-1], 2), f"Bottom of the smoke layer at t = {t_end} s"),
    ])
    show(charts.height_chart(kit, result, room, u))
    # Where the flames reach into the smoke layer, Heskestad's plume equation is outside its range.
    flames_in_layer = next((t for t in range(1, t_end + 1)
                            if result.layer_height[t] < room.height - 0.01
                            and flame_height(result.hrr[t], burning_diameter(result.hrr[t], peak_hrr, fire_diameter))
                            >= result.layer_height[t]), None)
    if flames_in_layer is not None:
        st.caption(f"With a {u.fmt('length', fire_diameter, 1)} full-size fire diameter, the flames reach into the smoke "
                   f"layer from {flames_in_layer} s. From then on Heskestad's plume equation, which is meant "
                   "for heights above the flames, is used outside its range.")
    if min(result.layer_height) < 0.05:
        st.caption("Why the line jitters near the floor: once the room is full of smoke, the plume still "
                   "brings in slightly more gas than the door can let out, so the model's layer keeps "
                   "trying to go below the floor. The height is held at 0, the plume briefly adds nothing, "
                   "the layer bounces back up a few centimetres, and the cycle repeats. Read it as smoke "
                   "all the way down to the floor.")
    method(explanations.show_escape_method)
    step_nav(guide.TAB_ESCAPE)


def protection_tab():
    st.subheader("Sprinklers and heat detectors")
    step_intro(guide.TAB_PROTECTION,
               guide.explain_protection(room, result, unprotected, sprinkler, heat_detector, occupant, u),
               "Fire protection")
    if sprinkler is not None or heat_detector is not None:
        p1, p2, p3 = st.columns(3)
        if sprinkler is not None:
            if result.sprinkler_time is not None:
                p1.metric("Sprinkler activates", seconds(result.sprinkler_time))
                p1.caption(f"The fire stops growing at {u.fmt('hrr', result.sprinkler_hrr)}")
            else:
                p1.metric("Sprinkler activates", "—")
                p1.caption(f"Not within {t_end} s: the ceiling jet never heats it to its rating")
            before = (f"{unprotected.flashover_range[0]}–{unprotected.flashover_range[1]} s"
                      if unprotected.flashover_range else "none")
            after = (f"{result.flashover_range[0]}–{result.flashover_range[1]} s" if result.flashover_range else "none")
            p2.metric("Flashover without → with sprinkler", f"{before} → {after}")
            p2.caption(f"Hottest smoke {u.fmt('temperature', max(unprotected.layer_temp))} → "
                       f"{u.fmt('temperature', max(result.layer_temp))}")
        if heat_detector is not None:
            target = p3 if sprinkler is not None else p1
            target.metric("Heat detector alarm", seconds(result.heat_detector_time, missing="—"))
            target.caption(f"Instead of a {occupant.detection_time:g} s smoke alarm detection time")
        st.markdown("**How the devices heat up:** each device's element (its colored line) heats up more slowly "
                    "than the hot ceiling jet around it, and activates when it reaches its rating (gray dashed line).")
        show(charts.temperature_chart(kit, result, u, sprinkler, heat_detector))
        if sprinkler is not None:
            st.markdown("**What the sprinkler changes:** the fire stops growing when it activates (dotted: the "
                        "same fire without it).")
            show(charts.hrr_chart(kit, result, u, s.growth, peak_hrr, unprotected))
    method(explanations.show_protection_method, "How sprinklers and detectors are calculated: the method and its data")
    step_nav(guide.TAB_PROTECTION)


def view_tab():
    st.subheader("What it looks like inside")
    st.markdown(
        "A 3D picture of this calculator's results, drawn to scale. Pick a key moment or any time, press "
        "**Play** to watch the fire grow, the smoke drop and heat up and the occupant head for the door, "
        "and drag the picture to turn it."
    )
    moments = guide.key_moments(result, occupant, heat_detector is not None, u)
    times = {m.key: m.time for m in moments}
    labels = {m.key: f"{m.label} · {m.time} s" for m in moments}
    # The view opens at the moment the room becomes untenable (if it does). A picked
    # moment keeps its current time, since the times move when the inputs change.
    if "moment_key" not in s:
        s.moment_key = "untenable" if "untenable" in times else None
    if s.moment_key not in times:
        s.moment_key = None
    if s.moment_key is not None:
        s.moment_t = times[s.moment_key]
    default_t = result.aset if result.aset is not None else min(120, t_end)
    s.moment_t = int(min(max(s.get("moment_t", default_t), 0), t_end))
    st.pills("Jump to a key moment", list(times), format_func=labels.get, key="moment_key",
             on_change=pick_moment, args=(times,), persist_state="page")
    st.slider("Or pick any time (s)", 0, t_end, key="moment_t", on_change=pick_time, persist_state="page")
    t = s.moment_t
    fuel = None if s.fuel == CUSTOM else s.fuel
    show(room_3d_figure(result, room, occupant, colors, u, start_time=t, fire_diameter=fire_diameter,
                        peak_hrr=peak_hrr, sprinkler=sprinkler, heat_detector=heat_detector, fuel=fuel))
    left, right = st.columns([3, 2], gap="large")
    with left:
        for paragraph in guide.describe_moment(t, result, room, occupant, peak_hrr, fire_diameter, u, sprinkler,
                                               heat_detector, base=burning_surface_height(fuel)):
            st.markdown(paragraph)
        st.caption("This description is for the moment picked above. While the animation plays, the "
                   "caption at the top of the picture follows it.")
    with right.container(border=True):
        st.markdown("**:material/visibility: How to read this view**")
        st.markdown("Calculated by the model:")
        st.markdown("\n".join(f"- {line}" for line in guide.view_calculated(u)))
        st.markdown("Drawn for realism only:")
        st.markdown("\n".join(f"- {line}" for line in guide.VIEW_DRAWN))
        st.caption("This is not a 3D fire simulation: a two-zone model knows only the smoke layer's depth "
                   "and one average temperature, so the smoke is one uniform slab. Full 3D fire simulation "
                   "needs CFD software such as NIST's FDS.")
    step_nav(guide.TAB_3D)


def math_tab():
    st.subheader("Check the calculation by hand")
    st.markdown(
        "Every equation at one moment, with this scenario's numbers put in, so you can redo each line "
        "with a calculator. The calculator uses SI units internally, as the correlations were written."
    )
    s.worked_t = int(min(s.get("worked_t", min(150, t_end)), t_end))
    st.slider("Show the calculation at t (s)", 1, t_end, key="worked_t", persist_state="page")
    sections = build_worked_example(s.worked_t, GROWTH_TIMES[s.growth], peak_hrr, room, lining,
                                    occupant, result, sprinkler=sprinkler, heat_detector=heat_detector)
    for tab, (title, lines) in zip(st.tabs([title.split(":")[0] for title, _ in sections]), sections):
        with tab:
            st.markdown(f"**{title}**")
            for explanation, latex in lines:
                st.markdown(explanation)
                if latex:
                    st.latex(latex)

    with st.expander("Show the numbers behind the charts", icon=":material/table:"):
        step = 5 if t_end <= 300 else 10
        rows = []
        for t in range(0, t_end + 1, step):
            row = {
                "Time (s)": t,
                f"Fire size ({u.unit('hrr')})": round(u.show("hrr", result.hrr[t])),
                f"Smoke layer temperature ({u.unit('temperature')})": round(u.show("temperature", result.layer_temp[t])),
                f"Bottom of smoke layer ({u.unit('length')})": round(u.show("length", result.layer_height[t]), 2),
            }
            if result.sprinkler_temps is not None:
                row[f"Sprinkler element ({u.unit('temperature')})"] = round(u.show("temperature", result.sprinkler_temps[t]))
            if result.heat_detector_temps is not None:
                row[f"Heat detector element ({u.unit('temperature')})"] = round(u.show("temperature", result.heat_detector_temps[t]))
            rows.append(row)
        st.dataframe(rows, hide_index=True, width="stretch")


TAB_CONTENT = {
    guide.TAB_OVERVIEW: overview_tab,
    guide.TAB_FIRE: fire_tab,
    guide.TAB_HEAT: heat_tab,
    guide.TAB_FLASHOVER: flashover_tab,
    guide.TAB_ESCAPE: escape_tab,
    guide.TAB_PROTECTION: protection_tab,
    guide.TAB_3D: view_tab,
    guide.TAB_MATH: math_tab,
    guide.TAB_ABOUT: explanations.show_methods_page,
}
for name, tab in zip(guide.TABS, st.tabs(guide.TABS, key="page", on_change="rerun")):
    with tab:
        if tab.open:
            TAB_CONTENT[name]()

st.divider()
st.caption(
    "A learning tool built step by step as a first-year fire protection engineering project "
    "by Dhruv Sirigiri. Not for real design decisions."
)
