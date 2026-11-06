"""
Validation against the U.S. NRC's NUREG-1805 Fire Dynamics Tools.

Each NUREG-1805 Supplement 1 spreadsheet (version 1805.1, SI units) ships with a
worked example already filled in. The cases below give the NRC's inputs, the
NRC's answer (and the spreadsheet cell it was read from), and this model's
answer for the same inputs. Copies of the spreadsheets are in docs/nureg-1805/.

Two notes that apply to several cases:
  * The NRC examples use an ambient temperature of 25 °C, so temperature
    RISES are compared (the rise does not depend on ambient).
  * For concrete, the NRC tables round the thermal inertia k*rho*c to 2.9,
    while k, rho and c themselves (0.0016, 2400, 0.75) multiply to 2.88. That
    0.7% difference changes the MQH temperature rise by about 0.1%.
"""

from dataclasses import dataclass, replace

from fire_model.detection import (
    Device,
    activation_time_steady,
    ceiling_jet_temperature_rise,
    ceiling_jet_velocity,
    detector_response,
    fahrenheit_to_celsius,
)
from fire_model.flashover import babrauskas_flashover_hrr, mqh_flashover_hrr, thomas_flashover_hrr
from fire_model.layer_temp import (
    LININGS,
    T_AMBIENT,
    mqh_layer_temperature,
    mqh_temperature_rise,
    thermal_penetration_time,
)
from fire_model.room import Room, door_area, interior_surface_area
from fire_model.smoke_filling import flame_height

CH2 = "02.1-temperature-nv-sup1-si.xls, sheet Temperature-NV"
CH3 = "03-hrr-flame-height-burning-duration-calculations-sup1-si.xls, sheet HRR-Calculations"
CH10S = "10-detector-activation-time-sup1-si.xls, sheet Sprinkler"
CH10D = "10-detector-activation-time-sup1-si.xls, sheet FTHDetector"
CH13 = "13-compartment-flashover-calculations-sup1-si.xls, sheet Flashover_HRR"


@dataclass(frozen=True)
class ValidationCase:
    """One comparison between this model and a NUREG-1805 spreadsheet value."""

    topic: str  # which part of the model is being checked
    quantity: str  # what is compared
    unit: str
    nrc: float  # the NRC spreadsheet's value
    model: float  # this model's value for the same inputs
    source: str  # spreadsheet and cell
    tolerance_percent: float  # how close they must be (see the note)
    note: str = ""

    @property
    def difference_percent(self):
        return 100 * (self.model - self.nrc) / self.nrc

    @property
    def passes(self):
        return abs(self.difference_percent) <= self.tolerance_percent


# ---------------------------------------------------------------------------
# Chapter 2.1: hot gas layer temperature (MQH), natural ventilation.
# 3.7 m wide x 3.05 m long x 2.44 m high, vent 0.914 m wide x 1.22 m high,
# 152 mm concrete, steady 300 kW fire (cells F24:F31, F46:F49, F80).
# ---------------------------------------------------------------------------
CH2_ROOM = Room(length=3.05, width=3.7, height=2.44, door_width=0.914, door_height=1.22)
CH2_LINING = replace(LININGS["Concrete"], thickness=0.152)
CH2_HRR = 300.0
# (time s, NRC h_k kW/m2.K, NRC dT_g K, row) from the results table, columns D, E, F.
CH2_RESULTS = [
    (60, 0.219848, 125.232, 169),
    (120, 0.155456, 140.568, 170),
    (300, 0.0983192, 163.761, 173),
    (600, 0.0695222, 183.816, 174),
    (1800, 0.0401386, 220.751, 178),
    (3600, 0.0283823, 247.784, 184),
]


def mqh_cases():
    cases = [
        ValidationCase("MQH temperature (NUREG-1805 Ch. 2.1)", "Vent area A_o", "m²",
                       1.11508, door_area(CH2_ROOM), f"{CH2}, F113", 0.001),
        ValidationCase("MQH temperature (NUREG-1805 Ch. 2.1)", "Surface area A_T", "m²",
                       54.3949, interior_surface_area(CH2_ROOM), f"{CH2}, F151", 0.001),
        ValidationCase("MQH temperature (NUREG-1805 Ch. 2.1)", "Thermal penetration time t_p", "s",
                       6498.0, thermal_penetration_time(CH2_LINING), f"{CH2}, F126", 0.01),
    ]
    for t, h_k_nrc, dT_nrc, row in CH2_RESULTS:
        # (a) The MQH equation itself, with the NRC's own h_k: should agree exactly.
        cases.append(ValidationCase(
            "MQH temperature (NUREG-1805 Ch. 2.1)", f"Temperature rise at {t} s, NRC's h_k", "K",
            dT_nrc, mqh_temperature_rise(CH2_HRR, CH2_ROOM, h_k_nrc), f"{CH2}, F{row}", 0.001,
            "Same equation, same inputs."))
        # (b) The whole chain, with h_k from the model's own concrete properties.
        model_rise = mqh_layer_temperature(t, CH2_HRR, CH2_ROOM, CH2_LINING) - T_AMBIENT
        cases.append(ValidationCase(
            "MQH temperature (NUREG-1805 Ch. 2.1)", f"Temperature rise at {t} s, model's h_k", "K",
            dT_nrc, model_rise, f"{CH2}, F{row}", 0.2,
            "NRC rounds concrete's k·ρ·c to 2.9; the model uses 0.0016 × 2400 × 0.75 = 2.88."))
    return cases


# ---------------------------------------------------------------------------
# Chapter 13: flashover HRR. 30.48 m wide x 5.49 m long x 3.048 m high, vent
# 0.914 m wide x 2.44 m high, 152.4 mm concrete (cells F25:F31).
# ---------------------------------------------------------------------------
CH13_ROOM = Room(length=5.49, width=30.48, height=3.048, door_width=0.914, door_height=2.44)
CH13_H_K = 0.0016 / 0.1524  # k/delta, walls heated through (cell E83 = 0.0104987)


def flashover_cases():
    return [
        ValidationCase("Flashover (NUREG-1805 Ch. 13)", "Surface area A_T", "m²",
                       551.713, interior_surface_area(CH13_ROOM), f"{CH13}, E107", 0.001),
        ValidationCase("Flashover (NUREG-1805 Ch. 13)", "Babrauskas Q_FO", "kW",
                       2612.72, babrauskas_flashover_hrr(CH13_ROOM), f"{CH13}, D131", 0.001),
        ValidationCase("Flashover (NUREG-1805 Ch. 13)", "Thomas Q_FO", "kW",
                       5620.17, thomas_flashover_hrr(CH13_ROOM), f"{CH13}, D150", 0.001),
        ValidationCase("Flashover (NUREG-1805 Ch. 13)", "MQH Q_FO, 610 closed form", "kW",
                       2740.12, mqh_flashover_hrr(CH13_ROOM, CH13_H_K), f"{CH13}, D113", 0.001),
        ValidationCase(
            "Flashover (NUREG-1805 Ch. 13)", "MQH Q_FO, model's 500 K criterion", "kW",
            2740.12, mqh_equivalent_hrr_for_500k(CH13_ROOM, CH13_H_K), f"{CH13}, D113", 2.5,
            "Known: solving MQH exactly for a 500 K rise gives a coefficient of ~624 instead "
            "of the published 610, so the model's flashover criterion sits ~2.2% higher."),
    ]


def mqh_equivalent_hrr_for_500k(room, h_k):
    """Fire size (kW) at which the MQH temperature rise is exactly 500 K, the
    criterion the model uses for MQH flashover. Found by bisection, so it relies
    only on mqh_temperature_rise()."""
    low, high = 1.0, 1e6
    for _ in range(200):
        mid = (low + high) / 2
        if mqh_temperature_rise(mid, room, h_k) < 500:
            low = mid
        else:
            high = mid
    return (low + high) / 2


# ---------------------------------------------------------------------------
# Chapter 10: sprinkler and heat detector activation, steady 1000 kW fire.
# ---------------------------------------------------------------------------
NRC_AMBIENT = 25.0  # °C, used in the Chapter 10 examples (cells F25)
CH10_SPRINKLER = Device("Quick response bulb", rti=42.0, activation_temp=100.0, radial_distance=3.0)
CH10_SPRINKLER_H = 3.0  # m (cells F20:F25: Q = 1000 kW, RTI 42, 212 °F, H = 3 m, r = 3 m)
CH10_DETECTOR = Device("Heat detector 128 °F, 15 ft spacing", rti=306.0,
                       activation_temp=fahrenheit_to_celsius(128.0), radial_distance=3.0)
CH10_DETECTOR_H = 4.0  # m (cells F20:F25: Q = 1000 kW, r = 3 m, 128 °F, RTI 306, H = 4 m)


def detection_cases():
    def steady_1000_kw(t):
        return 1000.0

    spr_t_euler, _ = detector_response(steady_1000_kw, CH10_SPRINKLER_H, CH10_SPRINKLER, t_end=600,
                                       ambient=NRC_AMBIENT)
    det_t_euler, _ = detector_response(steady_1000_kw, CH10_DETECTOR_H, CH10_DETECTOR, t_end=600,
                                       ambient=NRC_AMBIENT)
    euler_note = ("The model steps the device temperature forward every 0.25 s (needed for "
                  "growing fires); the NRC uses the exact steady-fire formula.")
    return [
        ValidationCase("Sprinkler (NUREG-1805 Ch. 10)", "Ceiling jet temperature rise", "K",
                       86.2145, ceiling_jet_temperature_rise(1000, CH10_SPRINKLER_H, 3.0), f"{CH10S}, D99", 0.001),
        ValidationCase("Sprinkler (NUREG-1805 Ch. 10)", "Ceiling jet velocity", "m/s",
                       1.35205, ceiling_jet_velocity(1000, CH10_SPRINKLER_H, 3.0), f"{CH10S}, D120", 0.001),
        ValidationCase("Sprinkler (NUREG-1805 Ch. 10)", "Activation time, steady formula", "s",
                       73.6723, activation_time_steady(1000, CH10_SPRINKLER_H, CH10_SPRINKLER, NRC_AMBIENT),
                       f"{CH10S}, C125", 0.001),
        ValidationCase("Sprinkler (NUREG-1805 Ch. 10)", "Activation time, model's time stepping", "s",
                       73.6723, spr_t_euler, f"{CH10S}, C125", 1.0, euler_note),
        ValidationCase("Heat detector (NUREG-1805 Ch. 10)", "Ceiling jet temperature rise", "K",
                       64.6609, ceiling_jet_temperature_rise(1000, CH10_DETECTOR_H, 3.0), f"{CH10D}, E138", 0.001),
        ValidationCase("Heat detector (NUREG-1805 Ch. 10)", "Ceiling jet velocity", "m/s",
                       1.56122, ceiling_jet_velocity(1000, CH10_DETECTOR_H, 3.0), f"{CH10D}, E159", 0.001),
        ValidationCase("Heat detector (NUREG-1805 Ch. 10)", "Activation time, steady formula", "s",
                       141.205, activation_time_steady(1000, CH10_DETECTOR_H, CH10_DETECTOR, NRC_AMBIENT),
                       f"{CH10D}, D164", 0.001),
        ValidationCase("Heat detector (NUREG-1805 Ch. 10)", "Activation time, model's time stepping", "s",
                       141.205, det_t_euler, f"{CH10D}, D164", 1.0, euler_note),
    ]


# ---------------------------------------------------------------------------
# Chapter 3: Heskestad flame height. Rows of the table at cells A178:F197
# (pool area, diameter D, fire size Q, flame height).
# ---------------------------------------------------------------------------
CH3_ROWS = [  # (D m, Q kW, NRC flame height m, row)
    (0.34393, 200.319, 1.60694, 178),
    (0.769051, 1448.21, 3.53474, 182),
    (1.0876, 3135.94, 4.77387, 187),
    (1.71965, 8199.34, 6.88726, 194),
    (3.4393, 33113.1, 11.5951, 197),
]


def flame_height_cases():
    return [
        ValidationCase("Flame height (NUREG-1805 Ch. 3)", f"Flame height, D = {d:g} m, Q = {q:,.0f} kW", "m",
                       nrc, flame_height(q, d), f"{CH3}, F{row}", 0.01,
                       "NRC table values are rounded to 6 significant figures.")
        for d, q, nrc, row in CH3_ROWS
    ]


def all_cases():
    """Every comparison, in the order they are reported."""
    return mqh_cases() + flashover_cases() + detection_cases() + flame_height_cases()
