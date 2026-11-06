"""
Units for the app: metric (SI) or US customary.

The physics in fire_model/ always works in SI, because the correlations
(MQH's 6.85, Alpert's 16.9 and 5.38, ...) only give the right answer with SI
inputs. This module just converts numbers on their way into and out of the
app, so a user can type and read feet, °F and Btu/s.

Conversion factors are exact definitions:
    1 ft  = 0.3048 m          1 in = 25.4 mm          1 lb = 0.45359237 kg
    1 Btu = 1.05505585262 kJ  (International Table Btu)
    °F = °C × 9/5 + 32        a temperature DIFFERENCE of 1 K = 1.8 °F
"""

M_PER_FT = 0.3048
KJ_PER_BTU = 1.05505585262
KG_PER_LB = 0.45359237
FT_PER_M = 1 / M_PER_FT

# kind: (SI unit, US unit, factor to multiply an SI value by to get US).
# Temperature is handled separately because it has an offset.
_LINEAR = {
    "length": ("m", "ft", FT_PER_M),
    "thickness": ("mm", "in", 1 / 25.4),
    "area": ("m²", "ft²", FT_PER_M**2),
    "opening_factor": ("m⁵ᐟ²", "ft⁵ᐟ²", FT_PER_M**2.5),
    "speed": ("m/s", "ft/s", FT_PER_M),
    "hrr": ("kW", "Btu/s", 1 / KJ_PER_BTU),
    "alpha": ("kW/s²", "Btu/s³", 1 / KJ_PER_BTU),
    "energy": ("MJ", "Btu", 1000 / KJ_PER_BTU),
    "mass_flow": ("kg/s", "lb/s", 1 / KG_PER_LB),
    "density": ("kg/m³", "lb/ft³", M_PER_FT**3 / KG_PER_LB),
    "rti": ("(m·s)½", "(ft·s)½", FT_PER_M**0.5),
    "temperature_rise": ("K", "°F", 1.8),
    "time": ("s", "s", 1.0),
}

SYSTEMS = ("Metric (SI)", "US customary")


class Units:
    """Converts between SI (used by the physics) and the chosen display system."""

    def __init__(self, system):
        if system not in SYSTEMS:
            raise ValueError(f"unknown unit system {system!r}")
        self.us = system == SYSTEMS[1]

    def unit(self, kind):
        """The unit label shown for a kind of quantity, e.g. 'ft'."""
        if kind == "temperature":
            return "°F" if self.us else "°C"
        si_unit, us_unit, _ = _LINEAR[kind]
        return us_unit if self.us else si_unit

    def show(self, kind, si_value):
        """Convert an SI value to the display system."""
        if si_value is None or not self.us:
            return si_value
        if kind == "temperature":
            return si_value * 9 / 5 + 32
        return si_value * _LINEAR[kind][2]

    def to_si(self, kind, value):
        """Convert a value in the display system back to SI."""
        if value is None or not self.us:
            return value
        if kind == "temperature":
            return (value - 32) * 5 / 9
        return value / _LINEAR[kind][2]

    def series(self, kind, si_values):
        """Convert a whole list (e.g. a time series)."""
        return [self.show(kind, v) for v in si_values]

    def fmt(self, kind, si_value, decimals=0):
        """Format an SI value for display, with its unit: e.g. '14.8 ft'."""
        if si_value is None:
            return "—"
        return f"{self.show(kind, si_value):,.{decimals}f} {self.unit(kind)}"
