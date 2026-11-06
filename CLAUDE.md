# Compartment Fire Calculator

A first-year fire protection engineering (FPE) portfolio project by Dhruv Sirigiri (B.S. Fire Protection Engineering, University of Maryland). It predicts how a fire in one room grows, how hot the smoke gets, whether the room flashes over, and whether occupants escape before conditions become untenable. It will go on a resume and be presented to an FPE professor.

**This is a learning tool, not a design tool.** Keep that statement visible in the app.

## Who you're working with

Dhruv is new to programming and to fire dynamics (currently in Calculus III). When you work on this project:
- Explain what each change does and why, in plain language, before or after making it.
- Prefer clear, readable code over clever code. Comment the physics, not the obvious.
- Never invent physics, coefficients or validation data. If a value needs a source, say so and ask.
- Build in small steps that run and can be checked, not one giant rewrite.

## Current state

The Python/Streamlit app is built and deployed at https://compartment-fire-calculator.streamlit.app/ (code: https://github.com/dhruvsirigiri/compartment-fire-calculator). Streamlit Community Cloud redeploys automatically when `main` is pushed. It keeps the Python process running, so `app.py` starts by reloading the project's own modules when any project `.py` file has changed (without that, an update made while nobody had the app open left old modules in memory and caused an ImportError). If the live app ever shows a stale-code error anyway, reboot it from "Manage app" on share.streamlit.io.

`index.html` is the original single-file prototype (HTML + vanilla JS). It is the reference implementation: with no sprinkler and no heat detector, the app must reproduce its results (see "Check values" below).

Beyond the prototype the app has: sprinkler and heat detector activation; a metric / US customary unit switch (display only, the physics stays in SI); a 3D view (cutaway room with furniture, Heskestad flame height, smoke colored by temperature, door spill, sprinkler spray, occupant, labels pinned to the scene); a "check the calculation by hand" section; and validation against the NUREG-1805 spreadsheets (`fire_model/validation.py`, `docs/VALIDATION.md`).

It is laid out as an interactive guide: the verdict, then a "What your last change did" box (which results moved, before → after, better or worse, and why, with Undo), then tabs: Overview (step headlines and key moments), one tab per step (explanation for the current inputs, readouts, chart, "Try this" buttons that change one input, the method and equations, Back/Next), Sprinklers & detectors, 3D view (key moments, a description of the chosen moment, what is calculated vs. only drawn), Check the math, and Methods & validation. A one-line result sits under each group of inputs in the sidebar. All of these sentences come from `guide.py`, built only from `fire_model` numbers.

Streamlit notes (1.67): only the open tab is drawn (`st.tabs(..., on_change="rerun")` and `tab.open`), so widgets inside a tab use `persist_state="page"` to keep their value while it is closed. A menu (`selectbox`, `radio`) remembers its choice by its displayed label, so labels must never depend on the unit switch or on results (a unit in a fuel label once crashed the app after switching units); put such numbers in a caption.

## Target architecture (recommended)

- `fire_model/` — Python package with the physics as pure functions, one module per step (`growth.py`, `layer_temp.py`, `flashover.py`, `smoke_filling.py`, `egress.py`), SI units throughout.
- `tests/` — pytest tests. Start with the check values below, then add NUREG-1805 example problems.
- `app.py` — Streamlit front end (inputs in sidebar, verdict at top, Plotly charts, explanations per step). Deploy free on Streamlit Community Cloud so there's a public link for the resume.
- `README.md` — what it does, the methods, screenshots, limits, references.
- Git repository pushed to GitHub (public), with a clear commit history.

Keep the physics independent of the UI so it can be tested and reused.

As built: `fire_model/` also has `room.py` (geometry), `timeline.py` (first-time helpers), `scenario.py` (runs every step), `detection.py` (sprinklers and heat detectors) and `validation.py` (NUREG-1805 cases). The UI is split into `app.py` (inputs, verdict, change box, tabs), `guide.py` (plain-language explanations that follow the inputs), `charts.py`, `room_view.py` (3D), `worked_example.py`, `explanations.py` (each step's method and equations, validation, realism, sources) and `units.py`.

## The model

Ambient T_a = 20 °C. Head height for tenability = 1.8 m.

### Step 1: Fire growth (t-squared fire)
- Q(t) = α t², capped at user peak HRR Q_max (kW). No decay phase.
- Growth classes (NFPA 72 Annex B): t_g = 600 / 300 / 150 / 75 s to reach 1055 kW (slow / medium / fast / ultrafast); α = 1055 / t_g² (kW/s²).
- Fuel presets for peak HRR (rounded examples): wastebasket 100, office chair 750, armchair 1200, mattress and bed 2000, sofa 2500 kW.

### Step 2: Hot gas layer temperature (MQH, McCaffrey–Quintiere–Harkleroad 1981)
- ΔT_g = 6.85 [Q² / (A_o √H_o · h_k · A_T)]^(1/3)
- A_o = door width × height; H_o = door height; opening factor = A_o √H_o.
- A_T = 2(LW + LH + WH) − A_o (all interior surfaces minus the opening).
- Thermal penetration time t_p = (ρc/k)(δ/2)². h_k = √(kρc/t) for t < t_p, else k/δ. Units: k kW/m·K, ρ kg/m³, c kJ/kg·K, δ m.
- Correlation fit is for layer temperatures below ~600 °C; show results above that as out of range.
- Materials (NUREG-1805 typical): gypsum board k 0.00017, ρ 960, c 1.1 (16 mm); concrete 0.0016, 2400, 0.75 (150 mm); brick 0.0008, 2600, 0.8 (100 mm); plywood 0.00012, 540, 2.5 (13 mm); fiber insulation board 0.00053, 240, 1.25 (25 mm).

### Step 3: Flashover and air supply limit
- Ventilation limit: Q_vent = 1500 · A_o √H_o kW. The fire actually used everywhere is Q_eff(t) = min(α t², Q_max, Q_vent).
- Babrauskas: Q_FO = 750 · A_o √H_o.
- Thomas: Q_FO = 7.8 · A_T + 378 · A_o √H_o.
- MQH: time when the Step 2 layer temperature reaches T_a + 500 °C (equivalent to Q_FO = 610 (h_k A_T A_o √H_o)^½); report Q_eff at that time.
- Report the range of times the fire reaches each threshold; "None" if no method is reached.

### Step 4: Smoke filling and egress (ASET vs RSET)
- Two-zone mass balance, explicit Euler, dt = 0.25 s. Layer mass m; layer density ρ_g = 353 / T_g(K) with T_g from MQH using Q_eff; interface height z = H − m / (ρ_g · floor area), clamped at ≥ 0.
- Plume entrainment (Heskestad), convective fraction 0.7: ṁ_p = 0.071 Q_c^(1/3) z^(5/3) + 0.0018 Q_c (kg/s); fire at floor level, no virtual origin correction.
- Door outflow once z < door height: ṁ_out = (2/3) C_d W ρ_g √(2 g (1 − T_a/T_g) T_g/T_a) (H_d − z)^(3/2), C_d = 0.7.
- dm/dt = ṁ_p − ṁ_out.
- ASET = earliest of: z ≤ 1.8 m, or layer temperature ≥ 200 °C.
- RSET = detection time + reaction (pre-movement) time + walk distance / walking speed.
- Occupant presets: awake with alarm (30, 30, 4 m, 1.2 m/s); asleep with alarm (30, 120, 4 m, 1.0 m/s); awake no alarm (90, 60, 4 m, 1.2 m/s); needs help (30, 90, 4 m, 0.5 m/s).

### Fire protection (added after the prototype; method and data from NUREG-1805 Supplement 1, Ch. 10)
- Ceiling jet (Alpert 1972), total Q, H = room height (fire at floor), r = horizontal distance: T_jet − T_a = 16.9 Q^(2/3)/H^(5/3) for r/H ≤ 0.18, else 5.38 (Q/r)^(2/3)/H; u_jet = 0.96 (Q/H)^(1/3) for r/H ≤ 0.15, else 0.195 Q^(1/3) H^(1/2)/r^(5/6).
- Device heating: dT_d/dt = √u_jet/RTI (T_jet − T_d), Euler dt = 0.25 s with Q_eff(t) (DETACT-QS). Steady-fire check: t_act = RTI/√u ln[(T_jet − T_a)/(T_jet − T_act)].
- Sprinkler: when it activates, the fire is held at Q_eff(t_act) (equivalent to lowering the peak HRR). Heat detector: its activation time replaces the occupant's detection time; if it never activates, RSET is unknown.
- Data: sprinkler RTI 34 / 42 / 130 / 235 (m·s)^½ for quick link / quick bulb / standard link / standard bulb (Madrzykowski 1995); generic ratings ordinary 165 °F, intermediate 212 °F, high 275 °F, extra high 350 °F, very extra high 450 °F (NFPA ASSH); heat detector RTI by rating and UL listed spacing from NFPA 72 Table B-3.2.5.1 (all as tabulated in the NUREG-1805 spreadsheet).

### Flame height (3D view and the flame-tip check only)
- Heskestad: L = 0.235 Q^(2/5) − 1.02 D (NUREG-1805 Ch. 3), clipped at 0. Burning diameter grows with the fire, D = D_full √(Q/Q_peak) (a t-squared fire is steady spread at constant HRR per unit area, so area ∝ Q). D_full is a user input (default 1.0 m, an assumption).
- The 3D view draws the flames from the top of the burning furniture (illustrative sizes per fuel, e.g. a 0.45 m sofa seat) and its description measures "reaches the ceiling" from there; the calculation itself keeps the fire at floor level (more plume entrainment, the cautious choice). Smoke color: gray to charcoal with temperature, glowing toward red above the Draper point (≈525 °C).

## Check values (the rebuilt model must match these)

Fast fire (α = 0.0469), sofa peak 2500 kW, 16 mm gypsum.

Bedroom 5 × 4 × 2.4 m, door 0.9 × 2.0 m:
- t_p ≈ 398 s; opening factor 2.546; A_T 81.4 m²
- T_g at t = 150 s (Q = 1055 kW): ≈ 388 °C. At 231 s (Q = 2500 kW): ≈ 723 °C. With 150 mm concrete at 150 s: ≈ 252 °C (an earlier value of ≈ 278 °C is what concrete gives if the lining thickness is left at 16 mm: t_p is then 72 s, so h_k = k/δ at 150 s)
- Babrauskas 1909 kW; Thomas 1597 kW; Q_vent 3818 kW; MQH flashover at 184 s
- Smoke layer reaches 1.8 m at 29 s; z at 60 / 120 / 300 s ≈ 1.22 / 0.88 / 0.10 m

Dorm example 4.5 × 3.5 × 2.6 m, door 0.9 × 2.1 m: Babrauskas 2054, Thomas 1591, Q_vent 4108 kW; MQH flashover 182 s; 1.8 m at 29 s.

Living room 7 × 6 × 2.4 m, door 1.8 × 2.1 m, slow fire, chair 750 kW: no flashover; 1.8 m at 86 s; z at 600 s ≈ 1.25 m.

RSET for "awake with alarm" = 63.3 s.

## Validation against NUREG-1805

`fire_model/validation.py` holds 33 comparisons with the NRC's NUREG-1805 Supplement 1 spreadsheets (copies in `docs/nureg-1805/`, inputs and answers with cell references); `tests/test_nureg1805.py` requires all to pass. Formulas agree to the NRC's printed precision; the full MQH chain is +0.12% (NRC rounds concrete k·ρ·c to 2.9); the 500 K MQH flashover criterion is +2.2% above the 610 closed form; DETACT-QS time stepping is within 0.3% of the steady-fire formula. NUREG-1805 does not cover this project's smoke-filling method. The report PDFs (ML13211A097/098) could not be downloaded automatically (NRC blocks automated access to /docs/); their worked examples are a possible addition.

## Known limitations (keep listed in the app)

Single room, single opening; fire at floor, never decays; a sprinkler only stops fire growth (no cooling or suppression); Alpert's correlations are for an unconfined ceiling, so in a small room activation tends to be predicted late; one average layer temperature from MQH (used outside its original purpose in the filling model); door outflow ignores the neutral plane and inflow below it, so late-time layer heights near the floor are approximate (once the room is smoke-logged the plume still delivers slightly more mass than the door removes, so z chatters between 0 and ~0.1 m; the z ≈ 0.10 m check value at 300 s is a point on that chatter); Heskestad's plume equation is for heights above the flame tip, so it is used outside its range when the layer is below the flames; flame height depends on the assumed fire diameter; tenability uses layer height and temperature only (no toxicity or visibility); occupant walks straight at constant speed.

## Ideas for later (in rough priority order)
Done: NUREG-1805 validation (spreadsheet examples), sprinkler / heat detector activation, SI / US unit toggle.
1. Add the worked examples from the NUREG-1805 report volumes (PDF) to `fire_model/validation.py`.
2. Smoke detector activation (NUREG-1805 Ch. 10 has a smoke detector sheet), so smoke alarm times can be calculated.
3. Fire decay phase and total fuel load.
4. Compare one scenario with NIST CFAST (free zone model).
5. Export a one-page PDF report of a scenario.

## References
- NFPA 72, Annex B (t-squared fires)
- McCaffrey, Quintiere & Harkleroad, Fire Technology 17 (1981)
- Babrauskas (1980); Thomas (1981) flashover correlations
- Heskestad, plume chapter, SFPE Handbook of Fire Protection Engineering
- U.S. NRC NUREG-1805, Fire Dynamics Tools (Supplement 1, 2013, spreadsheets v1805.1)
- Alpert, Fire Technology 8 (1972): ceiling jet
- Madrzykowski, ASIAFLAM'95 (1995): sprinkler RTI; NFPA Automatic Sprinkler Systems Handbook: ratings; NFPA 72 Table B-3.2.5.1: heat detector RTI
- U.S. NRC NUREG-1824, V&V of fire models (experimental validation of the FDTs)
- SFPE Engineering Guide to Human Behavior in Fire (ASET/RSET)
