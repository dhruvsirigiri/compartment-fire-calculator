"""
Step 3: Flashover and the air supply limit.

Flashover is the sudden transition from a fire burning one object to a room in
which every exposed surface is burning: radiation from the hot smoke layer heats
everything below it until it all ignites. Three classic hand methods estimate the
smallest fire (kW) that can cause it:

    Babrauskas (1980):  Q_FO = 750 * A_o*sqrt(H_o)
    Thomas (1981):      Q_FO = 7.8 * A_T + 378 * A_o*sqrt(H_o)
    MQH (1981):         the time at which the Step 2 layer temperature reaches
                        T_a + 500 °C. This is the MQH equation solved for the
                        fire that makes the layer 500 °C hotter than ambient. The
                        published closed form is
                        Q_FO = 610 * (h_k * A_T * A_o*sqrt(H_o))^(1/2).
                        (Solving 6.85 * [...]^(1/3) = 500 exactly gives ~624
                        instead of 610, about 2% higher; 610 corresponds to a rise
                        of ~493 °C. The model uses the temperature criterion.)

The air supply limit: almost all the oxygen a room fire burns comes in through
the door. The air inflow is roughly 0.5 * A_o*sqrt(H_o) kg/s, and burning 1 kg of
air releases about 3000 kJ, so the largest fire the opening can support is about

    Q_vent = 1500 * A_o*sqrt(H_o)   (kW)

The fire used everywhere in the model is therefore

    Q_eff(t) = min(alpha t^2, Q_max, Q_vent)
"""

from fire_model.growth import t_squared_hrr
from fire_model.layer_temp import T_AMBIENT
from fire_model.room import interior_surface_area, opening_factor
from fire_model.timeline import first_time_at_or_above

# MQH flashover criterion: the hot layer is 500 °C above ambient.
MQH_FLASHOVER_TEMP = T_AMBIENT + 500.0  # °C


def ventilation_limit(room):
    """Q_vent (kW): the largest fire the door's air supply can sustain."""
    return 1500.0 * opening_factor(room)


def effective_hrr(t, alpha, peak_hrr, room):
    """Q_eff (kW) at time t (s): the t-squared fire, capped by both the fuel's
    peak HRR and the air supply limit. A fire held back by its air supply is
    called ventilation-controlled."""
    return min(t_squared_hrr(t, alpha, peak_hrr), ventilation_limit(room))


def hrr_history(alpha, peak_hrr, room, t_end):
    """Q_eff (kW) at every whole second from 0 to t_end (s).
    result[t] is the fire size at t seconds."""
    return [effective_hrr(t, alpha, peak_hrr, room) for t in range(int(t_end) + 1)]


def babrauskas_flashover_hrr(room):
    """Minimum fire for flashover (kW), Babrauskas (1980)."""
    return 750.0 * opening_factor(room)


def thomas_flashover_hrr(room):
    """Minimum fire for flashover (kW), Thomas (1981). The first term accounts
    for heat lost to the room's surfaces, the second for heat lost out the door."""
    return 7.8 * interior_surface_area(room) + 378.0 * opening_factor(room)


def time_hrr_reaches(hrr_by_second, threshold):
    """First whole second (s) at which the fire reaches `threshold` kW, or None."""
    return first_time_at_or_above(hrr_by_second, threshold)


def mqh_flashover_time(temperature_by_second):
    """First whole second (s) at which the MQH layer temperature reaches
    T_a + 500 °C, or None if it never does."""
    return first_time_at_or_above(temperature_by_second, MQH_FLASHOVER_TEMP)
