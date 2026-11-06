"""
Step 1: Fire growth (the t-squared fire).

The heat release rate (HRR) is how much energy the fire gives off each second,
in kilowatts (kW). In the growth phase of many real fires the HRR rises roughly
with the square of time since ignition:

    Q(t) = alpha * t^2          Q in kW, t in s, alpha in kW/s^2

The fire then holds steady at a peak HRR set by what is burning. This model has
no decay phase: once the fire reaches its peak, it stays there.

Growth classes (NFPA 72, Annex B) are defined by the time t_g the fire takes to
reach 1055 kW (1000 BTU/s), so

    alpha = 1055 / t_g^2
"""

import math

# The HRR used to define the growth classes: 1000 BTU/s = 1055 kW.
REFERENCE_HRR = 1055.0  # kW

# Time for the fire to reach 1055 kW, for each growth class (NFPA 72 Annex B), s.
GROWTH_TIMES = {
    "slow": 600.0,
    "medium": 300.0,
    "fast": 150.0,
    "ultrafast": 75.0,
}

# Peak HRR presets for "what's burning", kW.
# These are rounded, generic examples (see CLAUDE.md), not measured data.
FUEL_PEAK_HRR = {
    "Wastebasket": 100.0,
    "Office chair": 750.0,
    "Upholstered armchair": 1200.0,
    "Mattress and bed": 2000.0,
    "Sofa": 2500.0,
}


def growth_coefficient(growth_time):
    """Growth coefficient alpha (kW/s^2) for a fire that reaches 1055 kW
    after `growth_time` seconds:  alpha = 1055 / t_g^2."""
    return REFERENCE_HRR / growth_time**2


def t_squared_hrr(t, alpha, peak_hrr):
    """Heat release rate (kW) at time t (s): Q = alpha * t^2, but never more
    than the peak HRR of the fuel (kW). No decay phase."""
    return min(alpha * t**2, peak_hrr)


def burning_diameter(hrr, peak_hrr, full_diameter):
    """Diameter (m) of the burning area while the fire grows.

    A t-squared fire is what you get when flames spread outward at a steady
    speed over fuel that releases a fixed amount of heat per square metre: the
    burning area then grows like t^2, just like Q. So the area is proportional to
    Q, and the diameter to sqrt(Q). It reaches `full_diameter` at the peak HRR.
    """
    if hrr <= 0 or peak_hrr <= 0:
        return 0.0
    return full_diameter * math.sqrt(min(1.0, hrr / peak_hrr))


def time_to_reach(hrr, alpha):
    """Time (s) for a t-squared fire to grow to `hrr` (kW).
    This is Q = alpha * t^2 solved for t:  t = sqrt(Q / alpha)."""
    return math.sqrt(hrr / alpha)
