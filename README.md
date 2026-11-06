# Compartment Fire Calculator

> **This is a learning tool, not a design tool.** It uses simplified hand-calculation
> methods with real limits (listed below). Don't use its results for real design decisions.

An interactive web app that predicts how a fire in one room grows, how hot the smoke
gets, whether the room flashes over, and whether the people inside get out before
conditions become untenable. Every result comes from a standard hand-calculation method
in fire dynamics, and the app explains each one.

A first-year fire protection engineering project by **Dhruv Sirigiri**
(B.S. Fire Protection Engineering, University of Maryland).

**Live app:** *link coming soon*

![The Compartment Fire Calculator: inputs, verdict and 3D room view](docs/screenshot.png)

## What it does

You describe a fire, a room and the people in it. The app works through four steps:

| Step | Question | Method |
|---|---|---|
| 1 | How big is the fire? | t-squared fire growth (NFPA 72) |
| 2 | How hot does the smoke get? | MQH hot gas layer correlation |
| 3 | Does the room flash over? | Babrauskas, Thomas and MQH flashover methods; air supply (ventilation) limit |
| 4 | Do people get out in time? | Two-zone smoke filling (Heskestad plume); ASET vs RSET |

It then shows:

- **A verdict**: the flashover time range, when the room becomes untenable (ASET), when
  everyone is out (RSET), and the safety margin between them.
- **A 3D view of the room** you can play like a video: the smoke layer dropping and
  heating up, the fire growing and the occupant walking to the door. It draws the
  two-zone model's results; it is not a 3D fire simulation (that would need CFD
  software such as NIST's FDS).
- **Interactive charts** of the fire size, the smoke layer temperature and the smoke
  layer height, plus the flashover methods table and the numbers behind every chart.
- **An explanation of every step**, with its equations, limits and sources.

## The methods

Ambient temperature $T_a$ = 20 °C. SI units throughout (kW, m, s, kg).

### Step 1: Fire growth (t-squared fire)

```math
Q(t) = \alpha t^2 \qquad \alpha = \frac{1055}{t_g^2}
```

The fire grows until it reaches the peak heat release rate of the fuel; there is no
decay phase. Growth classes from NFPA 72, Annex B, defined by the time $t_g$ to reach
1055 kW (1000 BTU/s):

| Growth | $t_g$ (s) | α (kW/s²) |
|---|---:|---:|
| Slow | 600 | 0.0029 |
| Medium | 300 | 0.0117 |
| Fast | 150 | 0.0469 |
| Ultrafast | 75 | 0.1876 |

### Step 2: Hot gas layer temperature (MQH)

McCaffrey, Quintiere and Harkleroad (1981):

```math
\Delta T_g = 6.85 \left[ \frac{Q^2}{A_o\sqrt{H_o}\; h_k\, A_T} \right]^{1/3}
```

- $A_o\sqrt{H_o}$ is the opening factor (door area × √door height).
- $A_T = 2(LW + LH + WH) - A_o$ is the interior surface area minus the opening.
- $h_k$ is the wall's effective heat transfer coefficient. It depends on the thermal
  penetration time $t_p$:

```math
t_p = \frac{\rho c}{k}\left(\frac{\delta}{2}\right)^2 \qquad
h_k = \begin{cases} \sqrt{k \rho c / t} & t < t_p \\ k/\delta & t \ge t_p \end{cases}
```

The correlation was fitted to layer temperatures below about 600 °C, so the app shows
results above that as outside its range. Lining properties (NUREG-1805):

| Lining | k (kW/m·K) | ρ (kg/m³) | c (kJ/kg·K) | Default δ (mm) |
|---|---:|---:|---:|---:|
| Gypsum board | 0.00017 | 960 | 1.1 | 16 |
| Concrete | 0.0016 | 2400 | 0.75 | 150 |
| Brick | 0.0008 | 2600 | 0.8 | 100 |
| Plywood | 0.00012 | 540 | 2.5 | 13 |
| Fiber insulation board | 0.00053 | 240 | 1.25 | 25 |

### Step 3: Flashover and the air supply limit

Three estimates of the smallest fire that can cause flashover:

```math
\text{Babrauskas: } Q_{FO} = 750\, A_o\sqrt{H_o} \qquad
\text{Thomas: } Q_{FO} = 7.8\, A_T + 378\, A_o\sqrt{H_o}
```

```math
\text{MQH: } Q_{FO} = 610 \left( h_k\, A_T\, A_o\sqrt{H_o} \right)^{1/2}
```

The MQH method is applied as the time the Step 2 layer temperature reaches
$T_a$ + 500 °C. (Solving the MQH equation exactly for a 500 K rise gives a coefficient
of about 624 rather than the published 610, a 2% difference.)

The door also limits how big the fire can get. About $0.5\,A_o\sqrt{H_o}$ kg/s of air can
flow in, and burning 1 kg of air releases about 3000 kJ:

```math
Q_{vent} = 1500\, A_o\sqrt{H_o} \qquad Q_{eff}(t) = \min\left(\alpha t^2,\ Q_{max},\ Q_{vent}\right)
```

$Q_{eff}$ is the fire used in every step.

### Step 4: Smoke filling and escape (ASET vs RSET)

A two-zone model: a hot, well-mixed smoke layer under the ceiling and clear air below
it, with the boundary at height $z$. The plume (Heskestad, convective fraction 0.7, fire
at floor level) carries mass up into the layer, and once the layer is below the top of
the door ($H_d$), smoke flows out through the doorway:

```math
\dot m_p = 0.071\, Q_c^{1/3} z^{5/3} + 0.0018\, Q_c \qquad Q_c = 0.7\,Q
```

```math
\dot m_{out} = \tfrac{2}{3} C_d W \rho_g \sqrt{2 g \left(1 - \tfrac{T_a}{T_g}\right)\tfrac{T_g}{T_a}}\,(H_d - z)^{3/2} \qquad C_d = 0.7
```

```math
\frac{dm}{dt} = \dot m_p - \dot m_{out} \qquad \rho_g = \frac{353}{T_g} \qquad z = H - \frac{m}{\rho_g\, A_{floor}}
```

The layer temperature $T_g$ (in K) comes from Step 2. The equation is solved with the
explicit Euler method, $\Delta t$ = 0.25 s.

- **ASET** (available safe egress time) is the earlier of: the layer drops to 1.8 m
  (head height), or the layer reaches 200 °C.
- **RSET** (required safe egress time) = detection time + reaction (pre-movement) time
  + walking distance / walking speed.
- The design works only if ASET > RSET.

## How it was checked

There are 75 automated tests (`pytest`). The model reproduces every check value worked
out with the original single-file prototype (`index.html`):

| Scenario | Quantity | Expected | Model |
|---|---|---|---|
| Bedroom | Thermal penetration time $t_p$ | ≈ 398 s | 397.6 s |
| Bedroom | Opening factor / $A_T$ | 2.546 / 81.4 m² | 2.5456 / 81.40 m² |
| Bedroom | $T_g$ at 150 s (1055 kW) | ≈ 388 °C | 388.2 °C |
| Bedroom | $T_g$ at 231 s (2500 kW) | ≈ 723 °C | 723.2 °C |
| Bedroom | $T_g$ at 150 s, 150 mm concrete | ≈ 252 °C | 251.8 °C |
| Bedroom | Babrauskas / Thomas / $Q_{vent}$ | 1909 / 1597 / 3818 kW | 1909.2 / 1597.2 / 3818.4 kW |
| Bedroom | MQH flashover time | 184 s | 184 s |
| Bedroom | Smoke layer reaches 1.8 m | 29 s | 29 s |
| Bedroom | $z$ at 60 / 120 / 300 s | ≈ 1.22 / 0.88 / 0.10 m | 1.216 / 0.877 / 0.100 m |
| Dorm | Babrauskas / Thomas / $Q_{vent}$ | 2054 / 1591 / 4108 kW | 2054.2 / 1590.7 / 4108.3 kW |
| Dorm | MQH flashover / 1.8 m | 182 s / 29 s | 182 s / 29 s |
| Living room | Flashover / 1.8 m / $z$ at 600 s | none / 86 s / ≈ 1.25 m | none / 86 s / 1.245 m |
| — | RSET, awake with an alarm | 63.3 s | 63.33 s |

Bedroom 5 × 4 × 2.4 m with a 0.9 × 2.0 m door; dorm 4.5 × 3.5 × 2.6 m with a 0.9 × 2.1 m
door (fast fire, 2500 kW sofa, 16 mm gypsum). Living room 7 × 6 × 2.4 m with a
1.8 × 2.1 m opening (slow fire, 750 kW chair).

Beyond the check values:

- The Python model agrees with the JavaScript prototype to about $10^{-13}$ at every
  second of four scenarios, and the app displayed the same values as the prototype for
  all 90 numbers compared across six scenarios.
- One original check value was corrected. "150 mm concrete at 150 s ≈ 278 °C" turned out
  to be the result for concrete left at 16 mm thick: its heat then soaks through in
  72 s, so by 150 s $h_k = k/\delta$. For 150 mm concrete the equation gives 252 °C.

Next step: validate each method against the worked example problems in NRC NUREG-1805.

## Run it yourself

You need Python 3.10 or newer ([python.org](https://www.python.org/downloads/)).

```bash
git clone https://github.com/dhruvsirigiri/compartment-fire-calculator.git
cd compartment-fire-calculator
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py             # opens http://localhost:8501
```

Run the tests with:

```bash
pytest
```

## Project structure

```
fire_model/          the physics, as pure functions (no user interface code)
  growth.py          Step 1: t-squared fire growth
  room.py            room geometry: opening factor, A_T, floor area, input checks
  layer_temp.py      Step 2: MQH layer temperature, lining properties
  flashover.py       Step 3: flashover thresholds, air supply limit
  smoke_filling.py   Step 4: two-zone smoke filling (Euler method)
  egress.py          Step 4: ASET, RSET, occupant timeline
  timeline.py        "first second at which something happens" helpers
  scenario.py        runs all four steps for one scenario
app.py               the Streamlit web app
room_view.py         the 3D room view
tests/               pytest tests, including every check value
index.html           the original single-file prototype (reference implementation)
```

## Limitations

- One room with one opening. Smoke spreading to other rooms is not modeled.
- The fire sits on the floor and never decays or burns out.
- No sprinklers.
- The smoke layer has one average temperature, from MQH. MQH was fitted to tests below
  about 600 °C, and the smoke filling model uses it outside its original purpose.
- The door outflow ignores the neutral plane and the fresh air flowing in below it, so
  late-time layer heights near the floor are approximate. Once the room is full of smoke,
  the plume still delivers slightly more gas than the door removes, so the layer height
  jitters between about 0 and 0.1 m.
- Heskestad's plume equation is meant for heights above the flame tip; when the smoke
  layer is lower than the flames it is used outside that range.
- Tenability uses layer height and temperature only (no toxic gases or visibility).
- The occupant walks straight to the door at a constant speed.

Real designs use full zone models such as CFAST, or CFD models such as FDS (both free
from NIST), together with safety factors.

## Ideas for later

1. Validate every step against the NRC NUREG-1805 example problems.
2. Sprinkler and heat detector activation time (Alpert ceiling jet, RTI, DETACT-QS), with
   the fire capped when a sprinkler activates.
3. SI / US customary unit toggle (ft, °F, BTU/s).
4. Fire decay phase and total fuel load.
5. Compare one scenario with NIST CFAST.
6. Export a one-page PDF report of a scenario.

## References

- NFPA 72, *National Fire Alarm and Signaling Code*, Annex B (t-squared fires).
- McCaffrey, B. J., Quintiere, J. G. and Harkleroad, M. F., "Estimating Room
  Temperatures and the Likelihood of Flashover Using Fire Test Data Correlations,"
  *Fire Technology* 17 (1981).
- Babrauskas, V. (1980); Thomas, P. H. (1981): flashover correlations.
- Heskestad, G., plume chapter, *SFPE Handbook of Fire Protection Engineering*.
- U.S. Nuclear Regulatory Commission, NUREG-1805, *Fire Dynamics Tools (FDTs)*.
- SFPE, *Engineering Guide to Human Behavior in Fire* (ASET/RSET framework).

Peak fire sizes and room presets are rounded, generic examples.
