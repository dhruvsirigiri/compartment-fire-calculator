"""
Compartment Fire Calculator: the Streamlit web app.

Run it with:    streamlit run app.py

All of the physics lives in the fire_model/ package. This file only
  1. collects the inputs in the sidebar (in metric or US customary units),
  2. calls fire_model.scenario.run_scenario() with SI values, and
  3. shows the verdict, the 3D view, the charts and the hand calculations.
The charts are drawn by charts.py and room_view.py, the hand calculations by
worked_example.py, and the explanatory text by explanations.py.

How Streamlit works, in one paragraph: every time you change an input,
Streamlit re-runs this whole file from top to bottom and redraws the page.
Values that must survive between runs (like "which room preset is selected")
live in st.session_state, a dictionary Streamlit keeps for each visitor.

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
from charts import PALETTES, round_half_up, seconds  # noqa: E402
from explanations import show_explanations  # noqa: E402
from fire_model.detection import HEAT_DETECTOR_RTI, SPRINKLER_RATING_F, SPRINKLER_RTI, Device, fahrenheit_to_celsius  # noqa: E402
from fire_model.egress import OCCUPANT_PRESETS, Occupant  # noqa: E402
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, REFERENCE_HRR, burning_diameter, growth_coefficient  # noqa: E402
from fire_model.layer_temp import LININGS  # noqa: E402
from fire_model.room import Room, room_problems  # noqa: E402
from fire_model.scenario import run_scenario  # noqa: E402
from fire_model.smoke_filling import flame_height  # noqa: E402
from room_view import room_3d_figure  # noqa: E402
from units import SYSTEMS, Units  # noqa: E402
from worked_example import build_worked_example  # noqa: E402

st.set_page_config(page_title="Compartment Fire Calculator", page_icon="🔥", layout="wide")


# =============================================================================
# A. Display data: labels and presets (rounded, generic examples)
# =============================================================================

CUSTOM = "Custom"
NO_SPRINKLER = "None"

GROWTH_LABELS = {
    "slow": ("Slow", "Dense wood furniture"),
    "medium": ("Medium", "Cotton or polyester bedding"),
    "fast": ("Fast", "Upholstered furniture, stacked boxes"),
    "ultrafast": ("Ultrafast", "Flammable liquid pool, thin plastics"),
}

# Room presets. Dimensions in m.
ROOM_PRESETS = {
    "Dorm room (example)": dict(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Bedroom": dict(length=5.0, width=4.0, height=2.4, door_width=0.9, door_height=2.0, lining="Gypsum board"),
    "Small office": dict(length=4.0, width=3.0, height=2.7, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Living room, wide opening": dict(length=7.0, width=6.0, height=2.4, door_width=1.8, door_height=2.1, lining="Gypsum board"),
    "Concrete storage room": dict(length=5.0, width=5.0, height=3.0, door_width=0.9, door_height=2.1, lining="Concrete"),
}
ROOM_KEYS = ("length", "width", "height", "door_width", "door_height")

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


def units():
    """The unit system currently selected."""
    return Units(st.session_state.units)


def get_si(key):
    """An input's value converted to SI for the physics."""
    return units().to_si(UNIT_INPUTS[key][0], st.session_state[key])


def set_si(key, si_value):
    """Put an SI value into an input box, converted to the units on screen."""
    st.session_state[key] = units().show(UNIT_INPUTS[key][0], si_value)


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


def unit_number(container, text, key, on_change=None, disabled=False, help=None):
    """A number box whose unit, limits and step follow the unit switch."""
    kind, si_min, si_max, si_step, us_step, si_format, us_format = UNIT_INPUTS[key]
    u = units()
    container.number_input(
        f"{text} ({u.unit(kind)})", u.show(kind, si_min), u.show(kind, si_max),
        step=us_step if u.us else si_step, format=us_format if u.us else si_format,
        key=key, on_change=on_change, disabled=disabled, help=help,
    )


# =============================================================================
# C. Inputs (sidebar)
# =============================================================================

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
    )
    st.caption(
        f"Reaches {u.fmt('hrr', REFERENCE_HRR)} in {GROWTH_TIMES[st.session_state.growth]:.0f} s. "
        f"Typical fuel: {GROWTH_LABELS[st.session_state.growth][1].lower()}."
    )
    st.selectbox(
        "What's burning (sets the peak size)",
        options=list(FUEL_PEAK_HRR) + [CUSTOM],
        format_func=lambda f: f if f == CUSTOM else f"{f} (≈{u.fmt('hrr', FUEL_PEAK_HRR[f])})",
        key="fuel",
        on_change=apply_fuel,
    )
    _, hrr_min, hrr_max, hrr_step, hrr_us_step, *_ = UNIT_INPUTS["peak_hrr"]
    st.slider(f"Peak heat release rate ({u.unit('hrr')})", u.show("hrr", hrr_min), u.show("hrr", hrr_max),
              step=hrr_us_step if u.us else hrr_step, format="%.0f", key="peak_hrr", on_change=mark_fuel_custom)
    unit_number(st, "Fire diameter at full size", "fire_diameter",
                help="Width of the burning area when the fire reaches its peak. While it grows, the burning "
                     "area grows with it (diameter ∝ √Q, as a t-squared fire spreads). Only used for the "
                     "flame height (Heskestad) in the 3D view and the check of where the flames reach. "
                     "An assumed value: set it to match the fuel.")
    st.slider("Time to simulate (s)", 60, 1200, step=30, key="t_end")
    t_end = st.session_state.t_end
    st.caption(f"{t_end} s = {t_end // 60}:{t_end % 60:02d} min")

    st.divider()
    st.subheader("Step 2 · The room")
    st.selectbox("Room type", options=list(ROOM_PRESETS) + [CUSTOM], key="room_preset", on_change=apply_room_preset)
    col1, col2, col3 = st.columns(3)
    unit_number(col1, "Length", "length", on_change=mark_room_custom)
    unit_number(col2, "Width", "width", on_change=mark_room_custom)
    unit_number(col3, "Height", "height", on_change=mark_room_custom)
    col1, col2 = st.columns(2)
    unit_number(col1, "Door width", "door_width", on_change=mark_room_custom)
    unit_number(col2, "Door height", "door_height", on_change=mark_room_custom)
    st.selectbox("Wall and ceiling lining", options=list(LININGS), key="lining", on_change=apply_lining)
    unit_number(st, "Lining thickness", "thickness", on_change=mark_room_custom)

    st.divider()
    st.subheader("Fire protection")
    st.selectbox(
        "Sprinkler",
        options=[NO_SPRINKLER] + list(SPRINKLER_RTI),
        format_func=lambda k: "No sprinkler" if k == NO_SPRINKLER else f"{k} (RTI {u.show('rti', SPRINKLER_RTI[k]):.0f} {u.unit('rti')})",
        key="sprinkler_type",
        help="Response Time Index (RTI) values: Madrzykowski (1995), as tabulated in NUREG-1805 Ch. 10.",
    )
    if st.session_state.sprinkler_type != NO_SPRINKLER:
        st.selectbox(
            "Sprinkler temperature rating",
            options=list(SPRINKLER_RATING_F),
            format_func=lambda k: f"{k} ({u.fmt('temperature', fahrenheit_to_celsius(SPRINKLER_RATING_F[k]))})",
            key="sprinkler_rating",
            help="Generic ratings from the NFPA Automatic Sprinkler Systems Handbook, via NUREG-1805 Ch. 10.",
        )
        unit_number(st, "Sprinkler distance from the fire", "sprinkler_distance",
                    help="Horizontal distance from the fire's centreline to the sprinkler on the ceiling.")
    st.checkbox("Alarm from a heat detector (instead of a smoke alarm)", key="use_heat_detector")
    if st.session_state.use_heat_detector:
        col1, col2 = st.columns(2)
        col1.selectbox("Rating", options=list(HEAT_DETECTOR_RTI), key="detector_rating", on_change=apply_detector_rating,
                       format_func=lambda r: u.fmt("temperature", fahrenheit_to_celsius(r)))
        col2.selectbox("UL listed spacing", options=list(HEAT_DETECTOR_RTI[st.session_state.detector_rating]),
                       key="detector_spacing", format_func=lambda sp: f"{sp} ft ({sp * 0.3048:.1f} m)")
        rti_detector = HEAT_DETECTOR_RTI[st.session_state.detector_rating][st.session_state.detector_spacing]
        st.caption(f"RTI {u.show('rti', rti_detector):.0f} {u.unit('rti')} (NFPA 72 Table B-3.2.5.1, via NUREG-1805).")
        unit_number(st, "Detector distance from the fire", "detector_distance")

    st.divider()
    st.subheader("Step 4 · The people")
    st.selectbox("Occupant scenario", options=list(OCCUPANT_PRESETS) + [CUSTOM], key="occupant_preset",
                 on_change=apply_occupant_preset)
    col1, col2 = st.columns(2)
    col1.number_input("Detection (s)", 0.0, 900.0, step=5.0, format="%.0f", key="detection",
                      on_change=mark_occupant_custom, disabled=st.session_state.use_heat_detector,
                      help="Set by the heat detector while it is switched on." if st.session_state.use_heat_detector else None)
    col2.number_input("Reaction (s)", 0.0, 1800.0, step=5.0, format="%.0f", key="reaction", on_change=mark_occupant_custom)
    unit_number(col1, "Walk to door", "distance", on_change=mark_occupant_custom)
    unit_number(col2, "Walk speed", "speed", on_change=mark_occupant_custom)
    st.caption("Detection is when the alarm sounds. Reaction is how long people take to notice, decide and start moving.")


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
# E. Header and verdict
# =============================================================================

st.caption("FIRE PROTECTION ENGINEERING · LEARNING TOOL")
st.title("Compartment Fire Calculator")
st.markdown(
    "Predicts how a fire in a single room grows, how hot the smoke gets, whether the room "
    "reaches flashover, whether a sprinkler or detector activates, and whether the people "
    "inside get out in time. Every result comes from a standard hand-calculation method in "
    "fire dynamics, checked against the U.S. NRC's Fire Dynamics Tools and explained below."
)
st.info(
    "**This is a learning tool, not a design tool.** It uses simplified hand-calculation "
    "methods with real limits (listed at the bottom of the page). Don't use its results "
    "for real design decisions.",
    icon=":material/school:",
)

for col, (step, text) in zip(st.columns(4), [
    ("Step 1", "Fire growth (heat release rate)"),
    ("Step 2", "Hot smoke layer temperature"),
    ("Step 3", "Flashover and the air supply limit"),
    ("Step 4", "Smoke filling and escape time"),
]):
    col.markdown(f"**{step}**  \n{text}")

problems = room_problems(room)
if problems:
    for problem in problems:
        st.error(f"**Check the room inputs.** {problem}", icon=":material/error:")
    st.stop()  # don't show results for a room that can't exist

result = run_scenario(alpha, peak_hrr, room, lining, occupant, t_end, sprinkler=sprinkler, heat_detector=heat_detector)
# With a sprinkler, also run the same fire without it, to show what it changed.
unprotected = (run_scenario(alpha, peak_hrr, room, lining, occupant, t_end, heat_detector=heat_detector)
               if sprinkler is not None else None)

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
        v1.metric("Flashover", f"{first} s" if first == last else f"{first}–{last} s")
        v1.caption(f"{n_methods} of 3 methods predict it")
    else:
        v1.metric("Flashover", "None")
        v1.caption("The fire stays below every flashover threshold")

    v2.metric("Room untenable (ASET)", seconds(result.aset, missing="—"))
    v2.caption(result.aset_reason or f"Not within {t_end} s: smoke stays above head height and below "
                                      f"{u.fmt('temperature', 200)}")

    if result.rset is None:
        v3.metric("Everyone is out (RSET)", "—")
        v3.caption("No alarm: the heat detector does not activate")
    else:
        v3.metric("Everyone is out (RSET)", seconds(result.rset))
        walk = occupant.walk_distance / occupant.walk_speed
        source = "heat detector" if heat_detector is not None else "detect"
        v3.caption(f"{round_half_up(result.alarm_time)} {source} + {occupant.reaction_time:g} react + "
                   f"{round_half_up(walk)} walk")

    if result.rset is None:
        v4.metric("Safety margin", "—")
    elif result.safety_margin is None:
        v4.metric("Safety margin", f"> {round_half_up(t_end - result.rset)} s")
    else:
        sign = "+" if result.safety_margin >= 0 else "−"
        v4.metric("Safety margin", f"{sign}{abs(round_half_up(result.safety_margin))} s")
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

if sprinkler is not None or heat_detector is not None:
    with st.container(border=True):
        st.markdown("**Fire protection**")
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
        if sprinkler is not None and result.sprinkler_time is not None and result.aset is not None \
                and result.sprinkler_time > result.aset:
            st.caption("The smoke reaches untenable conditions before the sprinkler activates. Sprinklers "
                       "control the fire and protect the building, but in a small room the smoke can still "
                       "fill it first, which is why early smoke detection matters for the people inside.")


# =============================================================================
# F. 3D view and charts
# =============================================================================

kit = charts.ChartKit(colors, t_end)


def show(fig):
    st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displaylogo": False})


def readouts(items):
    """A row of small numbers above a chart: (label, value, help text)."""
    for col, (name, value, help_text) in zip(st.columns(len(items)), items):
        col.metric(name, value, help=help_text)


with st.container(border=True):
    st.subheader("What it looks like inside")
    st.caption("3D VIEW OF THE MODEL'S RESULTS")
    st.markdown(
        ("It opens at the moment the room becomes untenable. " if result.aset is not None else "")
        + "Press **Play**, or drag the slider, to watch the fire grow, the smoke layer drop and heat up, "
        "and the occupant head for the door. Drag the picture to rotate it."
    )
    show(room_3d_figure(result, room, occupant, colors, u, start_time=result.aset or 120,
                        fire_diameter=fire_diameter, peak_hrr=peak_hrr, sprinkler=sprinkler,
                        heat_detector=heat_detector))
    st.caption(
        "This is a picture of this calculator's results, not a 3D fire simulation. The flame height is "
        "Heskestad's correlation, with the burning area growing to the fire diameter you set as the fire "
        "grows. The smoke is drawn as one flat, uniform "
        "slab because a two-zone model knows only the layer's depth and its single average temperature. "
        "The plume's shape is illustrative. Full 3D fire simulation needs CFD software such as NIST's FDS."
    )

with st.container(border=True):
    st.subheader("Fire size over time")
    st.caption("STEPS 1 & 3 · HEAT RELEASE RATE")
    time_to_peak = seconds(result.time_to_peak) if result.time_to_peak <= t_end else f"> {t_end} s"
    readouts([
        ("Growth coefficient α", f"{u.show('alpha', alpha):.4f} {u.unit('alpha')}", "α = 1055 / t_g², the t-squared growth rate (in kW/s²)"),
        ("Time to peak", time_to_peak, "When the fire stops growing: at its peak HRR, the air supply limit, or sprinkler activation"),
        ("Air supply limit", u.fmt("hrr", result.ventilation_limit), "1500 × the opening factor: the largest fire the door's air supply can feed"),
        ("Energy released", u.fmt("energy", result.energy_released), "Area under the HRR curve over the simulated time"),
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

with st.container(border=True):
    st.subheader("Hot smoke layer temperature")
    st.caption("STEP 2 · MQH METHOD" + (" · SPRINKLER AND DETECTOR HEATING" if sprinkler or heat_detector else ""))
    readouts([
        ("Opening factor Aₒ√Hₒ", u.fmt("opening_factor", result.opening_factor, 2), "Door area times the square root of door height"),
        ("Wall heat-soak time tₚ", seconds(result.penetration_time), "tₚ = (ρc/k)(δ/2)²: time for heat to reach the back of the lining"),
        (f"Layer reaches {u.fmt('temperature', 200)}", seconds(result.time_layer_200c), "Painful radiant heat for anyone below the layer"),
        (f"Layer reaches {u.fmt('temperature', 600)}", seconds(result.time_layer_600c), "Flashover likely; above this MQH is outside its fitted range"),
    ])
    show(charts.temperature_chart(kit, result, u, sprinkler, heat_detector))

with st.container(border=True):
    st.subheader("Smoke layer height")
    st.caption("STEP 4 · SMOKE FILLING")
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

with st.expander("Show the numbers behind the charts"):
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


# =============================================================================
# G. Check the calculation by hand
# =============================================================================

with st.container(border=True):
    st.subheader("Check the calculation by hand")
    st.markdown(
        "Every equation at one moment, with this scenario's numbers put in, so you can redo each line "
        "with a calculator. The calculator uses SI units internally, as the correlations were written."
    )
    st.session_state.setdefault("worked_t", min(150, t_end))
    if st.session_state.worked_t > t_end:
        st.session_state.worked_t = t_end
    st.slider("Show the calculation at t (s)", 1, t_end, key="worked_t")
    sections = build_worked_example(st.session_state.worked_t, GROWTH_TIMES[s.growth], peak_hrr, room, lining,
                                    occupant, result, sprinkler=sprinkler, heat_detector=heat_detector)
    for tab, (title, lines) in zip(st.tabs([title.split(":")[0] for title, _ in sections]), sections):
        with tab:
            st.markdown(f"**{title}**")
            for explanation, latex in lines:
                st.markdown(explanation)
                if latex:
                    st.latex(latex)


# =============================================================================
# H. How it works, validation, realism, limitations and sources
# =============================================================================

show_explanations()

st.divider()
st.caption(
    "A learning tool built step by step as a first-year fire protection engineering project "
    "by Dhruv Sirigiri. Not for real design decisions."
)
