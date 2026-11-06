"""
fire_model: the physics of the Compartment Fire Calculator.

One module per calculation step, all pure functions in SI units
(m, s, kW, kg, °C unless a name says K):

    growth.py         Step 1  t-squared fire growth
    layer_temp.py     Step 2  hot gas layer temperature (MQH)
    flashover.py      Step 3  flashover thresholds and the air supply limit
    smoke_filling.py  Step 4  smoke layer height over time (two-zone filling)
    egress.py         Step 4  required safe egress time (RSET) and ASET

"Pure function" means: the output depends only on the inputs, and the
function changes nothing else. That makes every step easy to test on its own.

This is a learning tool, not a design tool.
"""
