"""
3D view of the room for the app: a picture of the model's results.

This is NOT a 3D fire simulation (that would be CFD, e.g. NIST's FDS, which splits
the room into many small cells). It draws, to scale, what the two-zone model and
its correlations calculate, and adds a few illustrative details so the room is
easy to read. What is calculated and what is only drawn:

  Calculated by the model
  * smoke layer: depth from the ceiling down to z(t), and its temperature, which
    sets its color (gray when cool, charcoal when hot, glowing red above ~525 °C,
    the Draper point where hot soot starts to glow). One uniform slab, as the
    two-zone model assumes.
  * flames: Heskestad's flame height L = 0.235 Q^(2/5) - 1.02 D, with the burning
    diameter growing with the fire, D = D_full * sqrt(Q / Q_peak);
  * smoke pouring out of the top of the door once the layer is below the door top;
  * when the sprinkler activates (then its water spray is shown) and when the heat
    detector activates;
  * the occupant's position on the RSET timeline.

  Drawn for realism only
  * the burning furniture (illustrative size; the calculation puts the fire at
    floor level, which is slightly cautious), the cutaway walls and hallway;
  * the plume's shape, the soft lower edge of the smoke layer (the model treats
    it as a sharp boundary), flames spreading under the ceiling, the sprinkler
    droplets, and the fresh air flowing in at the bottom of the door (real, but
    not part of this model).
"""

import math
from dataclasses import replace

import plotly.graph_objects as go

from charts import rgba
from fire_model.egress import HEAD_HEIGHT, distance_left_to_walk, occupant_status
from fire_model.growth import burning_diameter
from fire_model.layer_temp import T_AMBIENT, is_within_mqh_range
from fire_model.smoke_filling import door_outflow, flame_height, kelvin

MAX_FRAMES = 121  # about one frame every 5 s for a 600 s simulation
SEGMENTS = 14  # sides used to draw round shapes (flames, plume)
DRAPER_POINT = 525.0  # °C, where hot objects (and soot) start to glow visibly
GLOW_FULL = 800.0  # °C, drawn fully glowing

# Illustrative furniture, as boxes (x0, x1, y0, y1, z0, z1) around the fire centre,
# and the height of the burning surface the flames start from (m).
FURNITURE = {
    "Wastebasket": ([(-0.15, 0.15, -0.15, 0.15, 0.0, 0.40)], 0.40),
    "Office chair": ([(-0.25, 0.25, -0.25, 0.25, 0.35, 0.45), (-0.04, 0.04, -0.04, 0.04, 0.0, 0.35),
                      (-0.25, 0.25, 0.20, 0.27, 0.45, 0.95)], 0.45),
    "Upholstered armchair": ([(-0.42, 0.42, -0.42, 0.42, 0.0, 0.45), (-0.42, 0.42, 0.25, 0.42, 0.45, 0.90),
                              (-0.42, -0.30, -0.42, 0.25, 0.45, 0.65), (0.30, 0.42, -0.42, 0.25, 0.45, 0.65)], 0.45),
    "Sofa": ([(-1.0, 1.0, -0.45, 0.45, 0.0, 0.45), (-1.0, 1.0, 0.25, 0.45, 0.45, 0.85),
              (-1.0, -0.85, -0.45, 0.25, 0.45, 0.65), (0.85, 1.0, -0.45, 0.25, 0.45, 0.65)], 0.45),
    "Mattress and bed": ([(-1.0, 1.0, -0.75, 0.75, 0.0, 0.55), (-1.05, -1.0, -0.75, 0.75, 0.0, 1.0)], 0.55),
}
GENERIC_FURNITURE = ([(-0.5, 0.5, -0.5, 0.5, 0.0, 0.45)], 0.45)


# ---------------------------------------------------------------------------
# Shapes (corner points and triangles for go.Mesh3d)
# ---------------------------------------------------------------------------

def _box(x0, x1, y0, y1, z0, z1):
    """A rectangular box. Each of the 6 faces is 2 triangles; i, j, k list their corners."""
    return dict(
        x=[x0, x1, x1, x0, x0, x1, x1, x0],
        y=[y0, y0, y1, y1, y0, y0, y1, y1],
        z=[z0, z0, z0, z0, z1, z1, z1, z1],
        i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3],
        j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
        k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
    )


def _boxes(boxes):
    """Several boxes joined into one shape (one trace)."""
    shape = dict(x=[], y=[], z=[], i=[], j=[], k=[])
    for b in boxes:
        one, offset = _box(*b), len(shape["x"])
        for axis in "xyz":
            shape[axis] += one[axis]
        for corner in "ijk":
            shape[corner] += [n + offset for n in one[corner]]
    return shape


def _cone(cx, cy, z_bottom, r_bottom, z_top, r_top):
    """The side of a (possibly cut-off) cone: flames, plume."""
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


def _mix(color_a, color_b, f):
    """Color part-way between two '#RRGGBB' colors (f = 0 gives a, 1 gives b)."""
    a = [int(color_a[n : n + 2], 16) for n in (1, 3, 5)]
    b = [int(color_b[n : n + 2], 16) for n in (1, 3, 5)]
    return "#" + "".join(f"{round(p + (q - p) * f):02x}" for p, q in zip(a, b))


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


def smoke_color(temp, colors):
    """Smoke color for a layer temperature (°C): thin gray, darkening as it heats,
    and glowing toward the fire color above the Draper point."""
    darkness = max(0.0, min(1.0, (temp - T_AMBIENT) / 400))
    glow = max(0.0, min(1.0, (temp - DRAPER_POINT) / (GLOW_FULL - DRAPER_POINT)))
    return _mix(_mix(colors["smoke_thin"], colors["smoke_thick"], darkness), colors["fire"], 0.75 * glow)


def room_3d_figure(result, room, occupant, colors, units, start_time=120, fire_diameter=1.0,
                   peak_hrr=None, sprinkler=None, heat_detector=None, fuel=None):
    """Build the animated 3D view. `result` is a fire_model ScenarioResult.

    fire_diameter is the burning diameter at full size (m), reached at the fuel's
    peak HRR `peak_hrr` (kW; defaults to the largest fire in the result). `fuel`
    picks the furniture drawn under the flames. All geometry is worked out in
    metres and scaled to the display unit.
    """
    if peak_hrr is None:
        peak_hrr = max(result.hrr)
    L, W, H = room.length, room.width, room.height
    s = units.show("length", 1.0)  # metres -> display length unit
    t_end = result.t_end
    door_y = min(max(0.6 * W, room.door_width / 2), W - room.door_width / 2)  # door centre on the x = L wall
    half_door = room.door_width / 2
    fire_x, fire_y = 0.28 * L, 0.3 * W

    # Furniture, shrunk if the room is small, and the height its top burns at.
    boxes, surface = FURNITURE.get(fuel, GENERIC_FURNITURE)
    shrink = min(1.0, 0.45 * L / max(b[1] - b[0] for b in boxes), 0.45 * W / max(b[3] - b[2] for b in boxes))
    furniture = [(fire_x + shrink * b[0], fire_x + shrink * b[1], fire_y + shrink * b[2], fire_y + shrink * b[3],
                  b[4], b[5]) for b in boxes]

    sprinkler_xy = _ceiling_spot(fire_x, fire_y, 0.5 * L, 0.5 * W, sprinkler.radial_distance, L, W) if sprinkler else None
    detector_xy = _ceiling_spot(fire_x, fire_y, 0.75 * L, 0.8 * W, heat_detector.radial_distance, L, W) if heat_detector else None
    # The occupant as alerted in this scenario: their detection time is when the
    # alarm actually sounds (a heat detector can change it). None: never alerted.
    alerted = replace(occupant, detection_time=result.alarm_time) if result.alarm_time is not None else None

    # Sprinkler water: a fixed pattern of droplets in a cone below the head.
    droplets = []
    for n in range(70):
        depth = 0.15 + 1.05 * ((n * 0.37) % 1.0)  # m below the ceiling
        radius = 0.75 * depth * math.sqrt((n + 0.5) / 70)
        angle = n * 2.39996  # golden angle spreads the droplets evenly
        droplets.append((radius * math.cos(angle), radius * math.sin(angle), depth))

    def sc(values):
        """Scale metres to the display unit, rounded to about a millimetre (keeps the page small)."""
        return [None if v is None else round(v * s, 3) for v in values]

    def mesh(d, **extra):
        """A shape scaled to display units (in frames, only the moving parts are sent)."""
        return dict(d, x=sc(d["x"]), y=sc(d["y"]), z=sc(d["z"]), **extra)

    def callout(x, y, z, text, ax=0, ay=0):
        """A label pinned to a point in the room (metres). It is drawn on top of the 3D
        picture, so smoke never hides it, and it follows the point when the view is
        turned. ax, ay: where the label sits relative to the point, in screen pixels;
        a thin line then points from the label to the point."""
        point = sc([x, y, z])
        return dict(x=point[0], y=point[1], z=point[2], text=text, showarrow=bool(ax or ay), ax=ax, ay=ay,
                    arrowhead=0, arrowwidth=1, arrowcolor=colors["text"], font=dict(size=11, color=colors["text"]),
                    bgcolor=rgba(colors["surface"], 0.82), borderpad=2)

    def state(t):
        """Every moving part at whole second t (dicts for traces), and the caption."""
        z, temp, q = result.layer_height[t], result.layer_temp[t], result.hrr[t]
        heat = max(0.0, min(1.0, (temp - T_AMBIENT) / 400))
        color = smoke_color(temp, colors)
        has_smoke = z < H - 0.01
        opacity = (0.3 + 0.45 * heat) if has_smoke else 0.0
        parts = []

        # Smoke layer, with a soft lower edge, and smoke spilling out of the door top.
        parts.append(mesh(_box(0, L, 0, W, min(z, H - 0.01), H), color=color, opacity=opacity, name="Smoke layer"))
        parts.append(mesh(_box(0, L, 0, W, max(0.0, min(z, H - 0.01) - 0.1), min(z, H - 0.01)), color=color,
                          opacity=0.35 * opacity, name="Smoke layer (soft edge)"))
        spilling = has_smoke and z < room.door_height
        parts.append(mesh(_box(L, L + 0.7, door_y - half_door, door_y + half_door, max(z, 0.0),
                               room.door_height + 0.05), color=color, opacity=0.6 * opacity if spilling else 0.0,
                          name="Smoke out of the door"))

        # Flames on the burning furniture: Heskestad flame height for the area burning now.
        diameter = burning_diameter(q, peak_hrr, fire_diameter)
        flames = flame_height(q, diameter)
        top = min(surface + flames, H)
        radius = max(diameter / 2, 0.05)
        on = q > 0
        for name, height_part, radius_part, color_flame, alpha in (
            ("Flames", 1.0, 1.0, colors["fire"], 0.5),
            ("Flames (middle)", 0.75, 0.75, "#F59E0B", 0.7),
            ("Flames (core)", 0.45, 0.45, "#FDE68A", 0.9),
        ):
            tip = surface + max(height_part * (top - surface), 0.03)
            parts.append(mesh(_cone(fire_x, fire_y, surface, radius * radius_part, tip, 0.0),
                              color=color_flame, opacity=alpha if on else 0.0, name=name))
        # Flames reaching the ceiling spread along it (drawn illustratively).
        overshoot = surface + flames - H
        parts.append(mesh(_cone(fire_x, fire_y, H - 0.08, max(radius, min(1.5, 0.5 * overshoot)), H - 0.02, 0.05),
                          color=colors["fire"], opacity=0.55 if on and overshoot > 0 else 0.0,
                          name="Flames under the ceiling"))
        # Plume: from the flame tip up into the smoke layer, widening as it rises.
        plume_top = min(z, H) if has_smoke else H
        rising = on and plume_top > top + 0.05
        parts.append(mesh(_cone(fire_x, fire_y, min(top, H - 0.02), radius * 0.6, max(plume_top, top + 0.01),
                                radius * 0.6 + 0.2 * max(0.0, plume_top - top)),
                          color=colors["smoke_thin"], opacity=0.16 if rising else 0.0, name="Plume"))

        # Sprinkler water, once the sprinkler has activated.
        if sprinkler is not None:
            wet = result.sprinkler_time is not None and t >= result.sprinkler_time
            sx, sy = sprinkler_xy
            parts.append(dict(type="scatter3d", x=sc([sx + dx for dx, _, _ in droplets]),
                              y=sc([sy + dy for _, dy, _ in droplets]), z=sc([H - dz for _, _, dz in droplets]),
                              mode="markers", marker=dict(color=colors["air"], size=3, opacity=0.75 if wet else 0.0),
                              name="Sprinkler water"))

        # Occupant: a stick figure walking along the room toward the door.
        if alerted is None:
            out, status = False, "No alarm: the heat detector has not activated"
            px = max(0.25, L - 0.25 - occupant.walk_distance)
        else:
            out = t >= result.rset
            status = occupant_status(t, alerted)
            px = L + 0.6 if out else max(0.25, L - 0.25 - distance_left_to_walk(t, alerted))
        untenable = result.aset is not None and t >= result.aset
        person_color = colors["safe"] if out else colors["heat"] if untenable else colors["air"]
        if untenable and not out:
            status += " · room untenable"
        py = door_y
        body_x = [px - 0.1, px, px + 0.1, None, px, px, None, px - 0.25, px, px + 0.25]
        body_z = [0.0, 0.85, 0.0, None, 0.85, 1.45, None, 1.0, 1.38, 1.0]
        parts.append(dict(type="scatter3d", x=sc(body_x), y=sc([py] * len(body_x)), z=sc(body_z), mode="lines",
                          line=dict(color=person_color, width=7), name="Occupant"))
        parts.append(dict(type="scatter3d", x=sc([px]), y=sc([py]), z=sc([1.6]), mode="markers",
                          marker=dict(color=person_color, size=9), name="Occupant (head)"))

        # Devices on the ceiling: hollow before activation, filled after.
        events, device_labels = [], []
        for device, xy, activation, temps, name, device_color in (
            (sprinkler, sprinkler_xy, result.sprinkler_time, result.sprinkler_temps, "Sprinkler", colors["air"]),
            (heat_detector, detector_xy, result.heat_detector_time, result.heat_detector_temps, "Heat detector",
             colors["detector"]),
        ):
            if device is None:
                continue
            active = activation is not None and t >= activation
            if active:
                events.append(f"{name.lower()} activated")
            parts.append(dict(type="scatter3d", x=sc([xy[0]]), y=sc([xy[1]]), z=sc([H - 0.03]), mode="markers",
                              marker=dict(color=device_color, size=8 if active else 6,
                                          symbol="circle" if active else "circle-open",
                                          line=dict(color=device_color, width=3)), name=name))
            element = temps[t] if temps is not None else T_AMBIENT
            device_labels.append(callout(xy[0], xy[1], H - 0.03, f"{name}: activated" if active else
                                         f"{name}: {units.fmt('temperature', element)} of "
                                         f"{units.fmt('temperature', device.activation_temp)}", ay=-26))

        # Labels: the regions (smoke, clear air) are labelled on the room's open
        # front side; the objects get a label with a pointer line.
        labels = []
        if has_smoke and H - z > 0.2:
            beyond = "" if is_within_mqh_range(temp) else " (beyond MQH's range)"
            labels.append(callout(0.78 * L, 0, (z + H) / 2, f"Hot smoke · {units.fmt('temperature', temp)}{beyond}"))
        if z > 0.45:
            labels.append(callout(0.78 * L, 0, max(0.2, min(z / 2, HEAD_HEIGHT)), "Clear air"))
        if on:
            reach = " (hit the ceiling)" if overshoot > 0 else ""
            labels.append(callout(fire_x, fire_y, surface + 0.55 * (top - surface),
                                  f"Flames {units.fmt('length', flames, 1)}{reach}", ax=-72, ay=-18))
        if spilling:
            labels.append(callout(L + 0.35, door_y, (max(z, 0.0) + room.door_height) / 2, "Smoke out", ax=48, ay=-26))
            labels.append(callout(L + 0.15, door_y, 0.2, "Fresh air in (not modeled)", ax=56, ay=24))
        else:
            labels.append(callout(L, door_y, 0.5 * room.door_height, "Door", ax=44, ay=16))
        labels += device_labels

        line1 = (f"<b>t = {t} s</b> · fire {units.fmt('hrr', q)} · flames {units.fmt('length', flames, 1)} tall"
                 + "".join(f" · {e}" for e in events))
        line2 = f"smoke {units.fmt('temperature', temp)}, bottom at {units.fmt('length', z, 2)} · {status}"
        return parts, f"{line1}<br>{line2}", labels

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

    legend_names = {"Smoke layer", "Flames", "Occupant", "Sprinkler", "Heat detector", "Sprinkler water"}
    FIXED_POSITION = {"Sprinkler water", "Sprinkler", "Heat detector"}

    def as_trace(part, full):
        """A trace for the figure (full) or for an animation frame (only what moves)."""
        part = dict(part)
        kind = part.pop("type", "mesh3d")
        if not full:  # frames only send what moves; Plotly keeps the rest from the first view
            for constant in ("i", "j", "k"):
                part.pop(constant, None)
            if part["name"] in FIXED_POSITION:  # these only appear or change color
                for axis in ("x", "y", "z"):
                    part.pop(axis, None)
        else:
            part.setdefault("showlegend", part["name"] in legend_names)
        if kind == "scatter3d":
            return go.Scatter3d(hoverinfo="skip", **part)
        return go.Mesh3d(flatshading=True, hoverinfo="skip", **part) if full else go.Mesh3d(**part)

    # Static parts: floor, hallway, cutaway walls, door frame, edges, head height, furniture.
    door_wall = _boxes([
        (L - 0.01, L + 0.01, 0, door_y - half_door, 0, H),
        (L - 0.01, L + 0.01, door_y + half_door, W, 0, H),
        (L - 0.01, L + 0.01, door_y - half_door, door_y + half_door, room.door_height, H),
    ])
    edges_x, edges_y, edges_z = [], [], []
    for zz in (0, H):
        x, y, z = _loop([0, L, L, 0], [0, 0, W, W], [zz] * 4)
        edges_x += x + [None]; edges_y += y + [None]; edges_z += z + [None]
    for x, y in ((0, 0), (L, 0), (L, W), (0, W)):
        edges_x += [x, x, None]; edges_y += [y, y, None]; edges_z += [0, H, None]
    door = _loop([L] * 4, [door_y - half_door, door_y + half_door, door_y + half_door, door_y - half_door],
                 [0, 0, room.door_height, room.door_height])
    head = _loop([0, L, L, 0], [0, 0, W, W], [HEAD_HEIGHT] * 4)
    static = [
        go.Mesh3d(**mesh(_box(0, L, 0, W, -0.02, 0)), color=colors["floor"], opacity=1.0, flatshading=True,
                  name="Floor", showlegend=False, hoverinfo="skip"),
        go.Mesh3d(**mesh(_box(L, L + 1.1, door_y - 0.9, door_y + 0.9, -0.02, 0)), color=colors["wall"], opacity=0.9,
                  flatshading=True, name="Hallway", showlegend=False, hoverinfo="skip"),
        go.Mesh3d(**mesh(_boxes([(0, L, W - 0.01, W + 0.01, 0, H), (-0.01, 0.01, 0, W, 0, H)])),
                  color=colors["wall"], opacity=0.45, flatshading=True, name="Walls", showlegend=False, hoverinfo="skip"),
        go.Mesh3d(**mesh(door_wall), color=colors["wall"], opacity=0.15, flatshading=True,
                  name="Door wall", showlegend=False, hoverinfo="skip"),
        go.Scatter3d(x=sc(edges_x), y=sc(edges_y), z=sc(edges_z), mode="lines",
                     line=dict(color=colors["reference"], width=2), name="Room", showlegend=False, hoverinfo="skip"),
        go.Scatter3d(x=sc(door[0]), y=sc(door[1]), z=sc(door[2]), mode="lines",
                     line=dict(color=colors["text"], width=6), name="Door", hoverinfo="skip"),
        go.Scatter3d(x=sc(head[0]), y=sc(head[1]), z=sc(head[2]), mode="lines",
                     line=dict(color=colors["text"], width=2, dash="dash"),
                     name=f"{units.fmt('length', HEAD_HEIGHT, 1)} head height", hoverinfo="skip"),
        go.Mesh3d(**mesh(_boxes(furniture)), color=colors["furniture"], opacity=1.0, flatshading=True,
                  name="Furniture", showlegend=False, hoverinfo="skip"),
    ]
    parts, caption, labels = state(start)
    moving = [as_trace(p, full=True) for p in parts]
    fig = go.Figure(data=static + moving)
    moving_indices = list(range(len(static), len(static) + len(moving)))

    frames = []
    for t in frame_times:
        f_parts, f_caption, f_labels = state(t)
        frames.append(go.Frame(name=str(t), data=[as_trace(p, full=False) for p in f_parts], traces=moving_indices,
                               layout=dict(title=dict(text=f_caption), scene=dict(annotations=f_labels))))
    fig.frames = frames

    span_x, span_y, span_z = (L + 1.3) * s, (W + 0.4) * s, (H + 0.1) * s
    biggest = max(span_x, span_y, span_z)
    play_args = dict(frame=dict(duration=90, redraw=True), transition=dict(duration=0),
                     fromcurrent=True, mode="immediate")
    unit = units.unit("length")
    hidden_axis = dict(showbackground=False, showgrid=False, zeroline=False, showticklabels=True)
    fig.update_layout(
        height=620,
        margin=dict(l=0, r=0, t=84, b=72),
        title=dict(text=caption, x=0.01, xanchor="left", y=0.985, yanchor="top",
                   font=dict(size=13, color=colors["text"])),
        legend=dict(orientation="h", x=0.0, xanchor="left", y=1.0, yanchor="bottom"),
        scene=dict(
            xaxis=dict(title=f"Length ({unit})", range=[-0.2 * s, (L + 1.1) * s], **hidden_axis),
            yaxis=dict(title=f"Width ({unit})", range=[-0.2 * s, (W + 0.2) * s], **hidden_axis),
            zaxis=dict(title=f"Height ({unit})", range=[-0.02 * s, (H + 0.1) * s], **hidden_axis),
            aspectmode="manual",
            aspectratio=dict(x=span_x / biggest, y=span_y / biggest, z=span_z / biggest),
            camera=dict(eye=dict(x=0.95, y=-1.3, z=0.7)),
            annotations=labels,
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
