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

`index.html` is a working single-file prototype (HTML + vanilla JS, no build step). It is the reference implementation: the rebuilt app must reproduce its results (see "Check values" below). Open it in a browser to see the intended behavior and layout.

## Target architecture (recommended)

- `fire_model/` — Python package with the physics as pure functions, one module per step (`growth.py`, `layer_temp.py`, `flashover.py`, `smoke_filling.py`, `egress.py`), SI units throughout.
- `tests/` — pytest tests. Start with the check values below, then add NUREG-1805 example problems.
- `app.py` — Streamlit front end (inputs in sidebar, verdict at top, Plotly charts, explanations per step). Deploy free on Streamlit Community Cloud so there's a public link for the resume.
- `README.md` — what it does, the methods, screenshots, limits, references.
- Git repository pushed to GitHub (public), with a clear commit history.

Keep the physics independent of the UI so it can be tested and reused.

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

## Known limitations (keep listed in the app)

Single room, single opening; fire at floor, never decays; no sprinklers; one average layer temperature from MQH (used outside its original purpose in the filling model); door outflow ignores the neutral plane and inflow below it, so late-time layer heights near the floor are approximate (once the room is smoke-logged the plume still delivers slightly more mass than the door removes, so z chatters between 0 and ~0.1 m; the z ≈ 0.10 m check value at 300 s is a point on that chatter); Heskestad's plume equation is for heights above the flame tip, so it is used outside its range when the layer is below the flames; tenability uses layer height and temperature only (no toxicity or visibility); occupant walks straight at constant speed.

## Ideas for later (in rough priority order)
1. Validate every step against NRC NUREG-1805 (Fire Dynamics Tools) example problems and document the comparison.
2. Sprinkler / heat detector activation time (Alpert ceiling jet + RTI, DETACT-QS), and cap the fire when a sprinkler activates.
3. SI / US customary unit toggle (US firms use ft, °F, BTU/s).
4. Fire decay phase and total fuel load.
5. Compare one scenario with NIST CFAST (free zone model).
6. Export a one-page PDF report of a scenario.

## References
- NFPA 72, Annex B (t-squared fires)
- McCaffrey, Quintiere & Harkleroad, Fire Technology 17 (1981)
- Babrauskas (1980); Thomas (1981) flashover correlations
- Heskestad, plume chapter, SFPE Handbook of Fire Protection Engineering
- U.S. NRC NUREG-1805, Fire Dynamics Tools
- SFPE Engineering Guide to Human Behavior in Fire (ASET/RSET)
