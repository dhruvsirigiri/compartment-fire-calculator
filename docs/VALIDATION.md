# Validation against NUREG-1805

This project's model was checked against the U.S. Nuclear Regulatory Commission's
**Fire Dynamics Tools** (NUREG-1805 Supplement 1, spreadsheet version 1805.1, SI
units). Each NRC spreadsheet ships with a worked example already filled in; the
model was run on the same inputs and compared with the NRC's answers.

**Result: 33 of 33 comparisons agree within their tolerance.**

The comparisons are defined in [`fire_model/validation.py`](../fire_model/validation.py)
and run by [`tests/test_nureg1805.py`](../tests/test_nureg1805.py) every time the
tests run. Copies of the spreadsheets are in [`docs/nureg-1805/`](nureg-1805/).
This table was generated from that code.

## The NRC examples

| NUREG-1805 chapter | Example inputs (from the spreadsheet) |
|---|---|
| 2.1 Hot gas layer temperature, natural ventilation (MQH) | Room 3.7 × 3.05 × 2.44 m; vent 0.914 × 1.22 m; 152 mm concrete; steady 300 kW fire; results at 1, 2, 5, 10, 30 and 60 min |
| 13 Compartment flashover | Room 30.48 × 5.49 × 3.048 m; vent 0.914 × 2.44 m; 152.4 mm concrete (h_k = k/δ) |
| 10 Sprinkler response | Steady 1000 kW; ceiling 3 m above the fuel; r = 3 m; quick-response bulb RTI 42 (m·s)½; 100 °C (212 °F) rating; ambient 25 °C |
| 10 Fixed-temperature heat detector | Steady 1000 kW; ceiling 4 m; r = 3 m; RTI 306 (m·s)½; 53.3 °C (128 °F) rating; ambient 25 °C |
| 3 Flame height (Heskestad) | Five rows of the pool-fire table (diameter 0.34 to 3.44 m, 200 to 33,113 kW) |

## Results

| Method | Quantity | NRC | Model | Unit | Difference | Tolerance | Agrees | Source (file, cell) |
|---|---|---:|---:|---|---:|---:|:---:|---|
| MQH temperature | Vent area A_o | 1.11508 | 1.11508 | m² | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F113 |
| MQH temperature | Surface area A_T | 54.3949 | 54.3949 | m² | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F151 |
| MQH temperature | Thermal penetration time t_p | 6,498 | 6,498 | s | 0.000% | ±0.01% | ✓ | `02.1-temperature-nv-sup1-si.xls` F126 |
| MQH temperature | Temperature rise at 60 s, NRC's h_k | 125.232 | 125.232 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F169 |
| MQH temperature | Temperature rise at 60 s, model's h_k | 125.232 | 125.377 | K | +0.115% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F169 |
| MQH temperature | Temperature rise at 120 s, NRC's h_k | 140.568 | 140.568 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F170 |
| MQH temperature | Temperature rise at 120 s, model's h_k | 140.568 | 140.73 | K | +0.116% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F170 |
| MQH temperature | Temperature rise at 300 s, NRC's h_k | 163.761 | 163.761 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F173 |
| MQH temperature | Temperature rise at 300 s, model's h_k | 163.761 | 163.95 | K | +0.115% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F173 |
| MQH temperature | Temperature rise at 600 s, NRC's h_k | 183.816 | 183.816 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F174 |
| MQH temperature | Temperature rise at 600 s, model's h_k | 183.816 | 184.028 | K | +0.115% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F174 |
| MQH temperature | Temperature rise at 1800 s, NRC's h_k | 220.751 | 220.751 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F178 |
| MQH temperature | Temperature rise at 1800 s, model's h_k | 220.751 | 221.006 | K | +0.115% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F178 |
| MQH temperature | Temperature rise at 3600 s, NRC's h_k | 247.784 | 247.784 | K | 0.000% | ±0.001% | ✓ | `02.1-temperature-nv-sup1-si.xls` F184 |
| MQH temperature | Temperature rise at 3600 s, model's h_k | 247.784 | 248.07 | K | +0.116% | ±0.2% | ✓ | `02.1-temperature-nv-sup1-si.xls` F184 |
| Flashover | Surface area A_T | 551.713 | 551.713 | m² | 0.000% | ±0.001% | ✓ | `13-compartment-flashover-calculations-sup1-si.xls` E107 |
| Flashover | Babrauskas Q_FO | 2,612.72 | 2,612.72 | kW | 0.000% | ±0.001% | ✓ | `13-compartment-flashover-calculations-sup1-si.xls` D131 |
| Flashover | Thomas Q_FO | 5,620.17 | 5,620.17 | kW | 0.000% | ±0.001% | ✓ | `13-compartment-flashover-calculations-sup1-si.xls` D150 |
| Flashover | MQH Q_FO, 610 closed form | 2,740.12 | 2,740.12 | kW | 0.000% | ±0.001% | ✓ | `13-compartment-flashover-calculations-sup1-si.xls` D113 |
| Flashover | MQH Q_FO, model's 500 K criterion | 2,740.12 | 2,801.3 | kW | +2.233% | ±2.5% | ✓ | `13-compartment-flashover-calculations-sup1-si.xls` D113 |
| Sprinkler | Ceiling jet temperature rise | 86.2145 | 86.2145 | K | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` D99 |
| Sprinkler | Ceiling jet velocity | 1.35205 | 1.35205 | m/s | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` D120 |
| Sprinkler | Activation time, steady formula | 73.6723 | 73.6723 | s | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` C125 |
| Sprinkler | Activation time, model's time stepping | 73.6723 | 73.5 | s | -0.234% | ±1% | ✓ | `10-detector-activation-time-sup1-si.xls` C125 |
| Heat detector | Ceiling jet temperature rise | 64.6609 | 64.6609 | K | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` E138 |
| Heat detector | Ceiling jet velocity | 1.56122 | 1.56122 | m/s | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` E159 |
| Heat detector | Activation time, steady formula | 141.205 | 141.205 | s | 0.000% | ±0.001% | ✓ | `10-detector-activation-time-sup1-si.xls` D164 |
| Heat detector | Activation time, model's time stepping | 141.205 | 141.25 | s | +0.032% | ±1% | ✓ | `10-detector-activation-time-sup1-si.xls` D164 |
| Flame height | Flame height, D = 0.34393 m, Q = 200 kW | 1.60694 | 1.60694 | m | 0.000% | ±0.01% | ✓ | `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` F178 |
| Flame height | Flame height, D = 0.769051 m, Q = 1,448 kW | 3.53474 | 3.53474 | m | 0.000% | ±0.01% | ✓ | `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` F182 |
| Flame height | Flame height, D = 1.0876 m, Q = 3,136 kW | 4.77387 | 4.77387 | m | 0.000% | ±0.01% | ✓ | `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` F187 |
| Flame height | Flame height, D = 1.71965 m, Q = 8,199 kW | 6.88726 | 6.88726 | m | 0.000% | ±0.01% | ✓ | `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` F194 |
| Flame height | Flame height, D = 3.4393 m, Q = 33,113 kW | 11.5951 | 11.5951 | m | 0.000% | ±0.01% | ✓ | `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` F197 |

## What the differences mean

- **The formulas themselves match to the NRC's printed precision** (6 significant
  figures): MQH, Babrauskas, Thomas, MQH 610, Alpert's ceiling jet temperature and
  velocity, the steady-fire activation time, and Heskestad's flame height.
- **+0.12% on the full MQH chain.** The NRC tables round concrete's thermal inertia
  k·ρ·c to 2.9, while the model multiplies k, ρ and c (0.0016 × 2400 × 0.75 = 2.88).
  Giving the model 2.9 makes the difference disappear; the tests check this.
- **+2.2% on the MQH flashover criterion.** The model finds MQH flashover when the
  layer is 500 K above ambient. Solving the MQH equation exactly for 500 K gives a
  coefficient of about 624 rather than the published 610, which corresponds to a
  493 K rise. The 610 closed form itself matches the NRC exactly.
- **Below 0.3% on activation times stepped through time.** The NRC example is a
  steady fire with an exact formula. The model steps the device temperature
  forward every 0.25 s (DETACT-QS) so that it also works for growing fires; with a
  steady fire it lands within 0.25 s of the exact answer.
- **The ambient temperature** in the NRC examples is 25 °C (the model uses 20 °C),
  so temperature rises are compared; the rise does not depend on ambient.

## What this does and doesn't show

It shows the **equations are implemented correctly**: given the same inputs, the
model produces the same numbers as the NRC's own tools.

It does **not** cover:

- **Step 4 smoke filling.** NUREG-1805 estimates smoke layer height with a different
  method (Yamana and Tanaka, for a closed room), so this model's two-zone filling
  with door outflow could not be compared this way. It is checked against the
  original prototype (to about 1e-13 at every second) and by physical sanity tests.
- **How close the correlations are to real fires.** That is a question of
  experimental validation. The NRC compared these Fire Dynamics Tools with
  full-scale experiments in NUREG-1824 (Verification and Validation of Selected
  Fire Models for Nuclear Power Plant Applications, Volume 3).

The NUREG-1805 PDF report volumes (ML13211A097, ML13211A098) contain further worked
examples; they could be added as more cases in `fire_model/validation.py`.
