# NUREG-1805 reference spreadsheets

These are the U.S. Nuclear Regulatory Commission's official Fire Dynamics Tools
(FDTs) spreadsheets, SI-unit versions, from **NUREG-1805 Supplement 1** (2013),
spreadsheet version 1805.1. They are U.S. government works, kept here so the
validation in this project can be checked against the exact files used.

Source page (downloaded 6 November 2026):
https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr1805/s1/

| File | NUREG-1805 chapter | Used to validate |
|---|---|---|
| `02.1-temperature-nv-sup1-si.xls` | 2.1 Hot gas layer temperature, natural ventilation (MQH) | Step 2 (MQH temperature) |
| `13-compartment-flashover-calculations-sup1-si.xls` | 13 Compartment flashover | Step 3 (Babrauskas, Thomas, MQH) |
| `10-detector-activation-time-sup1-si.xls` | 10 Detector activation time (sprinkler and fixed-temperature heat detector sheets) | Sprinkler and heat detector activation; RTI and temperature-rating tables |
| `03-hrr-flame-height-burning-duration-calculations-sup1-si.xls` | 3 Fire HRR, flame height and burning duration | Heskestad flame height (3D view) |

Each spreadsheet ships with an example already filled in. The inputs and the
NRC's computed answers, with the cell each value was read from, are recorded in
`fire_model/validation.py` and checked by `tests/test_nureg1805.py`. The
comparison is written up in `docs/VALIDATION.md`.

The NUREG-1805 report volumes themselves (PDF) are at the same page
(ML13211A097 and ML13211A098).
