"""
3D view of the room for the app: a picture of the two-zone model's results.

This is NOT a 3D fire simulation. The two-zone model only knows, at each
moment, how far down the smoke layer reaches and its one average temperature.
So the smoke is drawn as a single flat, uniform slab under the ceiling, which is
exactly the assumption the model makes. (A true 3D fire simulation is CFD, such
as NIST's FDS, which splits the room into many small cells.)

What is drawn, to scale from the inputs:
  * the room as a wire frame, with the door on the right-hand wall,
  * the smoke layer: from the ceiling down to the interface height z(t),
    colored from gray to red as its temperature rises,
  * the fire on the floor: its drawn size grows with the heat release rate
    (a visual cue only, not a calculated flame height),
  * the occupant walking to the door on the RSET timeline,
  * a dashed line at 1.8 m, the tenability head height.
"""

import math

import plotly.graph_objects as go

from fire_model.egress import HEAD_HEIGHT, distance_left_to_walk, occupant_status, rset
from fire_model.layer_temp import T_AMBIENT

PERSON_HEIGHT = 1.75  # m, drawing only
MAX_FRAMES = 121  # about one frame every 5 s for a 600 s simulation


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


def _pyramid(cx, cy, half_width, height):
    """A square pyramid standing on the floor, for go.Mesh3d (the fire)."""
    b = half_width
    return dict(
        x=[cx - b, cx + b, cx + b, cx - b, cx],
        y=[cy - b, cy - b, cy + b, cy + b, cy],
        z=[0, 0, 0, 0, height],
        i=[0, 0, 0, 1, 2, 3],
        j=[1, 2, 1, 2, 3, 0],
        k=[2, 3, 4, 4, 4, 4],
    )


def _mix(hex_a, hex_b, f):
    """Color part-way between two '#RRGGBB' colors (f = 0 gives a, 1 gives b)."""
    a = [int(hex_a[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i : i + 2], 16) for i in (1, 3, 5)]
    r, g, bl = (round(p + (q - p) * f) for p, q in zip(a, b))
    return f"rgb({r},{g},{bl})"


def _rectangle(x, y, z):
    """Close a list of corner points into a loop for a line trace."""
    return x + x[:1], y + y[:1], z + z[:1]


def room_3d_figure(result, room, occupant, colors, start_time=120):
    """Build the animated 3D view. `result` is a fire_model ScenarioResult."""
    L, W, H = room.length, room.width, room.height
    t_end = result.t_end
    door_y = min(max(0.6 * W, room.door_width / 2), W - room.door_width / 2)  # door centre
    fire_x, fire_y = 0.28 * L, 0.3 * W  # fire position on the floor
    time_to_escape = rset(occupant)

    def state(t):
        """The three moving parts (smoke, fire, occupant) and a caption at time t."""
        z, temp, q = result.layer_height[t], result.layer_temp[t], result.hrr[t]

        # Smoke: gray when cool, red as it approaches 600 °C.
        heat = max(0.0, min(1.0, (temp - T_AMBIENT) / 600))
        has_smoke = z < H - 0.01
        smoke = dict(**_box(0, L, 0, W, min(z, H - 0.01), H),
                     color=_mix(colors["smoke"], colors["heat"], heat),
                     opacity=(0.25 + 0.45 * heat) if has_smoke else 0.0)

        # Fire: drawn size grows with the square root of the HRR (visual cue only).
        size = math.sqrt(min(1.0, q / 3000))
        fire = dict(**_pyramid(fire_x, fire_y, 0.1 + 0.3 * size, min(0.9 * H, 0.15 + 1.2 * size)),
                    opacity=1.0 if q > 0 else 0.0)

        # Occupant: walks along the room toward the door, then steps outside.
        out = t >= time_to_escape
        status = occupant_status(t, occupant)
        if out:
            person_x = L + 0.5
            person_color = colors["safe"]
        else:
            person_x = max(0.25, L - 0.25 - distance_left_to_walk(t, occupant))
            untenable = result.aset is not None and t >= result.aset
            person_color = colors["heat"] if untenable else colors["air"]
            if untenable:
                status += " · room untenable"
        person = dict(**_box(person_x - 0.18, person_x + 0.18, door_y - 0.13, door_y + 0.13, 0, PERSON_HEIGHT),
                      color=person_color)

        caption = (f"<b>t = {t} s</b> · fire {q:,.0f} kW · smoke {temp:,.0f} °C, "
                   f"bottom at {z:.2f} m · {status}")
        return smoke, fire, person, caption

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

    smoke, fire, person, caption = state(start)
    edge = dict(color=colors["reference"], width=3)
    no_hover = dict(hoverinfo="skip")

    # Room wire frame: floor and ceiling outlines plus the four vertical edges.
    xs, ys, zs = [], [], []
    for zz in (0, H):
        x, y, z = _rectangle([0, L, L, 0], [0, 0, W, W], [zz] * 4)
        xs += x + [None]; ys += y + [None]; zs += z + [None]
    for x, y in ((0, 0), (L, 0), (L, W), (0, W)):
        xs += [x, x, None]; ys += [y, y, None]; zs += [0, H, None]

    half_door = room.door_width / 2
    door_x, door_yy, door_z = _rectangle(
        [L] * 4,
        [door_y - half_door, door_y + half_door, door_y + half_door, door_y - half_door],
        [0, 0, room.door_height, room.door_height],
    )
    head_x, head_y, head_z = _rectangle([0, L, L, 0], [0, 0, W, W], [HEAD_HEIGHT] * 4)

    fig = go.Figure(data=[
        go.Mesh3d(**_box(0, L, 0, W, 0, 0.001), color=colors["reference"], opacity=0.25,
                  name="Floor", showlegend=False, **no_hover),                                   # 0
        go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=edge, name="Room", showlegend=False, **no_hover),  # 1
        go.Scatter3d(x=door_x, y=door_yy, z=door_z, mode="lines", line=dict(color=colors["text"], width=6),
                     name="Door", **no_hover),                                                   # 2
        go.Scatter3d(x=head_x, y=head_y, z=head_z, mode="lines",
                     line=dict(color=colors["text"], width=2, dash="dash"),
                     name="1.8 m head height", **no_hover),                                      # 3
        go.Mesh3d(**smoke, name="Smoke layer", showlegend=True, flatshading=True, **no_hover),   # 4
        go.Mesh3d(**fire, color=colors["fire"], name="Fire", showlegend=True, flatshading=True, **no_hover),  # 5
        go.Mesh3d(**person, name="Occupant", showlegend=True, flatshading=True, **no_hover),     # 6
    ])

    # Animation frames: only the smoke, fire and occupant (traces 4-6) change.
    frames = []
    for t in frame_times:
        f_smoke, f_fire, f_person, f_caption = state(t)
        frames.append(go.Frame(
            name=str(t),
            data=[go.Mesh3d(**f_smoke), go.Mesh3d(**f_fire), go.Mesh3d(**f_person)],
            traces=[4, 5, 6],
            layout=dict(title=dict(text=f_caption)),
        ))
    fig.frames = frames

    play_args = dict(frame=dict(duration=90, redraw=True), transition=dict(duration=0),
                     fromcurrent=True, mode="immediate")
    fig.update_layout(
        height=560,
        # Top: caption, then the legend. Bottom: Play/Pause and the time slider.
        margin=dict(l=0, r=0, t=64, b=72),
        title=dict(text=caption, x=0.01, xanchor="left", y=0.985, yanchor="top",
                   font=dict(size=13, color=colors["text"])),
        legend=dict(orientation="h", x=0.0, xanchor="left", y=1.0, yanchor="bottom"),
        scene=dict(
            xaxis=dict(title="Length (m)", range=[-0.2, L + 1.0], showbackground=False),
            yaxis=dict(title="Width (m)", range=[-0.2, W + 0.2], showbackground=False),
            zaxis=dict(title="Height (m)", range=[0, H + 0.1], showbackground=False),
            aspectmode="manual",
            aspectratio=_true_scale(L + 1.2, W + 0.4, H + 0.1),
            camera=dict(eye=dict(x=1.0, y=-1.4, z=0.75)),
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


def _true_scale(dx, dy, dz):
    """Aspect ratio that keeps metres the same length on all three axes."""
    biggest = max(dx, dy, dz)
    return dict(x=dx / biggest, y=dy / biggest, z=dz / biggest)
