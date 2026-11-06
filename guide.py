"""
Plain-language explanations that react to the user's choices.

This module turns the model's numbers into sentences:
  * what each step shows for the scenario on screen,
  * what the user's last change did, and why (the "why" follows the equations),
  * the key moments of the fire, and what is happening at any moment (3D view).

No new physics lives here: every number comes from fire_model, and every
"because" restates what an equation in fire_model says. Numbers arrive in SI and
are formatted with a units.Units object, so the text follows the unit switch.
"""

import math
from dataclasses import dataclass, replace

from fire_model.detection import ceiling_jet_temperature_rise, ceiling_jet_velocity
from fire_model.egress import HEAD_HEIGHT, TENABILITY_TEMP, occupant_status
from fire_model.flashover import babrauskas_flashover_hrr, thomas_flashover_hrr, ventilation_limit
from fire_model.growth import GROWTH_TIMES, REFERENCE_HRR, burning_diameter, growth_coefficient, time_to_reach
from fire_model.layer_temp import MQH_UPPER_LIMIT, T_AMBIENT, mqh_layer_temperature, thermal_penetration_time
from fire_model.room import Room, floor_area, interior_surface_area, opening_factor
from fire_model.smoke_filling import door_outflow, flame_height, kelvin, plume_mass_flow

# ---------------------------------------------------------------------------
# Words shown to the user
# ---------------------------------------------------------------------------

# Growth classes: display name and a typical fuel (from the prototype).
GROWTH_LABELS = {
    "slow": ("Slow", "Dense wood furniture"),
    "medium": ("Medium", "Cotton or polyester bedding"),
    "fast": ("Fast", "Upholstered furniture, stacked boxes"),
    "ultrafast": ("Ultrafast", "Flammable liquid pool, thin plastics"),
}

# The app's tabs. The step tabs are visited in this order by the guided tour.
TAB_OVERVIEW = "Overview"
TAB_FIRE = "1 · Fire"
TAB_HEAT = "2 · Smoke temperature"
TAB_FLASHOVER = "3 · Flashover"
TAB_ESCAPE = "4 · Escape"
TAB_PROTECTION = "Sprinklers & detectors"
TAB_3D = "3D view"
TAB_MATH = "Check the math"
TAB_ABOUT = "Methods & validation"
TABS = [TAB_OVERVIEW, TAB_FIRE, TAB_HEAT, TAB_FLASHOVER, TAB_ESCAPE, TAB_PROTECTION, TAB_3D, TAB_MATH, TAB_ABOUT]
TOUR = [TAB_FIRE, TAB_HEAT, TAB_FLASHOVER, TAB_ESCAPE, TAB_PROTECTION, TAB_3D]

# Name of every model input, as shown in "what your last change did".
INPUT_LABELS = {
    "growth": "Fire growth rate", "fuel": "What's burning", "peak_hrr": "Peak heat release rate",
    "fire_diameter": "Fire diameter", "t_end": "Time simulated", "room_preset": "Room type",
    "length": "Room length", "width": "Room width", "height": "Ceiling height",
    "door_width": "Door width", "door_height": "Door height", "lining": "Wall lining",
    "thickness": "Lining thickness", "sprinkler_type": "Sprinkler", "sprinkler_rating": "Sprinkler rating",
    "sprinkler_distance": "Sprinkler distance", "use_heat_detector": "Heat detector alarm",
    "detector_rating": "Heat detector rating", "detector_spacing": "Heat detector spacing",
    "detector_distance": "Heat detector distance", "occupant_preset": "Occupant scenario",
    "detection": "Detection time", "reaction": "Reaction time", "distance": "Walk to the door",
    "speed": "Walking speed",
}

# What each input does, in words that follow the equations of the model.
WHY = {
    "growth": "The growth rate sets α in Q = αt², how fast the fire grows. A faster fire reaches every "
              "threshold sooner (smoke at head height, 200 °C, flashover), but not a bigger final size.",
    "fuel": "What's burning sets the peak heat release rate: the biggest the fire gets. It does not change "
            "the first minutes, while the fire is still small and growing.",
    "peak_hrr": "The peak heat release rate is the biggest the fire gets. A bigger peak can push the fire past "
                "the flashover thresholds and makes the smoke hotter once the fire stops growing.",
    "fire_diameter": "The fire diameter only changes the flame height (Heskestad): for the same fire size, a "
                     "wider fire has shorter flames. It is used for the 3D view and the flame-tip check.",
    "t_end": "This only changes how long the calculation runs. Everything inside that time is the same.",
    "room_preset": "A room preset changes the room size, the door and the lining together.",
    "length": "A longer room has a bigger floor, so the smoke spreads into a thinner layer and takes longer "
              "to reach head height. More wall area also soaks up more heat (cooler smoke, and a higher "
              "Thomas flashover threshold).",
    "width": "A wider room has a bigger floor, so the smoke spreads into a thinner layer and takes longer to "
             "reach head height. More wall area also soaks up more heat (cooler smoke, and a higher Thomas "
             "flashover threshold).",
    "height": "A higher ceiling leaves more space above head height for the smoke, and adds wall area that "
              "soaks up heat. Under a higher ceiling the ceiling jet is cooler, so sprinklers and detectors "
              "activate later.",
    "door_width": "The door's opening factor A_o√H_o controls how much air gets in and hot gas gets out. A "
                  "wider door raises the air supply limit and the Babrauskas and Thomas flashover thresholds, "
                  "and lets more heat escape, so the smoke is cooler.",
    "door_height": "The door's opening factor A_o√H_o controls how much air gets in and hot gas gets out; it "
                   "grows quickly with door height. A taller door also changes when the descending smoke "
                   "reaches the door top and starts to spill out.",
    "lining": "The lining sets how fast the walls soak up heat (h_k, through k·ρ·c). Heavy materials such as "
              "concrete and brick absorb much more heat than insulating ones such as gypsum board, so the "
              "smoke stays cooler.",
    "thickness": "The lining thickness sets the thermal penetration time t_p. Until then only the inside "
                 "surface heats up and the thickness doesn't matter; after it, a thicker wall absorbs less.",
    "sprinkler_type": "The sprinkler's RTI sets how fast its bulb or link heats up in the hot ceiling jet. A "
                      "quick-response sprinkler (low RTI) activates sooner, while the fire is smaller.",
    "sprinkler_rating": "The temperature rating is how hot the bulb or link must get before the sprinkler "
                        "opens. A lower rating activates sooner.",
    "sprinkler_distance": "The ceiling jet cools and slows as it spreads, so a sprinkler farther from the "
                          "fire activates later.",
    "use_heat_detector": "With a heat detector, the alarm sounds when the detector activates, instead of the "
                         "smoke alarm's detection time typed in for the occupant.",
    "detector_rating": "A heat detector with a lower temperature rating activates sooner.",
    "detector_spacing": "Heat detectors listed for a wider spacing have a lower RTI (they respond faster), so "
                        "they activate sooner at the same distance.",
    "detector_distance": "The ceiling jet cools and slows as it spreads, so a detector farther from the fire "
                         "activates later.",
    "occupant_preset": "The occupant scenario sets the detection, reaction, distance and speed together.",
    "detection": "RSET = detection + reaction + walking. Every second added here is a second later out of the "
                 "room; it does not change the fire or the smoke.",
    "reaction": "RSET = detection + reaction + walking. Reaction time is often the biggest part: people need "
                "to notice the alarm, understand it and decide to leave.",
    "distance": "RSET = detection + reaction + walking. A longer walk adds distance ÷ speed seconds.",
    "speed": "RSET = detection + reaction + walking. A slower walk adds time, especially over long distances.",
}

# occupant_status() phrases as sentences for the moment description.
OCCUPANT_SENTENCES = {
    "Alarm not yet sounding": "The alarm has not sounded yet, so the occupant does not know about the fire.",
    "Alarm sounding, occupant reacting": "The alarm is sounding and the occupant is reacting (noticing, deciding).",
    "Occupant walking to door": "The occupant is walking to the door.",
    "Occupant is out": "The occupant is out of the room.",
}

# Which tab shows the effect of each input best.
STEP_FOR = {
    "growth": TAB_FIRE, "fuel": TAB_FIRE, "peak_hrr": TAB_FIRE, "fire_diameter": TAB_3D, "t_end": TAB_FIRE,
    "room_preset": TAB_HEAT, "length": TAB_ESCAPE, "width": TAB_ESCAPE, "height": TAB_ESCAPE,
    "door_width": TAB_FLASHOVER, "door_height": TAB_FLASHOVER, "lining": TAB_HEAT, "thickness": TAB_HEAT,
    "sprinkler_type": TAB_PROTECTION, "sprinkler_rating": TAB_PROTECTION, "sprinkler_distance": TAB_PROTECTION,
    "use_heat_detector": TAB_PROTECTION, "detector_rating": TAB_PROTECTION, "detector_spacing": TAB_PROTECTION,
    "detector_distance": TAB_PROTECTION, "occupant_preset": TAB_ESCAPE, "detection": TAB_ESCAPE,
    "reaction": TAB_ESCAPE, "distance": TAB_ESCAPE, "speed": TAB_ESCAPE,
}

# When a preset changes, the inputs it fills in are explained by the preset itself.
PRESET_GROUPS = {
    "room_preset": ("length", "width", "height", "door_width", "door_height", "lining", "thickness"),
    "occupant_preset": ("detection", "reaction", "distance", "speed"),
    "fuel": ("peak_hrr",),
    "lining": ("thickness",),
}


def seconds(t):
    """A time for text: '29 s' (rounded like a calculator), or None if it never happens."""
    return None if t is None else f"{math.floor(t + 0.5):,} s"


def _a(word):
    """'a' or 'an' before a word."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def _room(inputs):
    return Room(inputs["length"], inputs["width"], inputs["height"], inputs["door_width"], inputs["door_height"])


# ---------------------------------------------------------------------------
# "What your last change did"
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Summary:
    """The headline results, compared before and after a change."""

    flashover: tuple | None  # (earliest, latest) s
    aset: int | None
    rset: float | None
    margin: float | None
    hottest: float  # °C
    head_time: int | None  # smoke at 1.8 m, s
    sprinkler_time: float | None
    alarm_time: float | None
    biggest_fire: float  # kW


def summarize(result):
    return Summary(
        flashover=result.flashover_range, aset=result.aset, rset=result.rset, margin=result.safety_margin,
        hottest=max(result.layer_temp), head_time=result.time_smoke_at_head_height,
        sprinkler_time=result.sprinkler_time, alarm_time=result.alarm_time, biggest_fire=max(result.hrr),
    )


@dataclass(frozen=True)
class Change:
    """What the last change did, ready to display."""

    headline: str  # e.g. "Door width: 0.9 m → 1.8 m"
    inputs: list  # lines "Name: old → new" for every changed input
    effects: list  # (result name, before, after, verdict) with verdict "better", "worse" or ""
    reasons: list  # paragraphs explaining why
    step: str  # the tab that shows the effect best
    toast: str  # one short line


def _range_text(r):
    return "none" if r is None else (f"{r[0]} s" if r[0] == r[1] else f"{r[0]}–{r[1]} s")


def _time_effect(name, before, after, later_is_better, missing):
    """(name, before text, after text, verdict) for a time that may be None (never)."""
    if before == after:
        return None
    b = seconds(before) or missing
    a = seconds(after) or missing
    if b == a:
        return None
    if before is None or after is None:
        verdict = ("better" if after is None else "worse") if later_is_better else ("worse" if after is None else "better")
    else:
        verdict = "better" if (after > before) == later_is_better else "worse"
    return (name, b, a, verdict)


def _effects(before, after, units):
    effects = []
    if before.flashover != after.flashover:
        b, a = before.flashover, after.flashover
        if a is None:
            verdict = "better"
        elif b is None:
            verdict = "worse"
        else:
            verdict = "better" if a[0] > b[0] else "worse" if a[0] < b[0] else ""
        if _range_text(b) != _range_text(a):
            effects.append(("Flashover", _range_text(b), _range_text(a), verdict))
    for item in (
        _time_effect("Room untenable (ASET)", before.aset, after.aset, True, "never"),
        _time_effect("Everyone out (RSET)", before.rset, after.rset, False, "no alarm"),
        _time_effect("Smoke at head height", before.head_time, after.head_time, True, "never")
        if before.head_time != before.aset or after.head_time != after.aset else None,
        _time_effect("Sprinkler activates", before.sprinkler_time, after.sprinkler_time, False, "—")
        if before.sprinkler_time is not None or after.sprinkler_time is not None else None,
    ):
        if item:
            effects.append(item)
    if (before.margin is not None or after.margin is not None) and before.margin != after.margin:
        def margin_text(m):
            return "—" if m is None else f"{'+' if m >= 0 else '−'}{abs(math.floor(m + 0.5))} s"
        b, a = margin_text(before.margin), margin_text(after.margin)
        if b != a:
            verdict = "" if before.margin is None or after.margin is None else ("better" if after.margin > before.margin else "worse")
            effects.append(("Safety margin", b, a, verdict))
    if abs(before.hottest - after.hottest) >= 0.5:
        effects.append(("Hottest smoke", units.fmt("temperature", before.hottest), units.fmt("temperature", after.hottest),
                        "better" if after.hottest < before.hottest else "worse"))
    if abs(before.biggest_fire - after.biggest_fire) >= 0.5:
        effects.append(("Biggest fire", units.fmt("hrr", before.biggest_fire), units.fmt("hrr", after.biggest_fire), ""))
    return effects


def _detail(key, old, new, units):
    """A sentence with the numbers behind an input change (from the model's equations)."""
    if key in ("door_width", "door_height", "length", "width", "height", "room_preset"):
        r0, r1 = _room(old), _room(new)
        parts = []
        if opening_factor(r0) != opening_factor(r1):
            parts.append(f"The opening factor went from {units.fmt('opening_factor', opening_factor(r0), 2)} to "
                         f"{units.fmt('opening_factor', opening_factor(r1), 2)}, so the air supply limit went from "
                         f"{units.fmt('hrr', ventilation_limit(r0))} to {units.fmt('hrr', ventilation_limit(r1))} and the "
                         f"Babrauskas threshold from {units.fmt('hrr', babrauskas_flashover_hrr(r0))} to "
                         f"{units.fmt('hrr', babrauskas_flashover_hrr(r1))}.")
        if floor_area(r0) != floor_area(r1):
            parts.append(f"The floor area went from {units.fmt('area', floor_area(r0), 1)} to {units.fmt('area', floor_area(r1), 1)}.")
        if interior_surface_area(r0) != interior_surface_area(r1):
            parts.append(f"The inside surface area A_T went from {units.fmt('area', interior_surface_area(r0), 1)} to "
                         f"{units.fmt('area', interior_surface_area(r1), 1)} (Thomas threshold "
                         f"{units.fmt('hrr', thomas_flashover_hrr(r0))} → {units.fmt('hrr', thomas_flashover_hrr(r1))}).")
        return " ".join(parts)
    if key == "growth":
        a0, a1 = growth_coefficient(GROWTH_TIMES[old[key]]), growth_coefficient(GROWTH_TIMES[new[key]])
        return (f"α went from {units.show('alpha', a0):.4f} to {units.show('alpha', a1):.4f} {units.unit('alpha')}: the fire now "
                f"reaches {units.fmt('hrr', REFERENCE_HRR)} at {GROWTH_TIMES[new[key]]:.0f} s instead of {GROWTH_TIMES[old[key]]:.0f} s.")
    if key in ("detection", "reaction", "distance", "speed", "occupant_preset"):
        def rset_of(i):
            return i["detection"] + i["reaction"] + i["distance"] / i["speed"]
        return f"Without a heat detector alarm, RSET is {seconds(rset_of(old))} → {seconds(rset_of(new))}." if not new.get("use_heat_detector") else ""
    return ""


def describe_change(old, new, before, after, units, format_input):
    """Explain the difference between two sets of inputs and their results.

    old, new        dicts of input values (SI) before and after the change
    before, after   Summary of the results before and after
    format_input    function (key, value) -> text for one input value
    Returns a Change, or None if no model input changed.
    """
    changed = [k for k in new if old.get(k) != new.get(k)]
    if not changed:
        return None
    # Inputs filled in by a preset are explained by the preset.
    hidden = {k for preset, group in PRESET_GROUPS.items() if preset in changed for k in group}
    main = [k for k in changed if k not in hidden] or changed
    lines = [f"{INPUT_LABELS.get(k, k)}: {format_input(k, old.get(k))} → {format_input(k, new.get(k))}" for k in changed]
    headline = lines[changed.index(main[0])] + (f" (and {len(changed) - 1} more)" if len(changed) > 1 else "")

    reasons = []
    for key in main[:3]:
        text = WHY.get(key, "")
        detail = _detail(key, old, new, units)
        reasons.append((f"**{INPUT_LABELS.get(key, key)}.** {text} {detail}").strip())
    effects = _effects(before, after, units)
    if not effects:
        reasons.append("None of the headline results changed: this input matters for other parts of the "
                       "calculation, or the change was too small to move them.")
    toast = headline + (f" · {effects[0][0]}: {effects[0][1]} → {effects[0][2]}" if effects else "")
    return Change(headline=headline, inputs=lines, effects=effects, reasons=reasons,
                  step=STEP_FOR.get(main[0], TAB_OVERVIEW), toast=toast)


# ---------------------------------------------------------------------------
# What each step shows, for this scenario
# ---------------------------------------------------------------------------

def explain_fire(growth_key, peak_hrr, room, result, units):
    alpha = growth_coefficient(GROWTH_TIMES[growth_key])
    name, fuel = GROWTH_LABELS[growth_key]
    cap = result.peak_hrr_used
    fmt = units.fmt
    t2 = min(60, math.floor(time_to_reach(min(cap, ventilation_limit(room)), alpha)))
    t1 = t2 // 2
    out = [
        f"**Your fire grows {name.lower()}**, typical of {fuel.lower().replace(', ', ' or ')}: "
        f"α = {units.show('alpha', alpha):.4f} {units.unit('alpha')}. "
        f"While it grows, Q = αt², so twice the time means four times the fire: {fmt('hrr', alpha * t1**2)} at {t1} s, "
        f"{fmt('hrr', alpha * t2**2)} at {t2} s."
    ]
    if min(cap, ventilation_limit(room)) >= REFERENCE_HRR:
        out.append(f"It reaches {fmt('hrr', REFERENCE_HRR)} (the size that defines the growth classes) at "
                   f"{GROWTH_TIMES[growth_key]:.0f} s.")
    if result.sprinkler_time is not None:
        out.append(f"It stops growing at **{fmt('hrr', result.sprinkler_hrr)}** when the sprinkler activates at "
                   f"{seconds(result.sprinkler_time)} (the fuel alone could reach {fmt('hrr', peak_hrr)}).")
    elif result.vent_limited:
        out.append(f"The fuel could reach {fmt('hrr', peak_hrr)}, but the door only lets in enough air for "
                   f"**{fmt('hrr', result.ventilation_limit)}**, so from {seconds(result.time_vent_limited)} the fire is "
                   "**ventilation-controlled**: held back by its air supply.")
    elif result.time_to_peak <= result.t_end:
        out.append(f"It reaches its peak of **{fmt('hrr', cap)}** (set by what is burning) at {seconds(result.time_to_peak)}, "
                   "then burns steadily: this model has no decay phase.")
    else:
        out.append(f"It is still growing when the calculation stops at {result.t_end} s ({fmt('hrr', result.hrr[-1])}).")
    out.append(f"Over the {result.t_end} s it releases {fmt('energy', result.energy_released)} of heat.")
    others = [(GROWTH_LABELS[k][0].lower(), time_to_reach(min(cap, ventilation_limit(room)), growth_coefficient(t)))
              for k, t in GROWTH_TIMES.items() if k != growth_key]
    out.append("To reach the same size, " + ", ".join(f"{_a(n)} {n} fire would take {seconds(t)}" for n, t in others) + ".")
    return out


def _lining_words(lining):
    inertia = lining.k * lining.rho * lining.c
    if inertia < 1.0:
        return inertia, "insulating: it soaks up heat slowly, so more of the heat stays in the smoke"
    return inertia, "heavy: it soaks up a lot of heat, so the smoke stays cooler"


def explain_heat(room, lining, result, units, alternative):
    """alternative: (name, Lining) to compare with, e.g. concrete instead of gypsum."""
    temps = result.layer_temp
    hottest = max(temps)
    t_hot = temps.index(hottest)
    fmt = units.fmt
    out = [f"**The hot smoke layer reaches {fmt('temperature', hottest)}**"
           + (f" (at {t_hot} s)." if t_hot < result.t_end else " by the end.")]
    if result.time_layer_200c is not None:
        out[-1] += (f" It passes {fmt('temperature', TENABILITY_TEMP)} at {result.time_layer_200c} s: from then on its "
                    "radiant heat would burn anyone underneath.")
    else:
        out[-1] += f" It stays below {fmt('temperature', TENABILITY_TEMP)}, so its radiant heat is not yet dangerous."
    inertia, words = _lining_words(lining)
    out.append(
        f"**Why that temperature:** MQH balances the fire's heat against two losses. Hot gas leaves through the "
        f"door (opening factor {fmt('opening_factor', result.opening_factor, 2)}), and heat soaks into the "
        f"{fmt('area', result.interior_area, 1)} of walls, ceiling and floor. Your {lining.name.lower()} has "
        f"k·ρ·c = {inertia:.2f}, so it is {words}."
    )
    alt_name, alt_lining = alternative
    alt_hottest = max(mqh_layer_temperature(t, q, room, alt_lining) for t, q in enumerate(result.hrr))
    out.append(f"With {alt_name.lower()} walls instead, the hottest smoke would be {fmt('temperature', alt_hottest)}.")
    t_p = thermal_penetration_time(lining)
    if t_p < result.t_end:
        thickness = fmt('thickness', lining.thickness * 1000, 2 if units.us else 0)
        out.append(f"At t_p = {seconds(t_p)} heat reaches the back of the {thickness} "
                   "lining. After that the walls absorb about half as much (h_k drops from 2k/δ to k/δ), so the "
                   "temperature steps up by about a quarter (2^(1/3) = 1.26).")
    else:
        out.append(f"Heat needs t_p = {seconds(t_p)} to reach the back of the lining, longer than the "
                   "calculation, so the wall acts as if it were infinitely thick the whole time.")
    if result.time_layer_600c is not None:
        out.append(f"From {result.time_layer_600c} s the layer is above {fmt('temperature', MQH_UPPER_LIMIT)}, outside the "
                   "range MQH was fitted to: treat those values as rough.")
    return out


def explain_flashover(room, result, units):
    fmt = units.fmt
    bab, tho, mqh = result.flashover
    reached = [m for m in result.flashover if m.time is not None]
    sizes = [m.threshold_hrr for m in result.flashover if m.threshold_hrr is not None]
    out = [
        f"**Flashover needs a fire of about {fmt('hrr', min(sizes))}–{fmt('hrr', max(sizes))}**, depending on the method. "
        f"Babrauskas ({fmt('hrr', bab.threshold_hrr)}) only uses the door's opening factor. Thomas "
        f"({fmt('hrr', tho.threshold_hrr)}) also counts the heat lost to the {fmt('area', result.interior_area, 1)} of "
        "walls, ceiling and floor. MQH asks when the smoke itself reaches 520 °C"
        + (f" ({fmt('hrr', mqh.threshold_hrr)} here)." if mqh.threshold_hrr is not None else "; in this scenario it never does.")
    ]
    biggest = max(result.hrr)
    if reached:
        first = min(reached, key=lambda m: m.time)
        how_many = "all 3 thresholds" if len(reached) == 3 else f"{len(reached)} of the 3 thresholds"
        out.append(f"**Your fire reaches {how_many}**, the first ({first.name.split(' (')[0]}) at {first.time} s. "
                   "After flashover every surface in the room burns: nobody inside survives, and the fire can spread "
                   "beyond the room.")
        out.append(f"To avoid flashover, the fire would have to stay below about {fmt('hrr', min(sizes))}: a smaller "
                   "fuel, or a sprinkler that activates before then.")
    else:
        out.append(f"**No flashover:** your fire tops out at {fmt('hrr', biggest)}, "
                   f"{100 * biggest / min(sizes):.0f}% of the lowest threshold.")
    if len(sizes) > 1:
        out.append(f"The methods disagree by {100 * (max(sizes) - min(sizes)) / min(sizes):.0f}%. That is normal: they "
                   "were fitted to different experiments, which is why engineers look at the whole range.")
    out.append(f"The door also caps the fire: it can only feed about {fmt('hrr', result.ventilation_limit)} "
               "(Q_vent = 1500 · A_o√H_o)."
               + (" Here that limit is what stops the fire growing." if result.vent_limited and result.sprinkler_time is None else ""))
    return out


def explain_escape(room, occupant, result, units, heat_detector_used):
    fmt = units.fmt
    out = []
    t_look = result.time_smoke_at_door_top or min(30, result.t_end)
    q, z = result.hrr[t_look], result.layer_height[t_look]
    out.append(f"**Smoke fills the room from the ceiling down.** At {t_look} s the plume is carrying about "
               f"{units.show('mass_flow', plume_mass_flow(q, z)):.2f} {units.unit('mass_flow')} of hot gas up into the layer: "
               "much more than the burning fuel gives off, because the plume pulls in room air as it rises.")
    if result.time_smoke_at_door_top is not None:
        out.append(f"The smoke reaches the top of the door at {result.time_smoke_at_door_top} s and starts spilling out.")
    if result.time_smoke_at_head_height is not None:
        out.append(f"It reaches head height ({fmt('length', HEAD_HEIGHT, 1)}) at **{result.time_smoke_at_head_height} s**.")
    else:
        out.append(f"It never reaches head height ({fmt('length', HEAD_HEIGHT, 1)}): the bottom of the layer ends at "
                   f"{fmt('length', min(result.layer_height), 2)}.")
    if result.aset is not None:
        out.append(f"So the room becomes **untenable at {result.aset} s**: {result.aset_reason.lower()}.")
    else:
        out.append(f"So the room **stays tenable** for the whole {result.t_end} s.")
    if result.rset is None:
        out.append("**No alarm sounds**: the heat detector never activates, so the occupant is never warned.")
        return out
    walk = occupant.walk_distance / occupant.walk_speed
    source = "the heat detector" if heat_detector_used else "the detection time you set"
    out.append(f"**Escape takes {seconds(result.rset)}:** the alarm sounds at {seconds(result.alarm_time)} ({source}), "
               f"the occupant needs {occupant.reaction_time:g} s to react, then walks {fmt('length', occupant.walk_distance, 1)} "
               f"at {fmt('speed', occupant.walk_speed, 1)} ({seconds(walk)}).")
    if result.safety_margin is not None and result.safety_margin < 0:
        waiting = result.alarm_time + occupant.reaction_time
        if waiting > walk:
            out.append(f"Most of that ({seconds(waiting)}) is waiting for the alarm and reacting, so earlier detection or "
                       "a faster response would help most. A larger or taller room would also buy time, by giving the "
                       "smoke more space to fill.")
        else:
            out.append("Most of that is walking, so a shorter route to the door would help most. A larger or taller "
                       "room would also buy time, by giving the smoke more space to fill.")
    elif result.safety_margin is not None:
        out.append(f"That leaves **{seconds(result.safety_margin)} to spare**. Real designs add a safety factor on top.")
    return out


def explain_protection(room, result, unprotected, sprinkler, heat_detector, occupant, units):
    fmt = units.fmt
    out = []
    if sprinkler is None and heat_detector is None:
        return ["**No sprinkler or heat detector is installed.** Add one in the sidebar, or with the buttons below, "
                "to see when it activates and what it changes."]
    H = room.height
    if sprinkler is not None:
        if result.sprinkler_time is not None:
            t = int(result.sprinkler_time)
            q = result.hrr[t]
            jet = T_AMBIENT + ceiling_jet_temperature_rise(q, H, sprinkler.radial_distance)
            u = ceiling_jet_velocity(q, H, sprinkler.radial_distance)
            out.append(f"**The sprinkler activates at {seconds(result.sprinkler_time)}**, when the fire is "
                       f"{fmt('hrr', result.sprinkler_hrr)}. At that moment the ceiling jet "
                       f"{fmt('length', sprinkler.radial_distance, 1)} from the fire is {fmt('temperature', jet)} and moving "
                       f"{fmt('speed', u, 1)}. The {sprinkler.name.lower()} has an RTI of {units.show('rti', sprinkler.rti):.0f} "
                       f"{units.unit('rti')}: it lags behind the hot gas and only now reaches its "
                       f"{fmt('temperature', sprinkler.activation_temp)} rating.")
            before = _range_text(unprotected.flashover_range) if unprotected else "—"
            after = _range_text(result.flashover_range)
            out.append(f"**What it changes:** flashover {before} → {after}; hottest smoke "
                       f"{fmt('temperature', max(unprotected.layer_temp))} → {fmt('temperature', max(result.layer_temp))}. "
                       "From activation on, the fire stays at that size (a cautious assumption: real sprinkler water "
                       "also cools the smoke and often shrinks the fire).")
            if result.aset is not None and result.sprinkler_time > result.aset:
                out.append("**But the room is already untenable when it activates.** Sprinklers control the fire and "
                           "protect the building, but in a small room the smoke can fill it first. Early smoke "
                           "detection is what protects the people inside.")
        else:
            peak_jet = max(T_AMBIENT + ceiling_jet_temperature_rise(q, H, sprinkler.radial_distance) for q in result.hrr)
            out.append(f"**The sprinkler never activates** within {result.t_end} s: the ceiling jet at its position only "
                       f"reaches {fmt('temperature', peak_jet)}, so its element never gets to its "
                       f"{fmt('temperature', sprinkler.activation_temp)} rating.")
    if heat_detector is not None:
        if result.heat_detector_time is not None:
            out.append(f"**The heat detector sounds the alarm at {seconds(result.heat_detector_time)}**, compared with the "
                       f"{occupant.detection_time:g} s detection time of the occupant scenario. Heat detectors wait for the "
                       "ceiling jet to heat them up, so they are usually much slower than smoke alarms.")
        else:
            out.append(f"**The heat detector never activates** within {result.t_end} s, so no alarm sounds.")
    return out


# ---------------------------------------------------------------------------
# Key moments and what is happening at any moment (3D view)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Moment:
    key: str
    time: int  # s
    label: str  # short, for a button
    text: str  # one sentence


def key_moments(result, occupant, heat_detector_used, units):
    moments = {}

    def add(key, t, label, text):
        if t is not None and 0 <= t <= result.t_end:
            moments[key] = Moment(key, int(math.floor(t + 0.5)), label, text)

    add("start", 0, "Ignition", "The fire starts. It is tiny and the room is still clear.")
    if result.alarm_time is not None:
        add("alarm", result.alarm_time, "Alarm",
            "The alarm sounds" + (" (the heat detector activates)." if heat_detector_used else "."))
        add("move", result.alarm_time + occupant.reaction_time, "Starts moving",
            "The occupant has reacted and starts walking to the door.")
    add("door", result.time_smoke_at_door_top, "Smoke at door top",
        "The smoke layer reaches the top of the door and starts spilling out.")
    if result.aset is not None:
        add("untenable", result.aset, "Untenable", f"The room becomes untenable: {result.aset_reason.lower()}.")
    if result.time_smoke_at_head_height not in (None, result.aset):
        add("head", result.time_smoke_at_head_height, "Smoke at head height",
            f"Smoke reaches head height ({units.fmt('length', HEAD_HEIGHT, 1)}).")
    if result.time_layer_200c not in (None, result.aset):
        hot = units.fmt("temperature", TENABILITY_TEMP)
        add("hot", result.time_layer_200c, f"Smoke at {hot}", f"The smoke layer reaches {hot}.")
    if result.rset is not None:
        add("out", result.rset, "Everyone out", "The occupant is out of the room.")
    add("sprinkler", result.sprinkler_time, "Sprinkler",
        "The sprinkler activates; from now on the fire stays the same size.")
    if result.sprinkler_time is None and result.time_to_peak <= result.t_end:
        add("peak", result.time_to_peak, "Full size",
            "The fire reaches its full size" + (" (the air supply limit)." if result.vent_limited else "."))
    if result.flashover_range is not None:
        add("flashover", result.flashover_range[0], "Flashover", "Flashover is predicted by the first method.")
    add("end", result.t_end, "End", "The end of the calculation.")
    return sorted(moments.values(), key=lambda m: (m.time, m.key != "start"))


def describe_moment(t, result, room, occupant, peak_hrr, fire_diameter, units, sprinkler=None, heat_detector=None):
    """What is happening at whole second t, as a few short paragraphs."""
    fmt = units.fmt
    t = max(0, min(int(t), result.t_end))
    q, temp, z = result.hrr[t], result.layer_temp[t], result.layer_height[t]
    out = []
    if q <= 0:
        out.append(f"**At {t} s** the fire has just started.")
    else:
        flames = flame_height(q, burning_diameter(q, peak_hrr, fire_diameter))
        reach = (" They reach the ceiling, so in reality they would spread along it." if flames >= room.height
                 else f" They reach into the smoke layer, where Heskestad's plume equation is outside its range."
                 if flames >= z and z < room.height - 0.01 else "")
        out.append(f"**At {t} s** the fire is {fmt('hrr', q)}, with flames about {fmt('length', min(flames, room.height), 1)} "
                   f"tall.{reach}")
    depth = room.height - z
    if depth < 0.01:
        out.append("There is no smoke layer yet.")
    else:
        if temp < 100:
            look = "light gray: warm, thin smoke"
        elif temp < 300:
            look = "darker gray: hot, sooty smoke"
        elif temp < 525:
            look = "dark charcoal: very hot smoke"
        else:
            look = "glowing red: above about 525 °C hot soot starts to glow (the Draper point), as it does near flashover"
        if z < 0.05:
            out.append(f"The smoke fills the whole room, down to the floor, at {fmt('temperature', temp)}. It is drawn "
                       f"{look}. (The model's layer height jitters near the floor here; read it as smoke-logged.)")
        else:
            out.append(f"The smoke layer fills the top {fmt('length', depth, 2)} of the room, down to "
                       f"{fmt('length', z, 2)} above the floor, at {fmt('temperature', temp)}. It is drawn {look}.")
        if z <= HEAD_HEIGHT:
            out.append("The bottom of the layer is at or below head height: anyone standing would be breathing smoke.")
        else:
            out.append("Below the layer the air is still clear, cool and breathable.")
        m_in = plume_mass_flow(q, z)
        m_out = door_outflow(room, z, kelvin(temp))
        flow = f"The plume is carrying {units.show('mass_flow', m_in):.2f} {units.unit('mass_flow')} into the layer"
        if m_out > 0:
            flow += (f" while {units.show('mass_flow', m_out):.2f} {units.unit('mass_flow')} spills out of the top of the door "
                     "(and fresh air flows in lower down, which this model leaves out).")
        else:
            flow += "; none is leaving yet, because the layer is still above the top of the door."
        out.append(flow)
    if result.alarm_time is None:
        out.append("No alarm has sounded, so the occupant does not know about the fire.")
    else:
        status = occupant_status(t, replace(occupant, detection_time=result.alarm_time))
        out.append(OCCUPANT_SENTENCES.get(status, status + "."))
    for name, device, activation, temps in (
        ("sprinkler", sprinkler, result.sprinkler_time, result.sprinkler_temps),
        ("heat detector", heat_detector, result.heat_detector_time, result.heat_detector_temps),
    ):
        if device is None or temps is None:
            continue
        if activation is not None and t >= activation:
            out.append(f"The {name} activated at {seconds(activation)}.")
        else:
            out.append(f"The {name}'s element is at {fmt('temperature', temps[t])}, heating toward its "
                       f"{fmt('temperature', device.activation_temp)} rating.")
    return out
