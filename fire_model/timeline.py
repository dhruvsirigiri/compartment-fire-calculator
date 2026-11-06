"""
Helpers for results recorded once per second.

Many results are "the first moment something happens": the fire reaches a
flashover threshold, the smoke drops to head height, the layer reaches 200 °C.
The model records its results at whole seconds in a list, where

    values[t]  is the value at t seconds   (values[0] is ignition, t = 0)

and reports each event as the first whole second at which the condition is met.
This matches how the index.html prototype reports times.
"""


def first_time_at_or_above(values, threshold):
    """First whole second t (s) at which values[t] >= threshold, or None if it
    never happens. The search starts at t = 1 s, because t = 0 is the starting
    state at ignition."""
    for t in range(1, len(values)):
        if values[t] >= threshold:
            return t
    return None


def first_time_at_or_below(values, threshold):
    """First whole second t (s) at which values[t] <= threshold, or None if it
    never happens. Used for the smoke layer height, which falls over time."""
    for t in range(1, len(values)):
        if values[t] <= threshold:
            return t
    return None
