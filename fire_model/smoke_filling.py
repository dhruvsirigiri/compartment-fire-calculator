"""
Step 4 (part 1): Smoke filling, how fast the smoke layer drops toward the floor.

Two-zone model: the room is split into a hot smoke layer under the ceiling and
cool, clear air below it. The boundary between them (the "interface") is at
height z above the floor.

Mass balance on the smoke layer (m = mass of hot gas in the layer, kg):

    dm/dt = m_plume - m_door                                         (kg/s)

  * m_plume: the plume rising from the fire pulls in (entrains) room air as it
    rises, so it delivers far more mass to the layer than the fuel itself
    produces. Heskestad plume, fire at floor level, no virtual origin:
        m_plume = 0.071 Q_c^(1/3) z^(5/3) + 0.0018 Q_c,   Q_c = 0.7 Q

  * m_door: once the layer is deeper than the top of the door (z < H_d), hot gas
    spills out of the doorway, driven by buoyancy:
        m_door = (2/3) C_d W rho_g sqrt(2 g (1 - T_a/T_g) T_g/T_a) (H_d - z)^(3/2)

From mass to height: the layer's density comes from the ideal gas law,
rho_g = 353 / T_g (T_g in K), using the Step 2 (MQH) layer temperature, so

    layer depth = m / (rho_g * floor area),     z = H - depth   (never below 0)

The equation is solved step by step with the explicit Euler method:
    m(t + dt) = m(t) + (m_plume - m_door) * dt,     dt = 0.25 s
"""

import math

from fire_model.flashover import effective_hrr
from fire_model.layer_temp import T_AMBIENT, mqh_layer_temperature
from fire_model.room import floor_area

GRAVITY = 9.81  # m/s^2
CONVECTIVE_FRACTION = 0.7  # share of the fire's heat carried up by the plume
DOOR_FLOW_COEFFICIENT = 0.7  # C_d, accounts for the flow contracting through the door
TIME_STEP = 0.25  # s, Euler time step


def kelvin(temperature_c):
    """Convert °C to K."""
    return temperature_c + 273.15


def gas_density(temperature_k):
    """Density of hot gas (kg/m^3) from the ideal gas law at atmospheric pressure.
    For air, rho * T is about 353 kg.K/m^3, so hotter gas is lighter."""
    return 353.0 / temperature_k


def plume_mass_flow(hrr, z):
    """Mass flow (kg/s) the Heskestad plume carries up into the smoke layer.

    hrr: fire size (kW).  z: height of the layer interface above the fire (m).
    The taller the clear air column the plume rises through, the more air it
    entrains, which is why the flow grows with z^(5/3).
    """
    if hrr <= 0 or z <= 0:
        return 0.0
    q_convective = CONVECTIVE_FRACTION * hrr  # Q_c, kW
    return 0.071 * q_convective ** (1 / 3) * z ** (5 / 3) + 0.0018 * q_convective


def door_outflow(room, z, layer_temp_k):
    """Mass flow of smoke (kg/s) out through the top of the door.

    Smoke only leaves once the layer interface z is below the door top. The hot
    layer is lighter than the outside air, so there is a pressure difference
    across the doorway that grows with depth below the door top; integrating the
    resulting velocity over the depth of smoke in the doorway, (H_d - z), gives
    the 3/2 power.

    Simplification (see Known limitations): the outflow is measured from the
    layer interface rather than the neutral plane, and air inflow below it is
    not modelled.
    """
    if z >= room.door_height:
        return 0.0
    ambient_k = kelvin(T_AMBIENT)
    rho_g = gas_density(layer_temp_k)
    # (rho_a - rho_g) / rho_a = 1 - T_a/T_g for an ideal gas; zero if not hot.
    buoyancy = max(0.0, 1.0 - ambient_k / layer_temp_k)
    velocity_scale = math.sqrt(2 * GRAVITY * buoyancy * layer_temp_k / ambient_k)
    return (
        (2 / 3)
        * DOOR_FLOW_COEFFICIENT
        * room.door_width
        * rho_g
        * velocity_scale
        * (room.door_height - z) ** 1.5
    )


def smoke_layer_heights(alpha, peak_hrr, room, lining, t_end, dt=TIME_STEP):
    """Height of the bottom of the smoke layer (m) at every whole second.

    Returns a list where result[t] is the interface height at t seconds,
    for t = 0, 1, ..., t_end. At t = 0 there is no smoke, so z = room height.
    """
    steps_per_second = round(1 / dt)
    if abs(steps_per_second * dt - 1) > 1e-9:
        raise ValueError("dt must divide 1 second evenly (e.g. 0.5, 0.25, 0.1)")

    area = floor_area(room)
    mass = 0.0  # kg of hot gas in the smoke layer
    heights = [room.height]  # t = 0: layer bottom is at the ceiling

    n_steps = int(t_end) * steps_per_second
    for step in range(1, n_steps + 1):
        t = step * dt

        # Fire size and layer temperature/density at this moment
        hrr = effective_hrr(t, alpha, peak_hrr, room)
        layer_temp_k = kelvin(mqh_layer_temperature(t, hrr, room, lining))
        rho_g = gas_density(layer_temp_k)

        # Where is the bottom of the layer right now?
        z = max(0.0, room.height - mass / (rho_g * area))

        # Euler step:  m_new = m + (dm/dt) * dt,  with dm/dt = in - out
        dm_dt = plume_mass_flow(hrr, z) - door_outflow(room, z, layer_temp_k)
        mass = max(0.0, mass + dm_dt * dt)

        # Record the height once per whole second
        if step % steps_per_second == 0:
            heights.append(max(0.0, room.height - mass / (rho_g * area)))

    return heights
