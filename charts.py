"""
The app's 2D charts (Plotly): fire size, smoke layer temperature, smoke layer height.

These functions only draw results; every number comes from a fire_model
ScenarioResult. Values arrive in SI and are converted for display with a
units.Units object, so the charts follow the metric / US customary switch.

Design rules used throughout (from the project's chart guidelines):
  * data lines are colored; threshold and reference lines are gray and dashed;
  * labels are written in the text color, never in a data color;
  * every color set was checked for color-blind safety and contrast.
"""

import math

import plotly.graph_objects as go

from fire_model.egress import HEAD_HEIGHT, TENABILITY_TEMP
from fire_model.growth import GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import MQH_UPPER_LIMIT

# Chart colors for light and dark mode. Each chart's colors were checked as a
# set for color-blind safety and contrast against the page background.
PALETTES = {
    "light": dict(
        fire="#C2410C",  # your fire (ember)
        flashover="#A3237A",  # flashover range band
        air="#1D4ED8",  # air supply limit, RSET, sprinkler
        heat="#B91C1C",  # smoke temperature, ASET
        detector="#047857",  # heat detector
        smoke="#4B5563",  # smoke layer height
        reference="#8A94A6",  # gray reference curves and threshold lines
        text="#5A6475",  # chart labels (text never uses the data colors)
        surface="#FFFFFF",  # page background, behind chart labels
        safe="#15803D",  # 3D view: occupant is out (always shown with a text label)
        smoke_thin="#B4BAC2",  # 3D view: cool, thin smoke ...
        smoke_thick="#33383F",  # ... darkening to hot, sooty smoke (glows red above ~525 °C)
        floor="#CDBFA8",  # 3D view scenery (illustrative)
        wall="#E3E6EA",
        furniture="#7D6F64",
    ),
    "dark": dict(
        fire="#E8590C",
        flashover="#D6409F",
        air="#4C8DF6",
        heat="#E0484A",
        detector="#0D9488",
        smoke="#9CA3AF",
        reference="#6B7586",
        text="#9AA3B2",
        surface="#11151C",
        safe="#4ADE80",
        smoke_thin="#E5E7EB",  # on a dark page, smoke is drawn light so it stays visible
        smoke_thick="#7E848D",
        floor="#4A4034",
        wall="#2B323D",
        furniture="#6A5E55",
    ),
}

GROWTH_NAMES = {"slow": "Slow", "medium": "Medium", "fast": "Fast", "ultrafast": "Ultrafast"}


def round_half_up(x):
    """Round like a calculator (2.5 -> 3). Python's round() would give 2."""
    return math.floor(x + 0.5)


def seconds(t, missing="Not reached"):
    """Format a time in s for display, or `missing` if it never happens."""
    return missing if t is None else f"{round_half_up(t):,} s"


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


class ChartKit:
    """Shared look and label helpers for one set of charts (one theme, one t_end)."""

    def __init__(self, colors, t_end):
        self.colors = colors
        self.t_end = t_end
        self.times = list(range(t_end + 1))  # one point per second, matching the model

    def new_chart(self, y_title, y_top, y_format):
        """An empty chart: time on x, one y-axis, a hover crosshair."""
        fig = go.Figure()
        fig.update_layout(
            height=360,
            margin=dict(l=8, r=8, t=16, b=8),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0, traceorder="normal"),
        )
        fig.update_xaxes(title_text="Time since ignition (s)", range=[0, self.t_end],
                         unifiedhovertitle=dict(text="t = %{x} s"))
        fig.update_yaxes(title_text=y_title, range=[0, y_top], tickformat=y_format)
        return fig

    def label(self, fig, x, y, text, xanchor="left", yanchor="bottom", xshift=0, yshift=0, textangle=0):
        """A direct label in the text color, on a see-through page-colored background
        so it stays readable if a line passes behind it."""
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False, xanchor=xanchor, yanchor=yanchor,
            xshift=xshift, yshift=yshift, textangle=textangle,
            font=dict(color=self.colors["text"], size=12), bgcolor=rgba(self.colors["surface"], 0.8),
        )

    def label_line(self, fig, y, text, curves, y_top):
        """Label a horizontal line at height y where the fewest curves cross the text.

        Tries six spots (right, left or middle; above or below the line) and counts
        how many points of `curves` (lists with one value per second) would fall
        under the label. The spot with the fewest wins, in that order of preference.
        """
        t_end = self.t_end
        width = min(0.6, 0.009 * len(text) + 0.02) * t_end  # ~0.9% of the width per character
        text_height = 0.09 * y_top
        spots = {
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
                hits = sum(low <= curve[t] <= high for curve in curves for t in range(int(t0), int(t1) + 1)
                           if curve[t] is not None)
                if best is None or hits < best[0]:
                    best = (hits, anchor, x, above)
        if best is None:
            best = (0, "right", t_end, True)
        _, anchor, x, above = best
        self.label(fig, x, y, text, xanchor=anchor, yanchor="bottom" if above else "top",
                   xshift={"right": -6, "left": 6, "center": 0}[anchor], yshift=0 if above else -2)

    def threshold_line(self, fig, y, text, curves, y_top):
        """A gray dashed horizontal threshold line with a direct label."""
        self.threshold_lines(fig, [(y, text)], curves, y_top)

    def threshold_lines(self, fig, lines, curves, y_top):
        """Several gray dashed threshold lines, each given as (y, label text).
        Each label avoids the curves and every OTHER threshold line, so labels of
        lines that sit close together don't land on top of each other's line."""
        flat = [[y] * len(self.times) for y, _ in lines]
        for n, (y, text) in enumerate(lines):
            fig.add_hline(y=y, line=dict(color=self.colors["reference"], width=1, dash="dash"))
            others = [line for m, line in enumerate(flat) if m != n]
            self.label_line(fig, y, text, curves + others, y_top)

    def event_lines(self, fig, events, y_top):
        """Vertical lines for moments in time, e.g. ASET and RSET.

        events: list of (time s, short label, legend name, color, dash). Labels run
        vertically beside each line, on its right, except that when two lines are
        very close the earlier one's label goes on its left so neither crosses the
        other line.
        """
        events = sorted((e for e in events if e[0] is not None and e[0] <= self.t_end), key=lambda e: e[0])
        for i, (t, short, long_name, color, dash) in enumerate(events):
            close_to_next = i + 1 < len(events) and events[i + 1][0] - t < 0.04 * self.t_end
            on_left = close_to_next or t > 0.97 * self.t_end
            fig.add_trace(go.Scatter(x=[t, t], y=[0, y_top], mode="lines", name=f"{long_name} {seconds(t)}",
                                     line=dict(color=color, width=2, dash=dash), hoverinfo="skip",
                                     legendrank=10 + i))
            self.label(fig, t, y_top, f"{short} {seconds(t)}", textangle=-90,
                       xanchor="right" if on_left else "left", yanchor="top", xshift=-3 if on_left else 3)


def hrr_chart(kit, result, units, growth_key, peak_hrr, unprotected=None):
    """Chart 1 (Steps 1 and 3): fire size over time, flashover range, air supply
    limit, the other growth classes, and (with a sprinkler) the unprotected fire."""
    c, t_end, times = kit.colors, kit.t_end, kit.times

    def show(kw):
        """A fire size in kW, converted to the display unit."""
        return units.show("hrr", kw)

    hrr = units.series("hrr", result.hrr)
    fo_sizes = [show(m.threshold_hrr) for m in result.flashover if m.threshold_hrr is not None]
    q_vent = show(result.ventilation_limit)
    peak = show(peak_hrr)
    y_top = nice_axis_top(max(peak, min(q_vent, peak * 1.6), *fo_sizes) * 1.12)
    fig = kit.new_chart(f"Heat release rate ({units.unit('hrr')})", y_top, ",.0f")
    show_vent_line = q_vent <= y_top

    # Every curve on the chart, one value per second, so labels can avoid them.
    other_classes = [key for key in GROWTH_TIMES if key != growth_key]
    curves = [hrr] + [[show(growth_coefficient(GROWTH_TIMES[k]) * t**2) for t in times] for k in other_classes]
    if unprotected is not None:
        curves.append(units.series("hrr", unprotected.hrr))

    if fo_sizes:
        low, high = min(fo_sizes), max(fo_sizes)
        high = max(high, low + y_top * 0.005)  # keep a single-value band visible
        fig.add_trace(go.Scatter(x=[0, t_end], y=[low, low], mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=[0, t_end], y=[high, high], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=rgba(c["flashover"], 0.22),
                                 name="Flashover range (3 methods)", hoverinfo="skip", legendrank=3))
        kit.label_line(fig, high, f"Flashover range {min(fo_sizes):,.0f}–{max(fo_sizes):,.0f} {units.unit('hrr')}",
                       curves + ([[q_vent] * len(times)] if show_vent_line else []), y_top)

    if show_vent_line:
        fig.add_trace(go.Scatter(x=[0, t_end], y=[q_vent] * 2, mode="lines",
                                 line=dict(color=c["air"], width=1.5, dash="dash"),
                                 name="Air supply limit", hoverinfo="skip", legendrank=4))
        kit.label_line(fig, q_vent, f"Air supply limit {q_vent:,.0f} {units.unit('hrr')}", curves, y_top)

    first = True
    for key in other_classes:
        a = show(growth_coefficient(GROWTH_TIMES[key]))  # in display units per s^2
        t_exit = math.sqrt(y_top / a)  # when alpha t^2 leaves the top of the chart
        ts = [min(t_end, t_exit) * i / 100 for i in range(101)]
        fig.add_trace(go.Scatter(x=ts, y=[a * t**2 for t in ts], mode="lines",
                                 line=dict(color=c["reference"], width=1.2, dash="dash"),
                                 name="Other growth rates", legendgroup="other",
                                 showlegend=first, hoverinfo="skip", legendrank=5))
        first = False
        if t_exit < t_end:
            kit.label(fig, t_exit, y_top, GROWTH_NAMES[key], yanchor="top", xshift=4)
        else:
            kit.label(fig, t_end, a * t_end**2, GROWTH_NAMES[key], xanchor="right", xshift=-4)

    if unprotected is not None:
        fig.add_trace(go.Scatter(x=times, y=units.series("hrr", unprotected.hrr), mode="lines",
                                 name="Same fire without the sprinkler", line=dict(color=c["fire"], width=1.5, dash="dot"),
                                 hovertemplate=f"%{{y:,.0f}} {units.unit('hrr')}", legendrank=2))
    if result.sprinkler_time is not None:
        kit.event_lines(fig, [(result.sprinkler_time, "Sprinkler", "Sprinkler activates", c["air"], "dot")], y_top)

    fig.add_trace(go.Scatter(x=times, y=hrr, mode="lines", name="Your fire",
                             line=dict(color=c["fire"], width=2.5),
                             fill="tozeroy", fillcolor=rgba(c["fire"], 0.10),
                             hovertemplate=f"%{{y:,.0f}} {units.unit('hrr')}", legendrank=1))
    return fig


def temperature_chart(kit, result, units, sprinkler=None, heat_detector=None):
    """Chart 2 (Step 2): MQH smoke layer temperature, plus the sprinkler and heat
    detector element temperatures when those devices are installed."""
    c, times = kit.colors, kit.times
    temps = units.series("temperature", result.layer_temp)
    limit = units.show("temperature", MQH_UPPER_LIMIT)
    tenable = units.show("temperature", TENABILITY_TEMP)
    y_top = nice_axis_top(max(max(temps) * 1.08, units.show("temperature", 700)))
    fig = kit.new_chart(f"Temperature ({units.unit('temperature')})", y_top, ",.0f")
    curves = [temps]

    devices = []
    if sprinkler is not None and result.sprinkler_temps is not None:
        devices.append((sprinkler, result.sprinkler_temps, result.sprinkler_time, "Sprinkler", c["air"]))
    if heat_detector is not None and result.heat_detector_temps is not None:
        devices.append((heat_detector, result.heat_detector_temps, result.heat_detector_time, "Heat detector", c["detector"]))
    for _, device_temps, _, _, _ in devices:
        curves.append(units.series("temperature", device_temps))

    # Above 600 °C the MQH correlation is outside the range it was fitted to.
    fig.add_hrect(y0=limit, y1=y_top, fillcolor=c["heat"], opacity=0.06, line_width=0)
    thresholds = [
        (tenable, f"{units.fmt('temperature', TENABILITY_TEMP)} · painful radiant heat below"),
        (limit, f"{units.fmt('temperature', MQH_UPPER_LIMIT)} · flashover likely; MQH not fitted above"),
    ] + [(units.show("temperature", device.activation_temp),
          f"{name} rating {units.fmt('temperature', device.activation_temp)}")
         for device, _, _, name, _ in devices]
    kit.threshold_lines(fig, thresholds, curves, y_top)

    if result.penetration_time < kit.t_end:
        fig.add_vline(x=result.penetration_time, line=dict(color=c["reference"], width=1, dash="dot"))
        kit.label(fig, result.penetration_time, 0, "t<sub>p</sub>", xanchor="right", xshift=-4, yshift=4)

    # Solid line up to 600 °C, dotted above it, joined at the crossing.
    in_range = [T if T <= limit else None for T in temps]
    out_of_range = [T if T > limit else None for T in temps]
    for t in range(1, len(temps)):
        if out_of_range[t] is not None and out_of_range[t - 1] is None:
            out_of_range[t - 1] = temps[t - 1]
    unit = units.unit("temperature")
    fig.add_trace(go.Scatter(x=times, y=in_range, mode="lines", name="Smoke layer temperature",
                             line=dict(color=c["heat"], width=2.5), hovertemplate=f"%{{y:,.0f}} {unit}", legendrank=1))
    if any(T is not None for T in out_of_range):
        fig.add_trace(go.Scatter(x=times, y=out_of_range, mode="lines", name="Above 600 °C, outside the method's range",
                                 line=dict(color=c["heat"], width=2.5, dash="dot"),
                                 hovertemplate=f"%{{y:,.0f}} {unit}", legendrank=2))

    # Device element temperatures, each with its activation rating.
    for i, (device, device_temps, activation, name, color) in enumerate(devices):
        fig.add_trace(go.Scatter(x=times, y=units.series("temperature", device_temps), mode="lines",
                                 name=f"{name} element temperature", line=dict(color=color, width=2),
                                 hovertemplate=f"%{{y:,.0f}} {unit}", legendrank=3 + i))
    kit.event_lines(fig, [(activation, name, f"{name} activates", color, "dot")
                          for _, _, activation, name, color in devices], y_top)
    return fig


def height_chart(kit, result, room, units):
    """Chart 3 (Step 4): the bottom of the smoke layer over time, with ASET and RSET."""
    c, times = kit.colors, kit.times
    heights = units.series("length", result.layer_height)
    ceiling = units.show("length", room.height)
    y_top = nice_axis_top(ceiling * 1.05, n_ticks=6) if units.us else math.ceil(room.height * 2) / 2
    fig = kit.new_chart(f"Height above floor ({units.unit('length')})", y_top, ".1f")

    # Shade the smoke: fill from the ceiling down to the bottom of the layer.
    fig.add_trace(go.Scatter(x=times, y=[ceiling] * len(times), mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=times, y=heights, mode="lines", name="Bottom of smoke layer",
                             line=dict(color=c["smoke"], width=2.5),
                             fill="tonexty", fillcolor=rgba(c["smoke"], 0.18),
                             hovertemplate=f"%{{y:.2f}} {units.unit('length')}", legendrank=1))

    thresholds = [(units.show("length", HEAD_HEIGHT), f"{units.fmt('length', HEAD_HEIGHT, 1)} · head height")]
    if abs(room.door_height - HEAD_HEIGHT) > 0.12 and units.show("length", room.door_height) < y_top:
        thresholds.append((units.show("length", room.door_height), "Top of door"))
    kit.threshold_lines(fig, thresholds, [heights], y_top)

    kit.event_lines(fig, [
        (result.aset, "ASET", "Untenable (ASET)", c["heat"], "solid"),
        (result.rset, "RSET", "Everyone out (RSET)", c["air"], "solid"),
    ], y_top)
    return fig
