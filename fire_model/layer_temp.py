"""
Step 2: Hot gas layer temperature (MQH method).

The fire plume carries hot gas up to the ceiling, where it collects as a smoke
layer. McCaffrey, Quintiere and Harkleroad (Fire Technology 17, 1981) fitted a
correlation for the layer's average temperature rise from an energy balance:
heat comes in from the fire and leaves through the door and into the walls.

    dT_g = 6.85 * [ Q^2 / (A_o*sqrt(H_o) * h_k * A_T) ]^(1/3)        (K)

    Q          heat release rate (kW)
    A_o*sqrt(H_o)   opening factor (m^(5/2)), see room.py
    A_T        interior surface area minus the opening (m^2), see room.py
    h_k        effective heat transfer coefficient of the walls (kW/m^2.K)

The correlation was fitted to tests with layer temperatures below about 600 °C,
so results above that are outside its range.

Units for wall materials (as in NUREG-1805):
    k   thermal conductivity   kW/(m.K)
    rho density                kg/m^3
    c   specific heat          kJ/(kg.K)
    delta (thickness)          m
"""

import math
from dataclasses import dataclass

from fire_model.room import interior_surface_area, opening_factor

T_AMBIENT = 20.0  # ambient (starting) temperature, °C

# Upper end of the temperature range the MQH correlation was fitted to, °C.
MQH_UPPER_LIMIT = 600.0

# Correlation constant in the MQH equation (McCaffrey, Quintiere & Harkleroad 1981).
MQH_CONSTANT = 6.85


@dataclass(frozen=True)
class Lining:
    """Wall and ceiling lining material."""

    name: str
    k: float  # thermal conductivity, kW/(m.K)
    rho: float  # density, kg/m^3
    c: float  # specific heat, kJ/(kg.K)
    thickness: float  # m


# Typical lining properties from NUREG-1805 (values and default thicknesses
# as listed in CLAUDE.md).
LININGS = {
    "Gypsum board": Lining("Gypsum board", k=0.00017, rho=960, c=1.1, thickness=0.016),
    "Concrete": Lining("Concrete", k=0.0016, rho=2400, c=0.75, thickness=0.150),
    "Brick": Lining("Brick", k=0.0008, rho=2600, c=0.8, thickness=0.100),
    "Plywood": Lining("Plywood", k=0.00012, rho=540, c=2.5, thickness=0.013),
    "Fiber insulation board": Lining(
        "Fiber insulation board", k=0.00053, rho=240, c=1.25, thickness=0.025
    ),
}


def thermal_penetration_time(lining):
    """t_p (s): roughly how long heat takes to soak through the lining.

        t_p = (rho c / k) * (delta / 2)^2

    rho*c/k is the inverse of the thermal diffusivity, so a dense, poorly
    conducting material takes longer to heat through.
    """
    return (lining.rho * lining.c / lining.k) * (lining.thickness / 2) ** 2


def wall_heat_transfer_coefficient(t, lining):
    """h_k (kW/m^2.K): how readily the walls absorb heat from the hot layer.

    Before t_p, heat has not reached the back of the wall, so the wall behaves
    like a very thick (semi-infinite) solid. Its surface warms up over time and
    it absorbs heat less and less readily:   h_k = sqrt(k rho c / t)

    After t_p, heat conducts steadily through the full thickness:
                                              h_k = k / delta
    """
    if t < thermal_penetration_time(lining):
        return math.sqrt(lining.k * lining.rho * lining.c / t)
    return lining.k / lining.thickness


def mqh_layer_temperature(t, hrr, room, lining):
    """Average hot gas layer temperature (°C) at time t (s) for a fire of
    `hrr` kW, using the MQH correlation."""
    # Before ignition (or with no fire) the room is at ambient. This also avoids
    # dividing by zero in h_k = sqrt(k rho c / t) at t = 0.
    if t <= 0 or hrr <= 0:
        return T_AMBIENT

    h_k = wall_heat_transfer_coefficient(t, lining)
    heat_loss_term = opening_factor(room) * h_k * interior_surface_area(room)
    temperature_rise = MQH_CONSTANT * (hrr**2 / heat_loss_term) ** (1 / 3)
    return T_AMBIENT + temperature_rise


def is_within_mqh_range(temperature):
    """True if a layer temperature (°C) is inside the range MQH was fitted to."""
    return temperature <= MQH_UPPER_LIMIT
