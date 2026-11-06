"""
3D view of the room for the app: a picture of the model's results.

This is NOT a 3D fire simulation (that would be CFD, e.g. NIST's FDS, which splits
the room into many small cells). It draws what the two-zone model and its
correlations calculate:

  * the smoke layer: one flat, uniform slab from the ceiling down to the layer
    height z(t), colored gray to red with its temperature (exactly the two-zone
    assumption: one layer, one temperature);
  * the flames: a cone with Heskestad's flame height L = 0.235 Q^(2/5) - 1.02 D
    (cut off at the ceiling). The burning diameter D grows with the fire,
    D = D_full * sqrt(Q / Q_peak), as a t-squared fire spreads;
  * the plume rising from the flame tip into the smoke layer (shape illustrative);
  * smoke spilling out of the top of the door once the layer is below the door top;
  * a sprinkler and/or heat detector on the ceiling at the distance set from the
    fire, with the sprinkler spray shown once it activates;
  * the occupant walking to the door on the RSET timeline;
  * a dashed line at 1.8 m, the tenability head height.
"""

import math
from dataclasses import replace

import plotly.graph_objects as go

from fire_model.egress import HEAD_HEIGHT, distance_left_to_walk, occupant_status
from fire_model.layer_temp import T_AMBIENT
from fire_model.growth import burning_diameter
from fire_model.smoke_filling import flame_height

MAX_FRAMES = 121  # about one frame every 5 s for a 600 s simulation
SEGMENTS = 16  # sides used to draw round shapes (flames, plume, spray)


def _box(x0, x1, y0, y1, z0, z1):
    """Corner points and triangles of a rectangular box, for go.Mesh3d.
    Each of the 6 faces is made of 2 triangles; i, j, k list their corners."""
    return dict(
        x=[x0, x1, x1, x0, x0, x1, x1, x0],
        y=[y0, y0, y1, y1, y0, y0, y1, y1],
        z=[z0, z0, z0, z0, z1, z1, z1, z1],
        i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3],
        j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
        k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
    )


def _cone(cx, cy, z_bottom, r_bottom, z_top, r_top):
    """The side of a (possibly cut-off) cone, for go.Mesh3d: flames, plume, spray."""
    x, y, z, i, j, k = [], [], [], [], [], []
    for s in range(SEGMENTS):
        angle = 2 * math.pi * s / SEGMENTS
        x += [cx + r_bottom * math.cos(angle), cx + r_top * math.cos(angle)]
        y += [cy + r_bottom * math.sin(angle), cy + r_top * math.sin(angle)]
        z += [z_bottom, z_top]
        b0, t0 = 2 * s, 2 * s + 1
        b1, t1 = (2 * s + 2) % (2 * SEGMENTS), (2 * s + 3) % (2 * SEGMENTS)
        i += [b0, t0]
        j += [b1, b1]
        k += [t0, t1]
    return dict(x=x, y=y, z=z, i=i, j=j, k=k)


def _mix(hex_a, hex_b, f):
    """Color part-way between two '#RRGGBB' colors (f = 0 gives a, 1 gives b)."""
    a = [int(hex_a[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i : i + 2], 16) for i in (1, 3, 5)]
    r, g, bl = (round(p + (q - p) * f) for p, q in zip(a, b))
    return f"rgb({r},{g},{bl})"


def _loop(x, y, z):
    """Close a list of corner points into a loop for a line trace."""
    return x + x[:1], y + y[:1], z + z[:1]


def _ceiling_spot(fire_x, fire_y, toward_x, toward_y, distance, L, W):
    """A point `distance` from the fire, heading toward (toward_x, toward_y), kept inside the room."""
    dx, dy = toward_x - fire_x, toward_y - fire_y
    length = math.hypot(dx, dy) or 1.0
    x = fire_x + distance * dx / length
    y = fire_y + distance * dy / length
    return min(max(x, 0.1), L - 0.1), min(max(y, 0.1), W - 0.1)


def room_3d_figure(result, room, occupant, colors, units, start_time=120, fire_diameter=1.0,
                   peak_hrr=None, sprinkler=None, heat_detector=None):
    """Build the animated 3D view. `result` is a fire_model ScenarioResult.

    fire_diameter is the burning diameter at full size (m), reached at the fuel's
    peak HRR `peak_hrr` (kW; defaults to the largest fire in the result).
    All geometry is worked out in metres and scaled to the display unit."""
    if peak_hrr is None:
        peak_hrr = max(result.hrr)
    L, W, H = room.length, room.width, room.height
    s = units.show("length", 1.0)  # metres -> display length unit
    t_end = result.t_end
    door_y = min(max(0.6 * W, room.door_width / 2), W - room.door_width / 2)  # door centre on the x = L wall
    half_door = room.door_width / 2
    fire_x, fire_y = 0.28 * L, 0.3 * W
    sprinkler_xy = _ceiling_spot(fire_x, fire_y, 0.5 * L, 0.5 * W, sprinkler.radial_distance, L, W) if sprinkler else None
    detector_xy = _ceiling_spot(fire_x, fire_y, 0.75 * L, 0.8 * W, heat_detector.radial_distance, L, W) if heat_detector else None
    # The occupant as alerted in this scenario: their detection time is when the
    # alarm actually sounds (a heat detector can change it). None: never alerted.
    alerted = replace(occupant, detection_time=result.alarm_time) if result.alarm_time is not None else None

    def sc(values):
        return [None if v is None else v * s for v in values]

    def mesh(d, **extra):
        """Scale a mesh dictionary's coordinates to display units."""
        return dict(d, x=sc(d["x"]), y=sc(d["y"]), z=sc(d["z"]), **extra)

    def state(t):
        """Every moving part at whole second t, plus the caption."""
        z, temp, q = result.layer_height[t], result.layer_temp[t], result.hrr[t]
        heat = max(0.0, min(1.0, (temp - T_AMBIENT) / 600))
        smoke_color = _mix(colors["smoke"], colors["heat"], heat)
        has_smoke = z < H - 0.01
        parts = []

        # Smoke layer: one uniform slab hanging from the ceiling.
        parts.append(mesh(_box(0, L, 0, W, min(z, H - 0.01), H), color=smoke_color,
                          opacity=(0.25 + 0.45 * heat) if has_smoke else 0.0, name="Smoke layer"))
        # Smoke spilling out of the top of the door once the layer is below the door top.
        spilling = has_smoke and z < room.door_height
        parts.append(mesh(_box(L, L + 0.6, door_y - half_door, door_y + half_door,
                               min(z, room.door_height - 0.01), room.door_height),
                          color=smoke_color, opacity=0.3 * (0.6 + heat) if spilling else 0.0,
                          name="Smoke leaving through the door"))

        # Flames: Heskestad flame height for the area burning now, cut off at the ceiling.
        diameter = burning_diameter(q, peak_hrr, fire_diameter)
        flames = min(flame_height(q, diameter), H)
        radius = diameter / 2
        parts.append(mesh(_cone(fire_x, fire_y, 0, radius, max(flames, 0.02), 0.0), color=colors["fire"],
                          opacity=0.85 if q > 0 else 0.0, name="Flames"))
        parts.append(mesh(_cone(fire_x, fire_y, 0, radius * 0.5, max(flames * 0.6, 0.01), 0.0),
                          color=_mix(colors["fire"], "#FDE68A", 0.7), opacity=0.9 if q > 0 else 0.0,
                          name="Flames (core)"))
        # Plume: from the flame tip up to the smoke layer, widening as it rises.
        plume_top = min(z, H) if has_smoke else H
        rising = q > 0 and plume_top > flames + 0.05
        parts.append(mesh(_cone(fire_x, fire_y, min(flames, H - 0.02), radius * 0.6,
                                max(plume_top, flames + 0.01), radius * 0.6 + 0.2 * max(0.0, plume_top - flames)),
                          color=colors["smoke"], opacity=0.15 if rising else 0.0, name="Plume"))

        # Sprinkler spray, once it has activated.
        if sprinkler is not None:
            on = result.sprinkler_time is not None and t >= result.sprinkler_time
            sx, sy = sprinkler_xy
            parts.append(mesh(_cone(sx, sy, max(H - 1.3, 0.1), 1.0, H - 0.05, 0.05), color=colors["air"],
                              opacity=0.18 if on else 0.0, name="Sprinkler spray"))

        # Occupant: a simple figure walking along the room toward the door, on the
        # RSET timeline (alarm, reaction, walking).
        if alerted is None:  # a heat detector alarm that never sounds
            out, status = False, "No alarm: the heat detector has not activated"
            px = max(0.25, L - 0.25 - occupant.walk_distance)
        else:
            out = t >= result.rset
            status = occupant_status(t, alerted)
            px = L + 0.5 if out else max(0.25, L - 0.25 - distance_left_to_walk(t, alerted))
        untenable = result.aset is not None and t >= result.aset
        person_color = colors["safe"] if out else colors["heat"] if untenable else colors["air"]
        if untenable and not out:
            status += " · room untenable"
        parts.append(dict(type="scatter3d", x=sc([px, px]), y=sc([door_y, door_y]), z=sc([0.0, 1.45]),
                          mode="lines", line=dict(color=person_color, width=14), name="Occupant"))
        parts.append(dict(type="scatter3d", x=sc([px]), y=sc([door_y]), z=sc([1.62]), mode="markers",
                          marker=dict(color=person_color, size=9), name="Occupant (head)", showlegend=False))

        # Devices on the ceiling: hollow before activation, filled after.
        events = []
        for device, xy, activation, name, color in (
            (sprinkler, sprinkler_xy, result.sprinkler_time, "Sprinkler", colors["air"]),
            (heat_detector, detector_xy, result.heat_detector_time, "Heat detector", colors["detector"]),
        ):
            if device is None:
                continue
            on = activation is not None and t >= activation
            if on:
                events.append(f"{name.lower()} activated")
            parts.append(dict(type="scatter3d", x=sc([xy[0]]), y=sc([xy[1]]), z=sc([H - 0.02]), mode="markers",
                              marker=dict(color=color, size=8 if on else 6, symbol="circle" if on else "circle-open",
                                          line=dict(color=color, width=3)), name=name))

        line1 = (f"<b>t = {t} s</b> · fire {units.fmt('hrr', q)} · flames {units.fmt('length', flames, 1)} tall"
                 + ("".join(f" · {e}" for e in events)))
        line2 = (f"smoke {units.fmt('temperature', temp)}, bottom at {units.fmt('length', z, 2)} · {status}")
        return parts, f"{line1}<br>{line2}"

    # One frame every `step` seconds. The grid point nearest the start time is
    # swapped for the exact start time, so the first view is exact and the
    # slider's steps stay evenly spaced.
    step = max(1, math.ceil(t_end / (MAX_FRAMES - 1)))
    start = int(min(start_time, t_end))
    frame_times = list(range(0, t_end + 1, step))
    if frame_times[-1] != t_end:
        frame_times.append(t_end)
    if start not in frame_times:
        nearest = min(range(len(frame_times)), key=lambda n: abs(frame_times[n] - start))
        frame_times[nearest] = start
        frame_times.sort()

    def as_trace(part):
        part = dict(part)
        if part.pop("type", None) == "scatter3d":
            return go.Scatter3d(hoverinfo="skip", **part)
        return go.Mesh3d(flatshading=True, hoverinfo="skip", **part)

    # Static parts: floor, room edges, door frame, head-height line.
    xs, ys, zs = [], [], []
    for zz in (0, H):
        x, y, z = _loop([0, L, L, 0], [0, 0, W, W], [zz] * 4)
        xs += x + [None]; ys += y + [None]; zs += z + [None]
    for x, y in ((0, 0), (L, 0), (L, W), (0, W)):
        xs += [x, x, None]; ys += [y, y, None]; zs += [0, H, None]
    door = _loop([L] * 4, [door_y - half_door, door_y + half_door, door_y + half_door, door_y - half_door],
                 [0, 0, room.door_height, room.door_height])
    head = _loop([0, L, L, 0], [0, 0, W, W], [HEAD_HEIGHT] * 4)
    static = [
        go.Mesh3d(**mesh(_box(0, L, 0, W, 0, 0.001)), color=colors["reference"], opacity=0.25,
                  name="Floor", showlegend=False, hoverinfo="skip"),
        go.Scatter3d(x=sc(xs), y=sc(ys), z=sc(zs), mode="lines", line=dict(color=colors["reference"], width=3),
                     name="Room", showlegend=False, hoverinfo="skip"),
        go.Scatter3d(x=sc(door[0]), y=sc(door[1]), z=sc(door[2]), mode="lines",
                     line=dict(color=colors["text"], width=6), name="Door", hoverinfo="skip"),
        go.Scatter3d(x=sc(head[0]), y=sc(head[1]), z=sc(head[2]), mode="lines",
                     line=dict(color=colors["text"], width=2, dash="dash"),
                     name=f"{units.fmt('length', HEAD_HEIGHT, 1)} head height", hoverinfo="skip"),
    ]
    parts, caption = state(start)
    legend_names = {"Smoke layer", "Flames", "Occupant", "Sprinkler", "Heat detector"}
    moving = [as_trace(dict(p, showlegend=p.get("showlegend", p["name"] in legend_names))) for p in parts]
    fig = go.Figure(data=static + moving)
    moving_indices = list(range(len(static), len(static) + len(moving)))

    frames = []
    for t in frame_times:
        f_parts, f_caption = state(t)
        frames.append(go.Frame(name=str(t), data=[as_trace(p) for p in f_parts], traces=moving_indices,
                               layout=dict(title=dict(text=f_caption))))
    fig.frames = frames

    span_x, span_y, span_z = (L + 1.2) * s, (W + 0.4) * s, (H + 0.1) * s
    biggest = max(span_x, span_y, span_z)
    play_args = dict(frame=dict(duration=90, redraw=True), transition=dict(duration=0),
                     fromcurrent=True, mode="immediate")
    unit = units.unit("length")
    fig.update_layout(
        height=600,
        margin=dict(l=0, r=0, t=84, b=72),
        title=dict(text=caption, x=0.01, xanchor="left", y=0.985, yanchor="top",
                   font=dict(size=13, color=colors["text"])),
        legend=dict(orientation="h", x=0.0, xanchor="left", y=1.0, yanchor="bottom"),
        scene=dict(
            xaxis=dict(title=f"Length ({unit})", range=[-0.2 * s, (L + 1.0) * s], showbackground=False),
            yaxis=dict(title=f"Width ({unit})", range=[-0.2 * s, (W + 0.2) * s], showbackground=False),
            zaxis=dict(title=f"Height ({unit})", range=[0, (H + 0.1) * s], showbackground=False),
            aspectmode="manual",
            aspectratio=dict(x=span_x / biggest, y=span_y / biggest, z=span_z / biggest),
            camera=dict(eye=dict(x=0.9, y=-1.25, z=0.62)),
        ),
        updatemenus=[dict(
            type="buttons", direction="left", x=0.0, y=0.0, xanchor="left", yanchor="top",
            pad=dict(t=28, r=8), showactive=False,
            buttons=[
                dict(label="▶ Play", method="animate", args=[None, play_args]),
                dict(label="❚❚ Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
            ],
        )],
        sliders=[dict(
            active=frame_times.index(start), x=0.17, len=0.83, y=0.0, yanchor="top",
            pad=dict(t=10, b=0), currentvalue=dict(visible=False),
            # Plotly shows every Nth label so they don't overlap.
            steps=[dict(label=str(t), method="animate",
                        args=[[str(t)], dict(frame=dict(duration=0, redraw=True), mode="immediate")])
                   for t in frame_times],
        )],
    )
    return fig
