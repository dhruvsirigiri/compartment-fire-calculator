"""Validation against the U.S. NRC's NUREG-1805 Fire Dynamics Tools spreadsheets.

Every case in fire_model/validation.py compares this model with the NRC's own
worked example (inputs and answers read from the spreadsheets in
docs/nureg-1805/). Each must agree within its stated tolerance.
"""

from dataclasses import replace

import pytest

from fire_model.layer_temp import T_AMBIENT, mqh_layer_temperature
from fire_model.validation import (
    CH2_HRR,
    CH2_LINING,
    CH2_RESULTS,
    CH2_ROOM,
    all_cases,
    flashover_cases,
)

CASES = all_cases()


@pytest.mark.parametrize("case", CASES, ids=[f"{c.topic} | {c.quantity}" for c in CASES])
def test_matches_nureg_1805(case):
    assert case.passes, (
        f"{case.quantity}: model {case.model:.6g} vs NRC {case.nrc:.6g} {case.unit} "
        f"({case.difference_percent:+.3f}%, limit {case.tolerance_percent}%) - {case.source}"
    )


def test_mqh_difference_is_only_the_rounded_thermal_inertia():
    # The NRC rounds concrete's k*rho*c to 2.9 (the model's 0.0016*2400*0.75 = 2.88).
    # Give the model exactly 2.9, by adjusting c, and the full MQH chain matches
    # the NRC to rounding. (For these times t < t_p, so only k*rho*c matters.)
    nrc_inertia_lining = replace(CH2_LINING, c=2.9 / (CH2_LINING.k * CH2_LINING.rho))
    for t, _h_k, nrc_rise, _row in CH2_RESULTS:
        model_rise = mqh_layer_temperature(t, CH2_HRR, CH2_ROOM, nrc_inertia_lining) - T_AMBIENT
        assert model_rise == pytest.approx(nrc_rise, rel=1e-5)


def test_mqh_500k_criterion_is_the_documented_2_percent_above_610():
    # Solving MQH exactly for a 500 K rise gives (500/6.85)^1.5 = 623.6 instead
    # of the published 610.
    criterion = next(c for c in flashover_cases() if "500 K" in c.quantity)
    expected_percent = 100 * ((500 / 6.85) ** 1.5 / 610 - 1)
    assert criterion.difference_percent == pytest.approx(expected_percent, abs=0.01)
