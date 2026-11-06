"""
"Check the calculation by hand": every equation at one moment, with the numbers
substituted in, so a reader can redo each line with a calculator.

All the numbers come from the same fire_model functions the app uses, and the
equations are written in SI units (the correlations are only valid in SI).
build_worked_example() returns sections of (explanation, LaTeX) lines; the app
displays them with st.latex.
"""

import math

from fire_model.detection import ceiling_jet_temperature_rise, ceiling_jet_velocity
from fire_model.flashover import babrauskas_flashover_hrr, mqh_flashover_hrr, thomas_flashover_hrr, ventilation_limit
from fire_model.growth import REFERENCE_HRR
from fire_model.layer_temp import T_AMBIENT, mqh_temperature_rise, thermal_penetration_time, wall_heat_transfer_coefficient
from fire_model.room import door_area, interior_surface_area, opening_factor
from fire_model.smoke_filling import (
    CONVECTIVE_FRACTION,
    DOOR_FLOW_COEFFICIENT,
    GRAVITY,
    TIME_STEP,
    door_outflow,
    gas_density,
    kelvin,
    plume_mass_flow,
)


def n(x, decimals=2):
    """A number for LaTeX, with thousands separators: 1055.0 -> '1{,}055.00'."""
    return f"{x:,.{decimals}f}".replace(",", "{,}")


def g(x, digits=4):
    """A number to `digits` significant figures, for small material properties."""
    return f"{x:.{digits}g}"


def build_worked_example(t, growth_time, peak_hrr, room, lining, occupant, result,
                         sprinkler=None, heat_detector=None):
    """Sections of worked calculations at whole second t (s).

    growth_time is t_g (s) of the growth class; peak_hrr is the fuel's peak (kW);
    result is the ScenarioResult for this scenario. Returns a list of
    (section title, [(explanation, latex), ...]).
    """
    t = max(1, min(int(t), result.t_end))
    alpha = REFERENCE_HRR / growth_time**2
    q = result.hrr[t]
    sections = []

    # ---- Step 1 ----
    grow = alpha * t**2
    cap = result.peak_hrr_used
    q_vent = ventilation_limit(room)
    step1 = [
        ("Growth coefficient from the growth time $t_g$:",
         rf"\alpha = \frac{{1055}}{{t_g^2}} = \frac{{1055}}{{{n(growth_time, 0)}^2}} = {alpha:.5f}\ \text{{kW/s}}^2"),
        (f"Growing fire at t = {t} s:",
         rf"\alpha t^2 = {alpha:.5f} \times {t}^2 = {n(grow, 1)}\ \text{{kW}}"),
        ("The fire actually burning is the smallest of the three limits:",
         rf"Q_{{eff}} = \min(\alpha t^2,\ Q_{{max}},\ Q_{{vent}}) = \min({n(grow, 1)},\ {n(cap, 1)},\ {n(q_vent, 1)}) = {n(q, 1)}\ \text{{kW}}"),
    ]
    if cap < peak_hrr:
        step1.append((f"Here $Q_{{max}}$ is {n(cap, 0)} kW, not the fuel's {n(peak_hrr, 0)} kW, because the "
                      f"sprinkler activated at {result.sprinkler_time:g} s and the fire stopped growing.", ""))
    sections.append(("Step 1: fire size", step1))

    # ---- Step 2 ----
    a_o, of, a_t = door_area(room), opening_factor(room), interior_surface_area(room)
    t_p = thermal_penetration_time(lining)
    h_k = wall_heat_transfer_coefficient(t, lining)
    rise = mqh_temperature_rise(q, room, h_k) if q > 0 else 0.0
    t_g = T_AMBIENT + rise
    if t < t_p:
        h_k_line = rf"t < t_p:\quad h_k = \sqrt{{\frac{{k\rho c}}{{t}}}} = \sqrt{{\frac{{{g(lining.k)} \times {g(lining.rho)} \times {g(lining.c)}}}{{{t}}}}} = {h_k:.5f}\ \text{{kW/m}}^2\text{{K}}"
    else:
        h_k_line = rf"t \ge t_p:\quad h_k = \frac{{k}}{{\delta}} = \frac{{{g(lining.k)}}}{{{g(lining.thickness)}}} = {h_k:.5f}\ \text{{kW/m}}^2\text{{K}}"
    step2 = [
        ("Door area and opening factor:",
         rf"A_o = W H_d = {g(room.door_width)} \times {g(room.door_height)} = {n(a_o, 3)}\ \text{{m}}^2 \qquad "
         rf"A_o\sqrt{{H_o}} = {n(a_o, 3)} \times \sqrt{{{g(room.door_height)}}} = {n(of, 3)}\ \text{{m}}^{{5/2}}"),
        ("Inside surface area (walls, ceiling and floor, minus the door):",
         rf"A_T = 2(LW + LH + WH) - A_o = 2({g(room.length)}\cdot{g(room.width)} + {g(room.length)}\cdot{g(room.height)} + "
         rf"{g(room.width)}\cdot{g(room.height)}) - {n(a_o, 3)} = {n(a_t, 2)}\ \text{{m}}^2"),
        ("Thermal penetration time of the lining:",
         rf"t_p = \frac{{\rho c}}{{k}}\left(\frac{{\delta}}{{2}}\right)^2 = \frac{{{g(lining.rho)} \times {g(lining.c)}}}{{{g(lining.k)}}}"
         rf"\left(\frac{{{g(lining.thickness)}}}{{2}}\right)^2 = {n(t_p, 0)}\ \text{{s}}"),
        ("Wall heat transfer coefficient at this moment:", h_k_line),
        ("MQH temperature rise:",
         rf"\Delta T_g = 6.85\left[\frac{{Q^2}}{{A_o\sqrt{{H_o}}\, h_k\, A_T}}\right]^{{1/3}} = "
         rf"6.85\left[\frac{{{n(q, 1)}^2}}{{{n(of, 3)} \times {h_k:.5f} \times {n(a_t, 2)}}}\right]^{{1/3}} = {n(rise, 1)}\ \text{{K}}"),
        ("Smoke layer temperature:",
         rf"T_g = T_a + \Delta T_g = {n(T_AMBIENT, 0)} + {n(rise, 1)} = {n(t_g, 1)}\ ^\circ\text{{C}}"
         + (r"\quad(\text{above } 600\,^\circ\text{C: outside MQH's range})" if t_g > 600 else "")),
    ]
    sections.append(("Step 2: smoke layer temperature (MQH)", step2))

    # ---- Step 3 ----
    q_bab, q_tho = babrauskas_flashover_hrr(room), thomas_flashover_hrr(room)
    q_mqh = mqh_flashover_hrr(room, h_k)
    step3 = [
        ("Air supply limit:", rf"Q_{{vent}} = 1500\, A_o\sqrt{{H_o}} = 1500 \times {n(of, 3)} = {n(q_vent, 0)}\ \text{{kW}}"),
        ("Babrauskas:", rf"Q_{{FO}} = 750\, A_o\sqrt{{H_o}} = 750 \times {n(of, 3)} = {n(q_bab, 0)}\ \text{{kW}}"),
        ("Thomas:", rf"Q_{{FO}} = 7.8\, A_T + 378\, A_o\sqrt{{H_o}} = 7.8 \times {n(a_t, 2)} + 378 \times {n(of, 3)} = {n(q_tho, 0)}\ \text{{kW}}"),
        ("MQH, using this moment's $h_k$ (the calculator uses the equivalent test: the layer reaching 520 °C):",
         rf"Q_{{FO}} = 610\sqrt{{h_k A_T A_o\sqrt{{H_o}}}} = 610\sqrt{{{h_k:.5f} \times {n(a_t, 2)} \times {n(of, 3)}}} = {n(q_mqh, 0)}\ \text{{kW}}"),
        (f"Compare with the fire at t = {t} s, {n(q, 0)} kW: "
         + ", ".join(f"{name} {'reached' if q >= v else 'not reached'}"
                     for name, v in (("Babrauskas", q_bab), ("Thomas", q_tho), ("MQH", q_mqh))) + ".", ""),
    ]
    sections.append(("Step 3: flashover and the air supply limit", step3))

    # ---- Step 4 ----
    z = result.layer_height[t]
    t_g_c = result.layer_temp[t]
    t_g_k = kelvin(t_g_c)
    rho_g = gas_density(t_g_k)
    q_c = CONVECTIVE_FRACTION * q
    m_in = plume_mass_flow(q, z)
    m_out = door_outflow(room, z, t_g_k)
    t_a_k = kelvin(T_AMBIENT)
    step4 = [
        ("Smoke density from the ideal gas law (temperature in K):",
         rf"\rho_g = \frac{{353}}{{T_g}} = \frac{{353}}{{{n(t_g_k, 2)}}} = {rho_g:.4f}\ \text{{kg/m}}^3"),
        (f"From the step-by-step simulation, the bottom of the smoke layer is at z = {z:.3f} m. "
         f"The plume (convective part $Q_c = 0.7\\,Q$ = {q_c:,.1f} kW) carries this much gas into the layer:",
         rf"\dot m_p = 0.071\, Q_c^{{1/3}} z^{{5/3}} + 0.0018\, Q_c = 0.071 \times {n(q_c, 1)}^{{1/3}} \times {z:.3f}^{{5/3}} "
         rf"+ 0.0018 \times {n(q_c, 1)} = {m_in:.4f}\ \text{{kg/s}}"),
    ]
    if z < room.door_height:
        step4.append(("Smoke flowing out of the top of the door:",
                      rf"\dot m_{{out}} = \tfrac{{2}}{{3}} C_d W \rho_g \sqrt{{2g\left(1 - \tfrac{{T_a}}{{T_g}}\right)\tfrac{{T_g}}{{T_a}}}}\,(H_d - z)^{{3/2}}"))
        step4.append(("",
                      rf"= \tfrac{{2}}{{3}}({DOOR_FLOW_COEFFICIENT:g})({g(room.door_width)})({rho_g:.4f})"
                      rf"\sqrt{{2({GRAVITY:g})\left(1 - \tfrac{{{n(t_a_k, 2)}}}{{{n(t_g_k, 2)}}}\right)\tfrac{{{n(t_g_k, 2)}}}{{{n(t_a_k, 2)}}}}}"
                      rf"\,({g(room.door_height)} - {z:.3f})^{{3/2}} = {m_out:.4f}\ \text{{kg/s}}"))
    else:
        step4.append(("The layer is still above the top of the door, so no smoke flows out yet:",
                      r"\dot m_{out} = 0"))
    step4 += [
        ("The mass balance, and one Euler step of 0.25 s:",
         rf"\frac{{dm}}{{dt}} = \dot m_p - \dot m_{{out}} = {m_in:.4f} - {m_out:.4f} = {m_in - m_out:.4f}\ \text{{kg/s}}"
         rf"\qquad \Delta m = {m_in - m_out:.4f} \times {TIME_STEP:g} = {(m_in - m_out) * TIME_STEP:.4f}\ \text{{kg}}"),
    ]
    if result.rset is not None:
        step4.append(("Required safe egress time:",
                      rf"\text{{RSET}} = t_{{det}} + t_{{react}} + \frac{{d}}{{v}} = {n(result.alarm_time, 1)} + "
                      rf"{n(occupant.reaction_time, 0)} + \frac{{{g(occupant.walk_distance)}}}{{{g(occupant.walk_speed)}}} = "
                      rf"{n(result.rset, 1)}\ \text{{s}}"))
    sections.append(("Step 4: smoke filling and escape", step4))

    # ---- Sprinkler and heat detector ----
    for name, device, temps, activation in (
        ("Sprinkler", sprinkler, result.sprinkler_temps, result.sprinkler_time),
        ("Heat detector", heat_detector, result.heat_detector_temps, result.heat_detector_time),
    ):
        if device is None or temps is None:
            continue
        H, r = room.height, device.radial_distance
        rise_jet = ceiling_jet_temperature_rise(q, H, r)
        u_jet = ceiling_jet_velocity(q, H, r)
        t_jet = T_AMBIENT + rise_jet
        t_dev = temps[t]
        if r / H <= 0.18:
            jet_line = rf"\frac{{r}}{{H}} = {r / H:.3f} \le 0.18:\quad T_{{jet}} - T_a = \frac{{16.9\, Q^{{2/3}}}}{{H^{{5/3}}}} = \frac{{16.9 \times {n(q, 1)}^{{2/3}}}}{{{g(H)}^{{5/3}}}} = {n(rise_jet, 1)}\ \text{{K}}"
        else:
            jet_line = rf"\frac{{r}}{{H}} = {r / H:.3f} > 0.18:\quad T_{{jet}} - T_a = \frac{{5.38\,(Q/r)^{{2/3}}}}{{H}} = \frac{{5.38\,({n(q, 1)}/{g(r)})^{{2/3}}}}{{{g(H)}}} = {n(rise_jet, 1)}\ \text{{K}}"
        if r / H <= 0.15:
            u_line = rf"u_{{jet}} = 0.96\left(\frac{{Q}}{{H}}\right)^{{1/3}} = 0.96\left(\frac{{{n(q, 1)}}}{{{g(H)}}}\right)^{{1/3}} = {u_jet:.3f}\ \text{{m/s}}"
        else:
            u_line = rf"u_{{jet}} = \frac{{0.195\, Q^{{1/3}} H^{{1/2}}}}{{r^{{5/6}}}} = \frac{{0.195 \times {n(q, 1)}^{{1/3}} \times {g(H)}^{{1/2}}}}{{{g(r)}^{{5/6}}}} = {u_jet:.3f}\ \text{{m/s}}"
        rate = math.sqrt(u_jet) / device.rti * (t_jet - t_dev)
        lines = [
            ("Ceiling jet temperature (Alpert), with H = ceiling height above the fire:", jet_line),
            ("Ceiling jet velocity (Alpert):", u_line),
            (f"The {name.lower()}'s element is at {t_dev:.1f} °C. It heats at:",
             rf"\frac{{dT_d}}{{dt}} = \frac{{\sqrt{{u_{{jet}}}}}}{{RTI}}(T_{{jet}} - T_d) = \frac{{\sqrt{{{u_jet:.3f}}}}}{{{g(device.rti)}}}"
             rf"({n(t_jet, 1)} - {t_dev:.1f}) = {rate:.3f}\ \text{{K/s}}"),
            (f"It activates when its element reaches {device.activation_temp:.1f} °C: "
             + (f"at {activation:g} s." if activation is not None else f"not within {result.t_end} s."), ""),
        ]
        sections.append((f"{name}: activation (Alpert ceiling jet and RTI)", lines))
    return sections
