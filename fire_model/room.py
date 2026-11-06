"""
The room (compartment) and its geometry.

Every calculation step needs the room's size and its door, so they live here
once instead of being repeated in each module. The room is a rectangular box
with a single rectangular opening (a door) in one wall. All lengths are in m.

Quantities used by the hand-calculation methods (definitions from CLAUDE.md):

    A_o        door area = door width * door height                     (m^2)
    H_o        door height                                              (m)
    A_o*sqrt(H_o)   the "opening factor"                                (m^(5/2))
    A_T        all interior surfaces (walls, ceiling, floor) minus the door:
               A_T = 2(LW + LH + WH) - A_o                              (m^2)
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    """A rectangular room with one door. All dimensions in metres."""

    length: float
    width: float
    height: float  # floor to ceiling
    door_width: float
    door_height: float


def door_area(room):
    """A_o: area of the opening (m^2)."""
    return room.door_width * room.door_height


def opening_factor(room):
    """A_o * sqrt(H_o) (m^(5/2)).

    This combination shows up in the ventilation, MQH and flashover equations
    because the flow of gas through a door is driven by buoyancy: the flow rate
    scales with the door's area times the square root of its height. A taller
    door lets hot gas out (and fresh air in) more effectively than a wide one of
    the same area.
    """
    return door_area(room) * math.sqrt(room.door_height)


def interior_surface_area(room):
    """A_T: total inside surface area of walls, ceiling and floor, minus the
    door opening (m^2). These are the surfaces that absorb heat from the fire."""
    L, W, H = room.length, room.width, room.height
    return 2 * (L * W + L * H + W * H) - door_area(room)


def floor_area(room):
    """Floor area (m^2). The smoke layer fills the room across this area."""
    return room.length * room.width
