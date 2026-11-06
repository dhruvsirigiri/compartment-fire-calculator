"""
Compartment Fire Calculator: the Streamlit web app.

Run it with:    streamlit run app.py

All of the physics lives in the fire_model/ package. This file only
  1. collects the inputs in the sidebar,
  2. calls fire_model.scenario.run_scenario(), and
  3. shows the verdict, the charts and the explanations.

How Streamlit works, in one paragraph: every time you change an input,
Streamlit re-runs this whole file from top to bottom and redraws the page.
Values that must survive between runs (like "which room preset is selected")
live in st.session_state, a dictionary Streamlit keeps for each visitor.

This is a learning tool, not a design tool.
"""

import math
from dataclasses import replace

import plotly.graph_objects as go
import streamlit as st

from fire_model.egress import HEAD_HEIGHT, OCCUPANT_PRESETS, TENABILITY_TEMP, Occupant, walking_time
from fire_model.growth import FUEL_PEAK_HRR, GROWTH_TIMES, REFERENCE_HRR, growth_coefficient
from fire_model.layer_temp import LININGS, MQH_UPPER_LIMIT
from fire_model.room import Room, room_problems
from fire_model.scenario import run_scenario

st.set_page_config(page_title="Compartment Fire Calculator", page_icon="🔥", layout="wide")


# =============================================================================
# A. Display data: labels, presets and colors (from the index.html prototype)
# =============================================================================

CUSTOM = "Custom"

# Growth classes: display name and a typical fuel for each.
GROWTH_LABELS = {
    "slow": ("Slow", "Dense wood furniture"),
    "medium": ("Medium", "Cotton or polyester bedding"),
    "fast": ("Fast", "Upholstered furniture, stacked boxes"),
    "ultrafast": ("Ultrafast", "Flammable liquid pool, thin plastics"),
}

# Room presets: rounded, generic examples. Dimensions in m.
ROOM_PRESETS = {
    "Dorm room (example)": dict(length=4.5, width=3.5, height=2.6, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Bedroom": dict(length=5.0, width=4.0, height=2.4, door_width=0.9, door_height=2.0, lining="Gypsum board"),
    "Small office": dict(length=4.0, width=3.0, height=2.7, door_width=0.9, door_height=2.1, lining="Gypsum board"),
    "Living room, wide opening": dict(length=7.0, width=6.0, height=2.4, door_width=1.8, door_height=2.1, lining="Gypsum board"),
    "Concrete storage room": dict(length=5.0, width=5.0, height=3.0, door_width=0.9, door_height=2.1, lining="Concrete"),
}
ROOM_KEYS = ("length", "width", "height", "door_width", "door_height")

# Chart colors for light and dark mode. Each chart's colors were checked as a
# set for color-blind safety and contrast against the page background.
PALETTES = {
    "light": dict(
        fire="#C2410C",  # your fire (ember)
        flashover="#A3237A",  # flashover range band
        air="#1D4ED8",  # air supply limit, RSET
        heat="#B91C1C",  # smoke temperature, ASET
        smoke="#4B5563",  # smoke layer height
        reference="#8A94A6",  # gray reference curves and threshold lines
        text="#5A6475",  # chart labels (text never uses the data colors)
        surface="#FFFFFF",  # page background, behind chart labels
    ),
    "dark": dict(
        fire="#E8590C",
        flashover="#D6409F",
        air="#4C8DF6",
        heat="#E0484A",
        smoke="#9CA3AF",
        reference="#6B7586",
        text="#9AA3B2",
        surface="#11151C",
    ),
}


def lining_thickness_mm(lining_name):
    """Default thickness of a lining preset, in mm (the app shows mm, the model uses m)."""
    return round(LININGS[lining_name].thickness * 1000, 3)


def occupant_fields(preset_name):
    """The four occupant inputs for a preset, as floats for the number boxes."""
    o = OCCUPANT_PRESETS[preset_name]
    return {
        "detection": float(o.detection_time),
        "reaction": float(o.reaction_time),
        "distance": float(o.walk_distance),
        "speed": float(o.walk_speed),
    }


# =============================================================================
# B. Remembering inputs between re-runs (st.session_state) and preset logic
# =============================================================================

DEFAULTS = {
    "growth": "fast",
    "fuel": "Sofa",
    "peak_hrr": 2500,
    "t_end": 600,
    "room_preset": "Dorm room (example)",
    "length": 4.5,
    "width": 3.5,
    "height": 2.6,
    "door_width": 0.9,
    "door_height": 2.1,
    "lining": "Gypsum board",
    "thickness_mm": lining_thickness_mm("Gypsum board"),
    "occupant_preset": "Awake, smoke alarm in room",
    **occupant_fields("Awake, smoke alarm in room"),
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)  # only sets it on the first run


# These "callbacks" run when an input changes, just before the page re-runs.
# They keep the presets and the individual inputs in step, like the prototype:
# picking a preset fills in the numbers; editing a number switches to "Custom".

def apply_fuel():
    if st.session_state.fuel != CUSTOM:
        st.session_state.peak_hrr = int(FUEL_PEAK_HRR[st.session_state.fuel])


def mark_fuel_custom():
    st.session_state.fuel = CUSTOM


def apply_room_preset():
    preset = ROOM_PRESETS.get(st.session_state.room_preset)
    if preset is None:  # "Custom": keep the current numbers
        return
    for key in ROOM_KEYS:
        st.session_state[key] = float(preset[key])
    st.session_state.lining = preset["lining"]
    st.session_state.thickness_mm = lining_thickness_mm(preset["lining"])


def apply_lining():
    st.session_state.thickness_mm = lining_thickness_mm(st.session_state.lining)
    st.session_state.room_preset = CUSTOM


def mark_room_custom():
    st.session_state.room_preset = CUSTOM


def apply_occupant_preset():
    if st.session_state.occupant_preset in OCCUPANT_PRESETS:
        st.session_state.update(occupant_fields(st.session_state.occupant_preset))


def mark_occupant_custom():
    st.session_state.occupant_preset = CUSTOM


# =============================================================================
# C. Inputs (sidebar)
# =============================================================================

with st.sidebar:
    st.subheader("Step 1 · The fire")
    st.radio(
        "Fire growth rate",
        options=list(GROWTH_TIMES),
        format_func=lambda g: GROWTH_LABELS[g][0],
        captions=[f"α = {growth_coefficient(t_g):.4f} kW/s²" for t_g in GROWTH_TIMES.values()],
        key="growth",
    )
    growth_name, typical_fuel = GROWTH_LABELS[st.session_state.growth]
    st.caption(
        f"Reaches {REFERENCE_HRR:,.0f} kW in {GROWTH_TIMES[st.session_state.growth]:.0f} s. "
        f"Typical fuel: {typical_fuel.lower()}."
    )
    st.selectbox(
        "What's burning (sets the peak size)",
        options=list(FUEL_PEAK_HRR) + [CUSTOM],
        format_func=lambda f: f if f == CUSTOM else f"{f} (≈{FUEL_PEAK_HRR[f]:,.0f} kW)",
        key="fuel",
        on_change=apply_fuel,
    )
    st.slider("Peak heat release rate (kW)", 50, 5000, step=50, key="peak_hrr", on_change=mark_fuel_custom)
    st.slider("Time to simulate (s)", 60, 1200, step=30, key="t_end")
    t_end = st.session_state.t_end
    st.caption(f"{t_end} s = {t_end // 60}:{t_end % 60:02d} min")

    st.divider()
    st.subheader("Step 2 · The room")
    st.selectbox("Room type", options=list(ROOM_PRESETS) + [CUSTOM], key="room_preset", on_change=apply_room_preset)
    col1, col2, col3 = st.columns(3)
    col1.number_input("Length (m)", 1.0, 30.0, step=0.1, format="%.1f", key="length", on_change=mark_room_custom)
    col2.number_input("Width (m)", 1.0, 30.0, step=0.1, format="%.1f", key="width", on_change=mark_room_custom)
    col3.number_input("Height (m)", 2.0, 10.0, step=0.1, format="%.1f", key="height", on_change=mark_room_custom)
    col1, col2 = st.columns(2)
    col1.number_input("Door width (m)", 0.2, 10.0, step=0.1, format="%.1f", key="door_width", on_change=mark_room_custom)
    col2.number_input("Door height (m)", 0.3, 10.0, step=0.1, format="%.1f", key="door_height", on_change=mark_room_custom)
    st.selectbox("Wall and ceiling lining", options=list(LININGS), key="lining", on_change=apply_lining)
    st.number_input("Lining thickness (mm)", 3.0, 500.0, step=1.0, format="%.0f", key="thickness_mm", on_change=mark_room_custom)

    st.divider()
    st.subheader("Step 4 · The people")
    st.selectbox(
        "Occupant scenario",
        options=list(OCCUPANT_PRESETS) + [CUSTOM],
        key="occupant_preset",
        on_change=apply_occupant_preset,
    )
    col1, col2 = st.columns(2)
    col1.number_input("Detection (s)", 0.0, 900.0, step=5.0, format="%.0f", key="detection", on_change=mark_occupant_custom)
    col2.number_input("Reaction (s)", 0.0, 1800.0, step=5.0, format="%.0f", key="reaction", on_change=mark_occupant_custom)
    col1.number_input("Walk to door (m)", 0.0, 100.0, step=0.5, format="%.1f", key="distance", on_change=mark_occupant_custom)
    col2.number_input("Walk speed (m/s)", 0.2, 2.0, step=0.1, format="%.1f", key="speed", on_change=mark_occupant_custom)
    st.caption(
        "Detection is when the alarm sounds. Reaction is how long people take to "
        "notice, decide and start moving."
    )


# =============================================================================
# D. Build the model inputs and run the model
# =============================================================================

s = st.session_state
alpha = growth_coefficient(GROWTH_TIMES[s.growth])
peak_hrr = s.peak_hrr
room = Room(s.length, s.width, s.height, s.door_width, s.door_height)
lining = replace(LININGS[s.lining], thickness=s.thickness_mm / 1000)  # mm -> m
occupant = Occupant(s.detection, s.reaction, s.distance, s.speed)

# Pick chart colors for the current light/dark theme (light if unknown).
colors = PALETTES.get(st.context.theme.type, PALETTES["light"])


def round_half_up(x):
    """Round like a calculator (2.5 -> 3). Python's round() would give 2."""
    return math.floor(x + 0.5)


def seconds(t, missing="Not reached"):
    """Format a time in s for display, or `missing` if it never happens."""
    return missing if t is None else f"{round_half_up(t):,} s"


# =============================================================================
# E. Header and verdict
# =============================================================================

st.caption("FIRE PROTECTION ENGINEERING · LEARNING TOOL")
st.title("Compartment Fire Calculator")
st.markdown(
    "Predicts how a fire in a single room grows, how hot the smoke gets, whether the room "
    "reaches flashover, and whether the people inside get out in time. Every result comes "
    "from a standard hand-calculation method in fire dynamics, explained below."
)
st.info(
    "**This is a learning tool, not a design tool.** It uses simplified hand-calculation "
    "methods with real limits (listed at the bottom of the page). Don't use its results "
    "for real design decisions.",
    icon=":material/school:",
)

step_cols = st.columns(4)
for col, (step, label) in zip(
    step_cols,
    [
        ("Step 1", "Fire growth (heat release rate)"),
        ("Step 2", "Hot smoke layer temperature"),
        ("Step 3", "Flashover and the air supply limit"),
        ("Step 4", "Smoke filling and escape time"),
    ],
):
    col.markdown(f"**{step}**  \n{label}")

problems = room_problems(room)
if problems:
    for problem in problems:
        st.error(f"**Check the room inputs.** {problem}", icon=":material/error:")
    st.stop()  # don't show results for a room that can't exist

result = run_scenario(alpha, peak_hrr, room, lining, occupant, t_end)

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

    v2.metric("Room becomes untenable (ASET)", seconds(result.aset, missing="—"))
    v2.caption(result.aset_reason or f"Not within {t_end} s: smoke stays above head height and below 200 °C")

    v3.metric("Everyone is out (RSET)", seconds(result.rset))
    v3.caption(
        f"{occupant.detection_time:g} detect + {occupant.reaction_time:g} react + "
        f"{round_half_up(walking_time(occupant))} walk"
    )

    if result.safety_margin is None:
        v4.metric("Safety margin", f"> {round_half_up(t_end - result.rset)} s")
    else:
        sign = "+" if result.safety_margin >= 0 else "−"
        v4.metric("Safety margin", f"{sign}{abs(round_half_up(result.safety_margin))} s")
    v4.caption("Untenable time minus escape time")

    if result.safety_margin is None:
        st.success(
            f"**Occupants get out.** The room stays tenable for the whole {t_end} s simulated, "
            f"and escape takes {seconds(result.rset)}.",
            icon=":material/check_circle:",
        )
    elif result.safety_margin >= 0:
        st.success(
            f"**Occupants get out with {round_half_up(result.safety_margin)} s to spare.** Real "
            "designs add a safety factor, so a thin margin would still need improvement.",
            icon=":material/check_circle:",
        )
    else:
        st.error(
            f"**The room becomes untenable {abs(round_half_up(result.safety_margin))} s before "
            "the occupant is out.** Faster detection, a sprinkler, a slower-growing fuel or a "
            "larger room would all help. Try changing one.",
            icon=":material/warning:",
        )


# =============================================================================
# F. Charts (Plotly)
# =============================================================================

TIMES = list(range(t_end + 1))  # one point per second, matching the model


def rgba(hex_color, opacity):
    """'#RRGGBB' -> 'rgba(r,g,b,opacity)' for see-through fills."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{opacity})"


def nice_axis_top(value, n_ticks=5):
    """Round an axis maximum up to a clean number (e.g. 2,870 -> 3,000)."""
    raw_step = value / n_ticks
    power = 10 ** math.floor(math.log10(raw_step))
    f = raw_step / power
    step = (1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10) * power
    return math.ceil(value / step) * step


def new_chart(y_title, y_top, y_format):
    """An empty chart with the shared look: time on x, one y-axis, hover crosshair."""
    fig = go.Figure()
    fig.update_layout(
        height=360,
        margin=dict(l=8, r=8, t=16, b=8),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0, traceorder="normal"),
    )
    fig.update_xaxes(
        title_text="Time since ignition (s)",
        range=[0, t_end],
        unifiedhovertitle=dict(text="t = %{x} s"),
    )
    fig.update_yaxes(title_text=y_title, range=[0, y_top], tickformat=y_format)
    return fig


def label(fig, x, y, text, xanchor="left", yanchor="bottom", xshift=0, yshift=0):
    """A direct label on the chart, in the text color (never in a data color).
    A see-through background in the page color keeps it readable if a line
    passes behind it."""
    fig.add_annotation(
        x=x, y=y, text=text, showarrow=False, xanchor=xanchor, yanchor=yanchor,
        xshift=xshift, yshift=yshift, font=dict(color=colors["text"], size=12),
        bgcolor=rgba(colors["surface"], 0.8),
    )


def label_line(fig, y, text, curves, y_top):
    """Label a horizontal line at height y where the fewest curves cross the text.

    Tries six spots (right, left or middle of the chart; above or below the
    line) and counts how many points of `curves` (lists with one value per
    second) would fall under the label. The spot with the fewest wins, in that
    order of preference. Different scenarios put the curves in different places,
    so any fixed label position would collide sooner or later.
    """
    # Rough size of the label in axis units: ~0.9% of the chart width per
    # character, and ~9% of the chart height.
    width = min(0.6, 0.009 * len(text) + 0.02) * t_end
    text_height = 0.09 * y_top
    spots = {  # x anchor: (first second covered, last second covered, x position)
        "right": (t_end - width, t_end, t_end),
        "left": (0, width, 0),
        "center": ((t_end - width) / 2, (t_end + width) / 2, t_end / 2),
    }
    best = None
    for anchor, (t0, t1, x) in spots.items():
        for above in (True, False):
            low, high = (y, y + text_height) if above else (y - text_height, y)
            if high > y_top or low < 0:
                continue  # the label would stick out of the chart
            hits = sum(low <= curve[t] <= high for curve in curves for t in range(int(t0), int(t1) + 1))
            if best is None or hits < best[0]:
                best = (hits, anchor, x, above)
    if best is None:  # no room above or below: put it just above the line
        best = (0, "right", t_end, True)
    _, anchor, x, above = best
    label(fig, x, y, text, xanchor=anchor, yanchor="bottom" if above else "top",
          xshift={"right": -6, "left": 6, "center": 0}[anchor], yshift=0 if above else -2)


def threshold_line(fig, y, text, curves, y_top):
    """A gray dashed horizontal threshold line with a direct label."""
    fig.add_hline(y=y, line=dict(color=colors["reference"], width=1, dash="dash"))
    label_line(fig, y, text, curves, y_top)


def show(fig):
    st.plotly_chart(fig, theme="streamlit", width="stretch", config={"displaylogo": False})


# ---- Chart 1: heat release rate (Steps 1 and 3) ----

def hrr_chart():
    fo_sizes = [m.threshold_hrr for m in result.flashover if m.threshold_hrr is not None]
    y_top = nice_axis_top(max(peak_hrr, min(result.ventilation_limit, peak_hrr * 1.6), *fo_sizes) * 1.12)
    fig = new_chart("Heat release rate (kW)", y_top, ",.0f")
    show_vent_line = result.ventilation_limit <= y_top

    # Every curve on the chart, one value per second, so labels can avoid them.
    other_classes = [key for key in GROWTH_TIMES if key != s.growth]
    curves = [result.hrr] + [
        [growth_coefficient(GROWTH_TIMES[key]) * t**2 for t in TIMES] for key in other_classes
    ]
    vent_line = [result.ventilation_limit] * len(TIMES)

    # Flashover range: a band from the smallest to the largest threshold.
    if fo_sizes:
        low, high = min(fo_sizes), max(fo_sizes)
        high = max(high, low + y_top * 0.005)  # keep a single-value band visible
        fig.add_trace(go.Scatter(x=[0, t_end], y=[low, low], mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[0, t_end], y=[high, high], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=rgba(colors["flashover"], 0.22),
                                 name="Flashover range (3 methods)", hoverinfo="skip", legendrank=2))
        label_line(fig, high, f"Flashover range {min(fo_sizes):,.0f}–{max(fo_sizes):,.0f} kW",
                   curves + ([vent_line] if show_vent_line else []), y_top)

    # Air supply limit (only if it fits on the chart).
    if show_vent_line:
        fig.add_trace(go.Scatter(x=[0, t_end], y=[result.ventilation_limit] * 2, mode="lines",
                                 line=dict(color=colors["air"], width=1.5, dash="dash"),
                                 name="Air supply limit", hoverinfo="skip", legendrank=3))
        label_line(fig, result.ventilation_limit,
                   f"Air supply limit {result.ventilation_limit:,.0f} kW", curves, y_top)

    # The other growth classes, for comparison (gray, labelled where they end).
    first_reference = True
    for key in other_classes:
        a = growth_coefficient(GROWTH_TIMES[key])
        t_exit = math.sqrt(y_top / a)  # when alpha t^2 leaves the top of the chart
        ts = [min(t_end, t_exit) * i / 100 for i in range(101)]
        fig.add_trace(go.Scatter(x=ts, y=[a * t**2 for t in ts], mode="lines",
                                 line=dict(color=colors["reference"], width=1.2, dash="dash"),
                                 name="Other growth rates", legendgroup="other",
                                 showlegend=first_reference, hoverinfo="skip", legendrank=4))
        first_reference = False
        if t_exit < t_end:
            label(fig, t_exit, y_top, GROWTH_LABELS[key][0], yanchor="top", xshift=4)
        else:
            label(fig, t_end, a * t_end**2, GROWTH_LABELS[key][0], xanchor="right", xshift=-4)

    # Your fire, drawn last so it sits on top.
    fig.add_trace(go.Scatter(x=TIMES, y=result.hrr, mode="lines", name="Your fire",
                             line=dict(color=colors["fire"], width=2.5),
                             fill="tozeroy", fillcolor=rgba(colors["fire"], 0.10),
                             hovertemplate="%{y:,.0f} kW", legendrank=1))
    return fig


# ---- Chart 2: smoke layer temperature (Step 2) ----

def temperature_chart():
    temps = result.layer_temp
    y_top = nice_axis_top(max(max(temps) * 1.08, 700))
    fig = new_chart("Smoke layer temperature (°C)", y_top, ",.0f")

    # Above 600 °C the MQH correlation is outside the range it was fitted to.
    fig.add_hrect(y0=MQH_UPPER_LIMIT, y1=y_top, fillcolor=colors["heat"], opacity=0.06, line_width=0)
    threshold_line(fig, TENABILITY_TEMP, "200 °C · painful radiant heat below", [temps], y_top)
    threshold_line(fig, MQH_UPPER_LIMIT, "600 °C · flashover likely; MQH not fitted above", [temps], y_top)

    # Thermal penetration time: after this the walls conduct heat straight through.
    if result.penetration_time < t_end:
        fig.add_vline(x=result.penetration_time, line=dict(color=colors["reference"], width=1, dash="dot"))
        label(fig, result.penetration_time, 0, "t<sub>p</sub>", xanchor="right", xshift=-4, yshift=4)

    # Solid line up to 600 °C, dotted above it. The dotted part starts at the
    # last in-range point so the two pieces join up.
    in_range = [T if T <= MQH_UPPER_LIMIT else None for T in temps]
    out_of_range = [T if T > MQH_UPPER_LIMIT else None for T in temps]
    for t in range(1, len(temps)):
        if out_of_range[t] is not None and out_of_range[t - 1] is None:
            out_of_range[t - 1] = temps[t - 1]
    fig.add_trace(go.Scatter(x=TIMES, y=in_range, mode="lines", name="Smoke layer temperature",
                             line=dict(color=colors["heat"], width=2.5), hovertemplate="%{y:,.0f} °C"))
    if any(T is not None for T in out_of_range):
        fig.add_trace(go.Scatter(x=TIMES, y=out_of_range, mode="lines",
                                 name="Above 600 °C, outside the method's range",
                                 line=dict(color=colors["heat"], width=2.5, dash="dot"),
                                 hovertemplate="%{y:,.0f} °C"))
    return fig


# ---- Chart 3: smoke layer height with ASET and RSET (Step 4) ----

def height_chart():
    heights = result.layer_height
    y_top = math.ceil(room.height * 2) / 2
    fig = new_chart("Height above floor (m)", y_top, ".1f")

    # Shade the smoke: fill from the ceiling down to the bottom of the layer.
    fig.add_trace(go.Scatter(x=TIMES, y=[room.height] * len(TIMES), mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=TIMES, y=heights, mode="lines", name="Bottom of smoke layer",
                             line=dict(color=colors["smoke"], width=2.5),
                             fill="tonexty", fillcolor=rgba(colors["smoke"], 0.18),
                             hovertemplate="%{y:.2f} m", legendrank=1))

    threshold_line(fig, HEAD_HEIGHT, "1.8 m · head height", [heights], y_top)
    if abs(room.door_height - HEAD_HEIGHT) > 0.12 and room.door_height < y_top:
        threshold_line(fig, room.door_height, "Top of door", [heights], y_top)

    # ASET and RSET as vertical lines, each labelled with vertical text running
    # alongside its line. Labels go on the right of each line, except that when
    # the two lines are very close the earlier one's label goes on its left, so
    # neither label crosses the other line.
    events = [
        (t, short, long_name, color)
        for t, short, long_name, color in [
            (result.aset, "ASET", "Untenable (ASET)", colors["heat"]),
            (result.rset, "RSET", "Everyone out (RSET)", colors["air"]),
        ]
        if t is not None and t <= t_end
    ]
    events.sort(key=lambda event: event[0])  # earliest first
    very_close = len(events) == 2 and events[1][0] - events[0][0] < 0.04 * t_end
    for i, (t, short, long_name, color) in enumerate(events):
        fig.add_trace(go.Scatter(x=[t, t], y=[0, y_top], mode="lines", name=f"{long_name} {seconds(t)}",
                                 line=dict(color=color, width=2), hoverinfo="skip", legendrank=2 + i))
        on_left = (very_close and i == 0) or t > 0.97 * t_end
        fig.add_annotation(x=t, y=y_top, text=f"{short} {seconds(t)}", textangle=-90, showarrow=False,
                           xanchor="right" if on_left else "left", yanchor="top", xshift=-3 if on_left else 3,
                           font=dict(color=colors["text"], size=12))
    return fig


def readouts(items):
    """A row of small numbers above a chart: (label, value, help text)."""
    for col, (name, value, help_text) in zip(st.columns(len(items)), items):
        col.metric(name, value, help=help_text)


with st.container(border=True):
    st.subheader("Fire size over time")
    st.caption("STEPS 1 & 3 · HEAT RELEASE RATE")
    time_to_peak = (
        seconds(result.time_to_peak) if result.time_to_peak <= t_end else f"> {t_end} s"
    )
    readouts([
        ("Growth coefficient α", f"{alpha:.4f} kW/s²", "α = 1055 / t_g², the t-squared growth rate"),
        ("Time to peak", time_to_peak, "When the fire stops growing: at its peak HRR or the air supply limit, whichever is lower"),
        ("Air supply limit", f"{result.ventilation_limit:,.0f} kW", "1500 × the opening factor: the largest fire the door's air supply can feed"),
        ("Energy released", f"{result.energy_released:,.0f} MJ", "Area under the HRR curve over the simulated time"),
    ])
    show(hrr_chart())

    rows = ["| Flashover method | Minimum fire size | Your fire reaches it at |", "|---|---:|---:|"]
    for m in result.flashover:
        size = "—" if m.threshold_hrr is None else f"{m.threshold_hrr:,.0f} kW"
        rows.append(f"| {m.name} | {size} | {seconds(m.time)} |")
    vent_time = result.time_vent_limited
    rows.append(
        f"| Fire limited by air supply | {result.ventilation_limit:,.0f} kW | "
        f"{seconds(vent_time if vent_time is not None and vent_time <= t_end else None)} |"
    )
    st.markdown("\n".join(rows))

with st.container(border=True):
    st.subheader("Hot smoke layer temperature")
    st.caption("STEP 2 · MQH METHOD")
    readouts([
        ("Opening factor Aₒ√Hₒ", f"{result.opening_factor:.2f} m⁵ᐟ²", "Door area times the square root of door height"),
        ("Wall heat-soak time tₚ", f"{result.penetration_time:,.0f} s", "tₚ = (ρc/k)(δ/2)²: time for heat to reach the back of the lining"),
        ("Layer reaches 200 °C", seconds(result.time_layer_200c), "Painful radiant heat for anyone below the layer"),
        ("Layer reaches 600 °C", seconds(result.time_layer_600c), "Flashover likely; above this MQH is outside its fitted range"),
    ])
    show(temperature_chart())

with st.container(border=True):
    st.subheader("Smoke layer height")
    st.caption("STEP 4 · SMOKE FILLING")
    readouts([
        ("Floor area", f"{result.floor_area:.1f} m²", "The smoke layer spreads over this area as it fills the room"),
        ("Smoke reaches door top", seconds(result.time_smoke_at_door_top), "From here on, smoke flows out through the top of the door"),
        ("Smoke reaches 1.8 m", seconds(result.time_smoke_at_head_height), "Head height: people would be breathing smoke"),
        ("Height at end", f"{result.layer_height[-1]:.2f} m", f"Bottom of the smoke layer at t = {t_end} s"),
    ])
    show(height_chart())

with st.expander("Show the numbers behind the charts"):
    step = 5 if t_end <= 300 else 10
    st.dataframe(
        [
            {
                "Time (s)": t,
                "Fire size (kW)": round(result.hrr[t]),
                "Smoke layer temperature (°C)": round(result.layer_temp[t]),
                "Bottom of smoke layer (m)": round(result.layer_height[t], 2),
            }
            for t in range(0, t_end + 1, step)
        ],
        hide_index=True,
        width="stretch",
    )


# =============================================================================
# G. How it works: one panel per step, plus limitations and sources
# =============================================================================

st.header("How the calculator works")
left, right = st.columns(2)

with left.container(border=True):
    st.caption("STEP 1")
    st.subheader("How big is the fire?")
    st.markdown(
        "The **heat release rate** (HRR) is how much energy a fire gives off each second, in "
        "kilowatts (kW). Smoke temperature, smoke production and flashover all depend on it, so "
        "every later step uses this curve as its input."
    )
    st.latex(r"Q(t) = \alpha\, t^2 \qquad \alpha = \frac{1055}{t_g^{2}}")
    st.markdown(
        "**Q** is the heat release rate in kW, **t** is time since ignition in seconds, and "
        "**α** is the growth coefficient in kW/s². Because time is squared, doubling the time "
        "makes the fire four times bigger. The fire then holds at a **peak HRR** set by what is "
        "burning. Each growth rate is defined by the time $t_g$ to reach 1,055 kW (1,000 BTU/s)."
    )
    st.markdown(
        "\n".join(
            ["| Growth rate | $t_g$ (s) | α (kW/s²) | Typical fuel |", "|---|---:|---:|---|"]
            + [
                f"| {GROWTH_LABELS[k][0]} | {t_g:.0f} | {growth_coefficient(t_g):.4f} | {GROWTH_LABELS[k][1]} |"
                for k, t_g in GROWTH_TIMES.items()
            ]
        )
    )

with right.container(border=True):
    st.caption("STEP 2")
    st.subheader("How hot does the smoke get?")
    st.markdown(
        "The plume carries hot gas to the ceiling, where it forms a smoke layer. The **MQH method** "
        "(McCaffrey, Quintiere and Harkleroad, 1981) predicts the layer's average temperature from "
        "an energy balance: heat comes in from the fire and leaves out the door and into the walls."
    )
    st.latex(r"\Delta T_g = 6.85 \left[ \frac{Q^2}{A_o\sqrt{H_o}\; h_k\, A_T} \right]^{1/3}")
    st.markdown(
        r"- $A_o\sqrt{H_o}$, the **opening factor**: door area times the square root of its height. "
        "Taller doors vent hot gas better.\n"
        "- $A_T$, the inside surface area of walls, ceiling and floor minus the door.\n"
        "- $h_k$, how easily the walls absorb heat. Early on, heat only soaks into the surface; "
        "after the thermal penetration time $t_p$ it flows right through the wall:"
    )
    st.latex(
        r"t_p = \frac{\rho c}{k}\left(\frac{\delta}{2}\right)^2 \qquad "
        r"h_k = \begin{cases} \sqrt{k \rho c / t} & t < t_p \\ k/\delta & t \ge t_p \end{cases}"
    )
    st.markdown(
        "\n".join(
            ["| Lining | k (kW/m·K) | ρ (kg/m³) | c (kJ/kg·K) | Default δ (mm) |", "|---|---:|---:|---:|---:|"]
            + [
                f"| {m.name} | {m.k:g} | {m.rho:g} | {m.c:g} | {m.thickness * 1000:g} |"
                for m in LININGS.values()
            ]
        )
    )
    st.caption("MQH was fitted to tests with layer temperatures below about 600 °C. Lining properties: NUREG-1805.")

left, right = st.columns(2)

with left.container(border=True):
    st.caption("STEP 3")
    st.subheader("When does the room flash over?")
    st.markdown(
        "**Flashover** is the sudden switch from a fire burning one object to a room where every "
        "exposed surface is burning. Radiation from the hot smoke layer heats everything below it "
        "until it all ignites at once. After flashover, nobody in the room survives, and the fire "
        "can spread to the rest of the building. Three classic methods estimate the smallest fire "
        "that can cause it:"
    )
    st.latex(r"\text{Babrauskas:}\quad Q_{FO} = 750\, A_o\sqrt{H_o}")
    st.latex(r"\text{Thomas:}\quad Q_{FO} = 7.8\, A_T + 378\, A_o\sqrt{H_o}")
    st.latex(r"\text{MQH:}\quad Q_{FO} = 610 \left( h_k\, A_T\, A_o\sqrt{H_o} \right)^{1/2}")
    st.markdown(
        "The MQH version is Step 2 solved backwards for the fire that makes the smoke about 500 °C "
        "hotter than ambient, so the calculator reads it straight off the temperature curve (the "
        "time the layer reaches 520 °C). The methods disagree, which is normal: engineers look at "
        "the whole range rather than trusting one number."
    )
    st.markdown(
        "**The air supply limit.** A fire needs oxygen, and in a closed room almost all of it comes "
        r"through the door. About $0.5\,A_o\sqrt{H_o}$ kg/s of air can flow in, and burning 1 kg of "
        "air releases about 3,000 kJ, so the biggest fire the door can support is roughly:"
    )
    st.latex(r"Q_{vent} = 1500\, A_o\sqrt{H_o}")
    st.markdown(
        "A fire held back by its air supply is called **ventilation-controlled**. The fire used "
        "everywhere in the calculator is the smallest of the three limits:"
    )
    st.latex(r"Q_{eff}(t) = \min\left(\alpha t^2,\ Q_{max},\ Q_{vent}\right)")

with right.container(border=True):
    st.caption("STEP 4")
    st.subheader("Do people get out in time?")
    st.markdown(
        "Fire safety design compares two times. **ASET** (available safe egress time) is how long "
        "until the room becomes untenable. **RSET** (required safe egress time) is how long people "
        "need to get out. The design works only if ASET is longer than RSET."
    )
    st.markdown(
        "**Smoke filling.** The plume pulls in (entrains) room air as it rises, so it carries much "
        "more mass to the ceiling than the fire itself produces. The calculator uses Heskestad's "
        r"plume equation, with 70% of the fire's heat carried by the plume ($Q_c = 0.7\,Q$):"
    )
    st.latex(r"\dot m_p = 0.071\, Q_c^{1/3} z^{5/3} + 0.0018\, Q_c \quad \text{(kg/s)}")
    st.markdown(
        "$z$ is the height of the smoke layer's bottom edge. Once the layer drops below the top of "
        "the door ($H_d$), smoke flows out through the doorway (width $W$), pushed by buoyancy, with "
        "flow coefficient $C_d = 0.7$:"
    )
    st.latex(
        r"\dot m_{out} = \tfrac{2}{3} C_d W \rho_g \sqrt{2 g \left(1 - \tfrac{T_a}{T_g}\right)\tfrac{T_g}{T_a}}\,(H_d - z)^{3/2}"
    )
    st.markdown(
        "The mass $m$ in the layer changes by what comes in minus what goes out. Its density comes "
        "from the Step 2 temperature (in K), and spreading it over the floor area gives its depth:"
    )
    st.latex(r"\frac{dm}{dt} = \dot m_p - \dot m_{out}")
    st.latex(r"\rho_g = \frac{353}{T_g} \qquad z = H - \frac{m}{\rho_g\, A_{floor}}")
    st.markdown(
        "This differential equation is solved step by step every 0.25 s with **Euler's method**, "
        "the same idea as in calculus: $m_{new} = m + (dm/dt)\\,\\Delta t$."
    )
    st.markdown(
        "**Untenable** here means the earlier of two events: the smoke layer drops to 1.8 m (head "
        "height, so people breathe it), or the layer reaches 200 °C (painful radiant heat from above)."
    )
    st.latex(r"\text{RSET} = t_{detection} + t_{reaction} + \frac{\text{walking distance}}{\text{walking speed}}")

left, right = st.columns(2)

with left.container(border=True):
    st.caption("LIMITS")
    st.subheader("What this calculator leaves out")
    st.markdown(
        "- One room with one opening. Smoke spreading to other rooms is not modeled.\n"
        "- The fire sits on the floor and never decays or burns out.\n"
        "- No sprinklers. A sprinkler would cap or shrink the fire once it activates.\n"
        "- The smoke layer has one average temperature, from MQH. MQH was fitted to tests below "
        "about 600 °C, and the smoke filling model uses it outside its original purpose.\n"
        "- The door outflow ignores the neutral plane and the fresh air flowing in below it, so "
        "late-time smoke layer heights near the floor are approximate.\n"
        "- Untenability is judged by layer height and temperature only, not by toxic gases or "
        "visibility.\n"
        "- The occupant walks straight to the door at a steady speed."
    )
    st.markdown(
        "Real designs use full zone models such as CFAST, or CFD models such as FDS, both free from "
        "NIST, along with safety factors. This tool shows the physics those models are built on."
    )

with right.container(border=True):
    st.caption("SOURCES")
    st.subheader("Methods and data")
    st.markdown(
        "- t-squared growth classes: NFPA 72, Annex B.\n"
        "- Hot gas layer temperature and MQH flashover: McCaffrey, Quintiere and Harkleroad, "
        "*Fire Technology* 17 (1981).\n"
        "- Flashover correlations: Babrauskas (1980); Thomas (1981).\n"
        "- Plume entrainment: Heskestad, plume chapter, SFPE Handbook of Fire Protection Engineering.\n"
        "- Implementation of these methods and material properties: U.S. NRC NUREG-1805, "
        "Fire Dynamics Tools.\n"
        "- ASET/RSET framework: SFPE Engineering Guide to Human Behavior in Fire."
    )
    st.caption("Peak fire sizes and room presets are rounded, generic examples.")

st.divider()
st.caption(
    "A learning tool built step by step as a first-year fire protection engineering project "
    "by Dhruv Sirigiri. Not for real design decisions."
)
