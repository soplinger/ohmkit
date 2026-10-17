# ohmkit

**Offline resistor and basic circuit calculator, in one Python file.**

ohmkit does the arithmetic you would otherwise do on the back of a parts bin:
colour bands both ways, `4k7`-style value parsing, E12/E24/E96 snapping,
voltage dividers, LED resistors, series and parallel totals, RC and RL time
constants, wattage ratings and a line-numbered parts-file linter. It uses exact
fractions for resistor maths, so `4.7kΩ` stays exactly `4700` until it is
printed. No network, no accounts, no dependencies beyond the Python standard
library (pytest for the tests).

## Features

- **Colour-band encoder**: turn a resistance into 4- or 5-band colours, with a chosen tolerance band.
- **Colour-band decoder**: read 4- or 5-band colours back to an exact value and tolerance.
- **Flexible value parsing**: `4k7`, `4R7`, `1M5`, `2.2 kΩ`, `470`, `100 ohm`, `10uF`, `1ms`.
- **Standard-value snapping**: nearest E12, E24 or E96 value with the percentage error.
- **Round-up snapping**: the next standard value at or above a target, so LED currents never overshoot.
- **Voltage divider forward mode**: output voltage and ratio from two resistors.
- **Voltage divider solve mode**: the bottom resistor for a target output, plus the nearest standard part and what it actually gives.
- **LED series resistor**: sizes the resistor for any string of LEDs, reports current, dissipation and a wattage rating.
- **Power and rating check**: current, power and the smallest standard wattage with a 2× margin.
- **Series and parallel totals**: exact sums and reciprocal sums for any number of resistors.
- **RC time constant**: τ, the 1–5 τ charge table, and the percentage charged at any elapsed time.
- **RL time constant**: τ = L/R with the same table and elapsed-time readout.
- **Parts-file linter**: checks a plain-text `REF VALUE` list, with line-numbered errors for bad values, missing values and duplicate refs, and warnings for values off the chosen E-series.
- **CI-friendly exit codes**: `0` clean, `1` when the parts file has errors, `2` for a bad command-line value.

## Quick start

ohmkit needs Python 3 and nothing else.

```bash
# Colour bands for a 4.7 kΩ resistor, then back again
python3 ohmkit.py encode 4k7
python3 ohmkit.py decode yellow violet red gold

# Snap an off-grid value to E24, and round up for an LED
python3 ohmkit.py snap 1k25
python3 ohmkit.py snap 4701 --up

# 12 V divider with 10 kΩ on top and 4k7 on the bottom
python3 ohmkit.py divider --vin 12V --r1 10k --r2 4k7

# Bottom resistor for a 5 V output from 12 V, with 10 kΩ on top
python3 ohmkit.py divider --vin 12V --vout 5V --r1 10k

# Two red LEDs from a 9 V supply at 20 mA
python3 ohmkit.py led --supply 9V --count 2 --vf 2.1V --current 20mA

# RC: 10 kΩ and 100 µF, how far it has charged after 1 ms
python3 ohmkit.py rc --r 10k --c 100uF --time 1ms

# Lint a parts file (example included in the repo)
python3 ohmkit.py check examples/parts.txt
python3 ohmkit.py check examples/bad-parts.txt; echo "exit $?"
```

The sample parts file `examples/parts.txt` uses comments, mixed notation and one
off-grid value, so it produces a warning. `examples/bad-parts.txt` contains an
unreadable value, a duplicate ref, a missing value and a zero resistance, so it
exits with code `1` and reports each problem with its line number.

## Commands

| Command | What it does |
| --- | --- |
| `encode VALUE [--bands 4\|5] [--tol COLOUR]` | Resistance to colour bands |
| `decode COLOUR...` | Colour bands to resistance and tolerance |
| `snap VALUE [--series E12\|E24\|E96] [--up]` | Nearest (or next-up) preferred value |
| `divider --vin V (--r1 R --r2 R \| --vout V --r1 R)` | Divider output, or solve for R2 |
| `led --supply V [--vf V] [--count N] [--current I]` | Series resistor for an LED string |
| `power --volts V --ohms R` | Current, dissipation and wattage rating |
| `combine R... [--mode series\|parallel]` | Total resistance |
| `rc --r R --c C [--time T]` | RC time constant and charge curve |
| `rl --l L --r R [--time T]` | RL time constant and current rise |
| `check FILE [--series E12\|E24\|E96]` | Lint a `REF VALUE` parts file |

Values accept SI prefixes (`p n u µ m k M G`), optional units (`F H V A s Ω ohm`)
and the resistor letter notation (`4k7`, `4R7`, `1M5`).

## Parts file format

```
# comments start with a hash
R1  4k7
R2  2.2 kΩ    # trailing comments work too
R3  1M5
```

Each non-blank line has a reference and one value. Duplicate references are
errors, and the first occurrence is cited in the message.

## Running the tests

```bash
pip install pytest
python3 -m pytest -q
```

The tests cover value parsing, colour-band round trips, E-series snapping,
divider and LED maths, time constants, the parts-file linter and the command-line
exit codes.

## Project layout

```
ohmkit.py              the calculator and command-line interface
tests/test_ohmkit.py   pytest suite for the core logic and the CLI
examples/parts.txt     a clean sample parts file
examples/bad-parts.txt a parts file with deliberate errors
```

## Notes

- E12 and E24 are fixed tables. E96 is generated as 10^(n/96) rounded to three
  significant figures, following IEC 60063.
- The wattage rule of thumb is a 2× margin: the smallest standard rating at least
  twice the dissipation.
- RC and RL curves use floating point for the exponential. Everything else is exact.
