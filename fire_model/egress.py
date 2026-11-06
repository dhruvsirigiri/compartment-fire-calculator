"""
Step 4 (part 2): Do people get out in time? ASET vs RSET.

Fire safety design compares two times (SFPE Engineering Guide to Human Behavior
in Fire):

  ASET, available safe egress time: how long until the room is untenable. Here
  that is the earlier of
    * the smoke layer interface drops to head height (1.8 m), so people would
      be breathing smoke, or
    * the smoke layer reaches 200 °C (painful radiant heat from above).

  RSET, required safe egress time: how long people need to get out.
      RSET = detection time + reaction (pre-movement) time + walk distance / walk speed

  The design works only if ASET > RSET. Safety margin = ASET - RSET.
"""

from dataclasses import dataclass

from fire_model.timeline import first_time_at_or_above, first_time_at_or_below

HEAD_HEIGHT = 1.8  # m, smoke below this height is breathed
TENABILITY_TEMP = 200.0  # °C, layer temperature causing painful radiant heat below

REASON_SMOKE_LOW = "Smoke reaches head height (1.8 m)"
REASON_SMOKE_HOT = "Smoke layer reaches 200 °C"


@dataclass(frozen=True)
class Occupant:
    """How one person responds to the fire."""

    detection_time: float  # s, from ignition until the alarm sounds
    reaction_time: float  # s, to notice, decide and start moving (pre-movement)
    walk_distance: float  # m, straight-line distance to the door
    walk_speed: float  # m/s


# Occupant presets from CLAUDE.md: (detection, reaction, distance, speed)
OCCUPANT_PRESETS = {
    "Awake, smoke alarm in room": Occupant(30, 30, 4, 1.2),
    "Asleep, smoke alarm in room": Occupant(30, 120, 4, 1.0),
    "Awake, no alarm (notices fire)": Occupant(90, 60, 4, 1.2),
    "Needs help to move": Occupant(30, 90, 4, 0.5),
}


def walking_time(occupant):
    """Time (s) to walk to the door at a constant speed."""
    if occupant.walk_speed <= 0:
        raise ValueError("walk_speed must be greater than zero")
    return occupant.walk_distance / occupant.walk_speed


def rset(occupant):
    """Required safe egress time (s) = detection + reaction + walking."""
    return occupant.detection_time + occupant.reaction_time + walking_time(occupant)


def distance_left_to_walk(t, occupant):
    """How far (m) the occupant still has to walk at time t (s).

    They start walking once the alarm has sounded and they have reacted
    (t = detection + reaction), then walk straight to the door at constant speed.
    """
    start_walking = occupant.detection_time + occupant.reaction_time
    walked = max(0.0, (t - start_walking) * occupant.walk_speed)
    return max(0.0, occupant.walk_distance - walked)


def occupant_status(t, occupant):
    """What the occupant is doing at time t (s), in words."""
    if t >= rset(occupant):
        return "Occupant is out"
    if t < occupant.detection_time:
        return "Alarm not yet sounding"
    if t < occupant.detection_time + occupant.reaction_time:
        return "Alarm sounding, occupant reacting"
    return "Occupant walking to door"


def aset(layer_heights, layer_temps):
    """Available safe egress time.

    layer_heights[t]: smoke interface height (m) at t seconds
    layer_temps[t]:   smoke layer temperature (°C) at t seconds

    Returns (time in s, reason), or (None, None) if the room stays tenable for
    the whole simulation. If both limits are reached in the same second, the
    smoke height is given as the reason.
    """
    t_low = first_time_at_or_below(layer_heights, HEAD_HEIGHT)
    t_hot = first_time_at_or_above(layer_temps, TENABILITY_TEMP)

    if t_low is not None and (t_hot is None or t_low <= t_hot):
        return t_low, REASON_SMOKE_LOW
    if t_hot is not None:
        return t_hot, REASON_SMOKE_HOT
    return None, None


def safety_margin(aset_time, rset_time):
    """ASET - RSET (s). Positive means people are out before it is untenable.
    None if the room never became untenable (ASET not reached), or if RSET is
    unknown because the alarm never sounded."""
    if aset_time is None or rset_time is None:
        return None
    return aset_time - rset_time
