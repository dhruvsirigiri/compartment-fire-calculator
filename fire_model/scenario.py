"""
Run every step of the model for one scenario.

This is the "glue" between the physics modules and the app: it runs Steps 1-4
in order and collects every result the app displays, so the app itself contains
no physics.

    Step 1  growth.py         t-squared fire
    Step 3  flashover.py      ...capped by the air supply  -> Q_eff(t)
    Step 2  layer_temp.py     MQH layer temperature using Q_eff(t)
    Step 4  smoke_filling.py  smoke layer height
    Step 3  flashover.py      when each flashover threshold is reached
    Step 4  egress.py         ASET, RSET and the safety margin

Time series are recorded once per whole second: series[t] is the value at t s.
"""

from dataclasses import dataclass

from fire_model.egress import HEAD_HEIGHT, TENABILITY_TEMP, aset, rset, safety_margin
from fire_model.flashover import (
    babrauskas_flashover_hrr,
    hrr_history,
    mqh_flashover_time,
    thomas_flashover_hrr,
    time_hrr_reaches,
    ventilation_limit,
)
from fire_model.growth import time_to_reach
from fire_model.layer_temp import MQH_UPPER_LIMIT, temperature_history, thermal_penetration_time
from fire_model.room import floor_area, interior_surface_area, opening_factor
from fire_model.smoke_filling import smoke_layer_heights
from fire_model.timeline import first_time_at_or_above, first_time_at_or_below


@dataclass(frozen=True)
class FlashoverMethod:
    """One row of the flashover table."""

    name: str
    threshold_hrr: float | None  # kW; for MQH, the fire size when it is reached
    time: int | None  # s, first whole second the fire reaches it (None = not reached)


@dataclass(frozen=True)
class ScenarioResult:
    """Everything the model predicts for one scenario."""

    t_end: int  # s, length of the simulation

    # Time series, one value per whole second (index = time in s)
    hrr: list  # Q_eff, kW
    layer_temp: list  # °C
    layer_height: list  # m

    # Room and wall properties
    opening_factor: float  # m^(5/2)
    interior_area: float  # A_T, m^2
    floor_area: float  # m^2
    penetration_time: float  # t_p, s

    # Fire size (Steps 1 and 3)
    ventilation_limit: float  # Q_vent, kW
    vent_limited: bool  # True if the air supply caps the fire below the fuel's peak
    time_vent_limited: float | None  # s, when the fire hits Q_vent (None if it never does)
    time_to_peak: float  # s, when the fire stops growing (may be after t_end)
    energy_released: float  # MJ, over the simulated time

    # Flashover (Step 3)
    flashover: list  # list of FlashoverMethod
    flashover_range: tuple | None  # (earliest, latest) time in s, None if no method reached

    # Smoke layer milestones (Steps 2 and 4), s or None
    time_layer_200c: int | None
    time_layer_600c: int | None
    time_smoke_at_door_top: int | None
    time_smoke_at_head_height: int | None

    # Life safety (Step 4)
    aset: int | None  # s
    aset_reason: str | None
    rset: float  # s
    safety_margin: float | None  # s, ASET - RSET (None if ASET not reached)


def run_scenario(alpha, peak_hrr, room, lining, occupant, t_end=600):
    """Run the whole model.

    alpha     fire growth coefficient (kW/s^2)
    peak_hrr  peak heat release rate of the fuel (kW)
    room      fire_model.room.Room
    lining    fire_model.layer_temp.Lining
    occupant  fire_model.egress.Occupant
    t_end     simulated time (s)
    """
    t_end = int(t_end)

    # --- Steps 1-4 as time series ---
    hrr = hrr_history(alpha, peak_hrr, room, t_end)  # Q_eff(t)
    temps = temperature_history(hrr, room, lining)  # MQH, using Q_eff(t)
    heights = smoke_layer_heights(alpha, peak_hrr, room, lining, t_end)

    # --- Fire size readouts ---
    q_vent = ventilation_limit(room)
    vent_limited = peak_hrr > q_vent
    time_vent_limited = time_to_reach(q_vent, alpha) if vent_limited else None
    # The fire stops growing at whichever cap it meets first.
    time_to_peak = time_to_reach(min(peak_hrr, q_vent), alpha)

    # Energy released = area under the HRR curve. The trapezoid rule on
    # 1-second intervals: sum of (Q[t-1] + Q[t]) / 2 * 1 s, in kJ -> MJ.
    energy_kj = sum((hrr[t - 1] + hrr[t]) / 2 for t in range(1, len(hrr)))

    # --- Step 3: flashover ---
    q_babrauskas = babrauskas_flashover_hrr(room)
    q_thomas = thomas_flashover_hrr(room)
    t_mqh = mqh_flashover_time(temps)
    flashover = [
        FlashoverMethod("Babrauskas", q_babrauskas, time_hrr_reaches(hrr, q_babrauskas)),
        FlashoverMethod("Thomas", q_thomas, time_hrr_reaches(hrr, q_thomas)),
        # For MQH the threshold is read off the temperature curve, so the
        # "minimum fire size" reported is the fire size at that moment.
        FlashoverMethod(
            "MQH (smoke at 520 °C)",
            hrr[t_mqh] if t_mqh is not None else None,
            t_mqh,
        ),
    ]
    reached = [m.time for m in flashover if m.time is not None]
    flashover_range = (min(reached), max(reached)) if reached else None

    # --- Step 4: life safety ---
    aset_time, aset_reason = aset(heights, temps)
    rset_time = rset(occupant)

    return ScenarioResult(
        t_end=t_end,
        hrr=hrr,
        layer_temp=temps,
        layer_height=heights,
        opening_factor=opening_factor(room),
        interior_area=interior_surface_area(room),
        floor_area=floor_area(room),
        penetration_time=thermal_penetration_time(lining),
        ventilation_limit=q_vent,
        vent_limited=vent_limited,
        time_vent_limited=time_vent_limited,
        time_to_peak=time_to_peak,
        energy_released=energy_kj / 1000,
        flashover=flashover,
        flashover_range=flashover_range,
        time_layer_200c=first_time_at_or_above(temps, TENABILITY_TEMP),
        time_layer_600c=first_time_at_or_above(temps, MQH_UPPER_LIMIT),
        time_smoke_at_door_top=first_time_at_or_below(heights, room.door_height),
        time_smoke_at_head_height=first_time_at_or_below(heights, HEAD_HEIGHT),
        aset=aset_time,
        aset_reason=aset_reason,
        rset=rset_time,
        safety_margin=safety_margin(aset_time, rset_time),
    )
