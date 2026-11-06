"""
Sprinkler and heat detector activation (ceiling jet + RTI).

When the fire plume hits the ceiling it turns and spreads out as a thin, hot,
fast layer of gas: the "ceiling jet". A sprinkler or heat detector sits in that
jet and heats up with a delay. How quickly it heats is set by its Response Time
Index (RTI): a small RTI means a thin, fast-responding element ("quick response").
It activates when its own temperature reaches its rated activation temperature.

Method and data as in U.S. NRC NUREG-1805 Supplement 1, Chapter 10 (spreadsheet
10-detector-activation-time-sup1-si.xls, sheets "Sprinkler" and "FTHDetector").

Ceiling jet (Alpert 1972). Q = total heat release rate (kW), H = height of the
ceiling above the fuel (m), r = horizontal distance from the fire's centreline (m):

    T_jet - T_a = 16.9 Q^(2/3) / H^(5/3)            for r/H <= 0.18
    T_jet - T_a = 5.38 (Q/r)^(2/3) / H              for r/H >  0.18

    u_jet = 0.96 (Q/H)^(1/3)                        for r/H <= 0.15
    u_jet = 0.195 Q^(1/3) H^(1/2) / r^(5/6)         for r/H >  0.15

Device heating (the RTI model): the element warms toward the gas temperature,
faster when the gas moves faster:

    dT_d/dt = sqrt(u_jet) / RTI * (T_jet - T_d)

For a steady fire this has an exact solution (the NUREG-1805 equation):

    t_act = RTI / sqrt(u_jet) * ln[(T_jet - T_a) / (T_jet - T_act)]

For a growing fire the ceiling jet changes every moment, so the same equation is
stepped forward in time with the current fire size, the "DETACT-QS" approach
(quasi-steady: Alpert's steady-fire correlations applied at each instant).
"""

import math
from dataclasses import dataclass

from fire_model.layer_temp import T_AMBIENT

TIME_STEP = 0.25  # s, same Euler step as the smoke filling model


def fahrenheit_to_celsius(temp_f):
    """Convert °F to °C (the source tables give temperature ratings in °F)."""
    return (temp_f - 32) * 5 / 9


# Generic sprinkler RTI values, (m.s)^(1/2). Madrzykowski (1995), as tabulated in
# NUREG-1805 Ch. 10, "Sprinkler" sheet, cells B33:D36.
SPRINKLER_RTI = {
    "Quick response link": 34.0,
    "Quick response bulb": 42.0,
    "Standard response link": 130.0,
    "Standard response bulb": 235.0,
}

# Generic sprinkler temperature ratings, °F. NFPA Automatic Sprinkler Systems
# Handbook (1994), as tabulated in NUREG-1805 Ch. 10, "Sprinkler" sheet, B45:E49.
SPRINKLER_RATING_F = {
    "Ordinary": 165.0,
    "Intermediate": 212.0,
    "High": 275.0,
    "Extra high": 350.0,
    "Very extra high": 450.0,
}

# Fixed-temperature heat detector RTI, (m.s)^(1/2), by rated activation
# temperature (°F) and UL listed spacing (ft). NFPA 72 (1999) Table B-3.2.5.1, as
# tabulated in NUREG-1805 Ch. 10, "FTHDetector" sheet, cells C36:E93.
HEAT_DETECTOR_RTI = {
    128.0: {10: 490, 15: 306, 20: 325, 25: 152, 30: 116, 40: 87, 50: 72, 70: 44},
    135.0: {10: 404, 15: 233, 20: 165, 25: 123, 30: 98, 40: 70, 50: 54, 70: 20},
    145.0: {10: 321, 15: 191, 20: 129, 25: 96, 30: 75, 40: 50, 50: 37, 70: 11},
    160.0: {10: 239, 15: 135, 20: 86, 25: 59, 30: 44, 40: 22},
    170.0: {10: 196, 15: 109, 20: 64, 25: 39, 30: 27},
    196.0: {10: 119, 15: 55, 20: 21},
}


@dataclass(frozen=True)
class Device:
    """A sprinkler or heat detector on the ceiling."""

    name: str
    rti: float  # response time index, (m.s)^(1/2)
    activation_temp: float  # °C
    radial_distance: float  # m, horizontal distance from the fire's centreline


def ceiling_jet_temperature_rise(hrr, ceiling_height, radial_distance):
    """T_jet - T_a (K) in the ceiling jet, Alpert's correlation."""
    if hrr <= 0:
        return 0.0
    if radial_distance / ceiling_height <= 0.18:  # in the plume's turning region
        return 16.9 * hrr ** (2 / 3) / ceiling_height ** (5 / 3)
    return 5.38 * (hrr / radial_distance) ** (2 / 3) / ceiling_height


def ceiling_jet_velocity(hrr, ceiling_height, radial_distance):
    """Ceiling jet velocity u_jet (m/s), Alpert's correlation."""
    if hrr <= 0:
        return 0.0
    if radial_distance / ceiling_height <= 0.15:
        return 0.96 * (hrr / ceiling_height) ** (1 / 3)
    return 0.195 * hrr ** (1 / 3) * ceiling_height ** (1 / 2) / radial_distance ** (5 / 6)


def activation_time_steady(hrr, ceiling_height, device, ambient=T_AMBIENT):
    """Activation time (s) for a STEADY fire of `hrr` kW: the exact solution
    used in NUREG-1805. Returns None if the ceiling jet never gets hot enough."""
    t_jet = ambient + ceiling_jet_temperature_rise(hrr, ceiling_height, device.radial_distance)
    if t_jet <= device.activation_temp:
        return None
    u_jet = ceiling_jet_velocity(hrr, ceiling_height, device.radial_distance)
    return device.rti / math.sqrt(u_jet) * math.log((t_jet - ambient) / (t_jet - device.activation_temp))


def detector_response(fire_hrr, ceiling_height, device, t_end, dt=TIME_STEP, ambient=T_AMBIENT):
    """Heat a sprinkler or detector with a (growing) fire: DETACT-QS.

    fire_hrr is a function that gives the fire size (kW) at time t (s).
    Returns (activation_time, temps): the time (s) the device activates, or None
    if it doesn't within t_end, and its temperature (°C) at every whole second.
    """
    steps_per_second = round(1 / dt)
    device_temp = ambient
    temps = [ambient]
    activation = None
    for step in range(1, int(t_end) * steps_per_second + 1):
        t = step * dt
        q = fire_hrr(t)
        t_jet = ambient + ceiling_jet_temperature_rise(q, ceiling_height, device.radial_distance)
        u_jet = ceiling_jet_velocity(q, ceiling_height, device.radial_distance)

        # Euler step of  dT_d/dt = sqrt(u_jet)/RTI * (T_jet - T_d)
        device_temp += math.sqrt(u_jet) / device.rti * (t_jet - device_temp) * dt

        if activation is None and device_temp >= device.activation_temp:
            activation = t
        if step % steps_per_second == 0:
            temps.append(device_temp)
    return activation, temps
