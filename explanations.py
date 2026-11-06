"""
The explanatory text of the app: how each step's method works (with its
equations), sprinklers and heat detectors, validation against NUREG-1805, how
realistic the results are, limitations and sources. Each step tab shows its own
method; the "Methods & validation" tab shows the rest. Kept out of app.py so that
file stays about inputs, results and charts.
"""

import streamlit as st

from fire_model.detection import HEAT_DETECTOR_RTI, SPRINKLER_RATING_F, SPRINKLER_RTI, fahrenheit_to_celsius
from fire_model.growth import GROWTH_TIMES, growth_coefficient
from fire_model.layer_temp import LININGS
from fire_model.validation import all_cases
from guide import GROWTH_LABELS


def show_validation():
    """The NUREG-1805 comparison table, computed live from the model."""
    cases = all_cases()
    passed = sum(c.passes for c in cases)
    st.markdown(
        f"Every method in this calculator that NUREG-1805 also covers was checked against the U.S. "
        f"Nuclear Regulatory Commission's own Fire Dynamics Tools spreadsheets (NUREG-1805 Supplement 1). "
        f"Each spreadsheet comes with a worked example; the table runs this calculator on the same inputs. "
        f"**{passed} of {len(cases)} comparisons agree** within their tolerance."
    )
    st.dataframe(
        [
            {
                "Method": c.topic,
                "Quantity": c.quantity,
                "NRC": f"{c.nrc:,.6g} {c.unit}",
                "This calculator": f"{c.model:,.6g} {c.unit}",
                # Differences that round to zero show as 0.000% rather than "-0.000%".
                "Difference": f"{c.difference_percent:+.3f}%" if abs(c.difference_percent) >= 0.0005 else "0.000%",
                "Agrees": "✓" if c.passes else "✗",
                "Note": c.note,
            }
            for c in cases
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "- **The formulas match to the NRC's printed precision** (MQH, Babrauskas, Thomas, MQH 610, "
        "Alpert's ceiling jet, sprinkler and detector activation, Heskestad flame height).\n"
        "- **0.12% on the full MQH chain:** the NRC rounds concrete's k·ρ·c to 2.9; 0.0016 × 2400 × "
        "0.75 is 2.88. With 2.9 put in, the difference disappears (checked in the tests).\n"
        "- **2.2% on the MQH flashover criterion:** the published coefficient 610 corresponds to a "
        "493 K rise; this calculator uses the 500 K rise itself.\n"
        "- **Below 0.3% on activation times:** the NRC example is a steady fire with an exact formula; "
        "this calculator steps the temperature forward every 0.25 s so it also works for growing fires.\n"
        "- **Not covered:** NUREG-1805 uses a different smoke-filling method (Yamana and Tanaka), so "
        "the smoke layer height in Step 4 could not be checked this way."
    )
    st.caption("NRC values, cells and inputs: fire_model/validation.py. Spreadsheet copies: docs/nureg-1805/.")


def show_realism():
    st.markdown(
        "**Yes, in the sense engineers mean it, with clear limits.** Every result comes from a "
        "published correlation that fire protection engineers use for hand calculations, and that the "
        "NRC uses for fire inspections at nuclear plants. The calculations are shown in full in the "
        "“Check the math” tab, and "
        "this implementation reproduces the NRC's own spreadsheets."
    )
    st.markdown(
        "Matching the NRC shows the **equations are coded correctly**. How close those equations come "
        "to **real fires** is a separate question. The correlations were fitted to fire experiments, and "
        "the NRC compared them with full-scale tests in NUREG-1824 (Verification and Validation of "
        "Selected Fire Models, Volume 3 covers these Fire Dynamics Tools). Treat the results as "
        "engineering estimates:"
    )
    st.markdown(
        "- The three flashover methods disagree with each other by tens of percent. That is normal, "
        "and why the calculator shows the whole range.\n"
        "- Real fires do not follow a perfect t² curve, and real rooms leak, have more than one "
        "opening and have furniture in the way.\n"
        "- Timings are best read as \"about 30 seconds\" or \"about 3 minutes\", not to the second."
    )
    st.markdown(
        "**More realism needs a different kind of model:** a zone model such as NIST CFAST (several "
        "rooms, layers that interact, fire decay), or a CFD model such as NIST FDS, which splits the "
        "room into hundreds of thousands of cells and simulates the 3D flow. FDS runs take hours, so "
        "they cannot run live in a web page. Comparing one scenario with CFAST is a good next project."
    )


UNITS_NOTE = ("All equations use SI units, as the correlations were written. With US customary units "
              "selected, the calculator converts the inputs to SI, calculates, and converts the results back.")


def show_fire_method():
    """Step 1: the t-squared fire."""
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
        "burning. Each growth rate is defined by the time $t_g$ to reach 1,055 kW (1,000 Btu/s)."
    )
    st.markdown(
        "\n".join(
            ["| Growth rate | $t_g$ (s) | α (kW/s²) | Typical fuel |", "|---|---:|---:|---|"]
            + [f"| {GROWTH_LABELS[k][0]} | {t_g:.0f} | {growth_coefficient(t_g):.4f} | {GROWTH_LABELS[k][1]} |"
               for k, t_g in GROWTH_TIMES.items()]
        )
    )


def show_heat_method():
    """Step 2: MQH hot gas layer temperature."""
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
            + [f"| {m.name} | {m.k:g} | {m.rho:g} | {m.c:g} | {m.thickness * 1000:g} |" for m in LININGS.values()]
        )
    )
    st.caption("MQH was fitted to tests with layer temperatures below about 600 °C. Lining properties: NUREG-1805.")


def show_flashover_method():
    """Step 3: flashover thresholds and the air supply limit."""
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
        "everywhere in the calculator is the smallest of the limits (and stops growing if a "
        "sprinkler activates):"
    )
    st.latex(r"Q_{eff}(t) = \min\left(\alpha t^2,\ Q_{max},\ Q_{vent}\right)")


def show_escape_method():
    """Step 4: smoke filling, ASET and RSET."""
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
    st.latex(r"\dot m_{out} = \tfrac{2}{3} C_d W \rho_g \sqrt{2 g \left(1 - \tfrac{T_a}{T_g}\right)\tfrac{T_g}{T_a}}\,(H_d - z)^{3/2}")
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


def show_protection_method():
    """Sprinklers and heat detectors: ceiling jet and RTI heating."""
    left, right = st.columns(2)
    with left:
        st.markdown(
            "When the plume hits the ceiling it spreads out as a thin, hot, fast **ceiling jet**. "
            "Alpert's correlations give its temperature and speed at a horizontal distance $r$ from "
            "the fire, under a ceiling $H$ above the fire:"
        )
        st.latex(r"T_{jet} - T_a = \begin{cases} 16.9\, Q^{2/3}/H^{5/3} & r/H \le 0.18 \\ "
                 r"5.38\,(Q/r)^{2/3}/H & r/H > 0.18 \end{cases}")
        st.latex(r"u_{jet} = \begin{cases} 0.96\,(Q/H)^{1/3} & r/H \le 0.15 \\ "
                 r"0.195\, Q^{1/3} H^{1/2} / r^{5/6} & r/H > 0.15 \end{cases}")
        st.markdown(
            "A sprinkler bulb or a detector heats up with a delay set by its **Response Time Index** "
            "(RTI). A small RTI means a thin, quick element. It activates when it reaches its rated "
            "temperature:"
        )
        st.latex(r"\frac{dT_d}{dt} = \frac{\sqrt{u_{jet}}}{RTI}\,(T_{jet} - T_d)")
        st.markdown(
            "Because the fire grows, the calculator steps this forward every 0.25 s with the "
            "current fire size (the DETACT-QS approach). When a **sprinkler** activates, the fire "
            "stops growing and stays at its size then, a common cautious design assumption. A "
            "**heat detector** can set the alarm time instead of a smoke alarm."
        )
    with right:
        st.markdown(
            "\n".join(["| Sprinkler type | RTI (m·s)½ |", "|---|---:|"]
                      + [f"| {name} | {rti:g} |" for name, rti in SPRINKLER_RTI.items()])
        )
        st.caption("Generic RTI values: Madrzykowski (1995), as tabulated in NUREG-1805 Ch. 10.")
        st.markdown(
            "\n".join(["| Sprinkler rating | Activates at |", "|---|---:|"]
                      + [f"| {name} | {f:g} °F ({fahrenheit_to_celsius(f):.0f} °C) |" for name, f in SPRINKLER_RATING_F.items()])
        )
        st.caption("Generic temperature ratings: NFPA Automatic Sprinkler Systems Handbook, via NUREG-1805 Ch. 10.")
        spacings = [10, 15, 20, 25, 30, 40, 50, 70]
        st.markdown(
            "\n".join(["| Heat detector rating | " + " | ".join(f"{s} ft" for s in spacings) + " |",
                       "|---|" + "---:|" * len(spacings)]
                      + [f"| {rating:g} °F | " + " | ".join(str(row.get(s, "")) for s in spacings) + " |"
                         for rating, row in HEAT_DETECTOR_RTI.items()])
        )
        st.caption("Heat detector RTI (m·s)½ by rating and UL listed spacing: NFPA 72 Table B-3.2.5.1, via NUREG-1805 Ch. 10.")


def show_limitations():
    st.markdown(
        "- One room with one opening. Smoke spreading to other rooms is not modeled.\n"
        "- The fire sits on the floor and never decays or burns out.\n"
        "- A sprinkler only stops the fire from growing. The water cooling the smoke and shrinking "
        "the fire is not modeled.\n"
        "- Alpert's ceiling jet correlations are for a large flat ceiling. In a small room the hot "
        "layer makes the real ceiling jet hotter, so activation times here tend to be late "
        "(on the cautious side).\n"
        "- The smoke layer has one average temperature, from MQH. MQH was fitted to tests below "
        "about 600 °C, and the smoke filling model uses it outside its original purpose.\n"
        "- The door outflow ignores the neutral plane and the fresh air flowing in below it, so "
        "late-time smoke layer heights near the floor are approximate. Once the room is full of "
        "smoke the layer height jitters between about 0 and 0.1 m; read that as smoke down to "
        "the floor.\n"
        "- Heskestad's plume equation is meant for heights above the flame tip. When the smoke "
        "layer is lower than the flames, it is used outside that range (the app says when).\n"
        "- Flame height depends on the fire diameter, which is an assumed input.\n"
        "- Untenability is judged by layer height and temperature only, not by toxic gases or "
        "visibility.\n"
        "- The occupant walks straight to the door at a steady speed."
    )
    st.markdown(
        "Real designs use full zone models such as CFAST, or CFD models such as FDS, both free from "
        "NIST, along with safety factors. This tool shows the physics those models are built on."
    )


def show_sources():
    st.markdown(
        "- t-squared growth classes: NFPA 72, Annex B.\n"
        "- Hot gas layer temperature and MQH flashover: McCaffrey, Quintiere and Harkleroad, "
        "*Fire Technology* 17 (1981).\n"
        "- Flashover correlations: Babrauskas (1980); Thomas (1981).\n"
        "- Plume entrainment and flame height: Heskestad, SFPE Handbook of Fire Protection Engineering.\n"
        "- Ceiling jet: Alpert, \"Calculation of Response Time of Ceiling-Mounted Fire Detectors\" (1972).\n"
        "- Sprinkler RTI values: Madrzykowski (1995). Sprinkler ratings: NFPA Automatic Sprinkler "
        "Systems Handbook. Heat detector RTI: NFPA 72, Table B-3.2.5.1.\n"
        "- Implementation, material properties and validation examples: U.S. NRC NUREG-1805 "
        "Supplement 1, Fire Dynamics Tools.\n"
        "- ASET/RSET framework: SFPE Engineering Guide to Human Behavior in Fire."
    )
    st.caption("Peak fire sizes, room presets and the default fire diameter and device distances are "
               "rounded, generic examples.")


def show_methods_page():
    """The "Methods & validation" tab."""
    st.caption(UNITS_NOTE)
    with st.container(border=True):
        st.caption("VALIDATION")
        st.subheader("How we know the numbers are right")
        show_validation()
    left, right = st.columns(2)
    with left.container(border=True):
        st.caption("REALISM")
        st.subheader("Is this calculator realistic?")
        show_realism()
    with right.container(border=True):
        st.caption("LIMITS")
        st.subheader("What this calculator leaves out")
        show_limitations()
    with st.container(border=True):
        st.caption("SOURCES")
        st.subheader("Methods and data")
        show_sources()
