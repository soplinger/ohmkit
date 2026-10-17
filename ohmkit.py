#!/usr/bin/env python3
"""ohmkit: an offline resistor and basic circuit calculator.

Encodes and decodes resistor colour bands, reads values such as ``4k7`` or
``2.2 kΩ``, snaps to E12/E24/E96 preferred values, solves voltage dividers
and LED resistors, combines resistors, works out RC/RL time constants,
recommends wattage and checks a plain-text parts file with line-numbered
errors. Resistor arithmetic uses Fraction, so results stay exact until they
are displayed.
"""

import argparse
import math
import re
import sys
from fractions import Fraction

COLOURS = ["black", "brown", "red", "orange", "yellow",
           "green", "blue", "violet", "gray", "white"]
DIGIT_COLOURS = {name: index for index, name in enumerate(COLOURS)}
MULTIPLIER_COLOURS = {**DIGIT_COLOURS, "gold": -1, "silver": -2}
TOLERANCE_COLOURS = {
    "brown": Fraction(1), "red": Fraction(2), "green": Fraction(1, 2),
    "blue": Fraction(1, 4), "violet": Fraction(1, 10), "gray": Fraction(1, 20),
    "gold": Fraction(5), "silver": Fraction(10),
}

# Preferred values within one decade, written as integers and divided by 10.
E_TABLES = {
    "E12": [10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82],
    "E24": [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
            33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91],
}
WATT_RATINGS = [Fraction(1, 8), Fraction(1, 4), Fraction(1, 2),
                Fraction(1), Fraction(2), Fraction(5), Fraction(10)]

_SI_PREFIX = {"p": Fraction(1, 10**12), "n": Fraction(1, 10**9),
              "u": Fraction(1, 10**6), "µ": Fraction(1, 10**6),
              "μ": Fraction(1, 10**6), "m": Fraction(1, 10**3), "": Fraction(1),
              "k": Fraction(10**3), "K": Fraction(10**3),
              "M": Fraction(10**6), "G": Fraction(10**9)}
_SI_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([pnuµμmkKMG]?)\s*"
                    r"(?:[FfHhVvAaSsRr]|Ω|[Oo]hms?)?$")
_SPLIT_RE = re.compile(r"^(\d+)([kKMGR])(\d+)$")
_SPLIT_MULT = {"R": Fraction(1), "k": Fraction(10**3), "K": Fraction(10**3),
               "M": Fraction(10**6), "G": Fraction(10**9)}
_DISPLAY_PREFIXES = [(12, "T"), (9, "G"), (6, "M"), (3, "k"), (0, ""),
                     (-3, "m"), (-6, "µ"), (-9, "n"), (-12, "p")]


def parse_si(text):
    """Read a plain number with an optional SI prefix and unit, e.g. ``4.7k`` or ``10uF``."""
    match = _SI_RE.match(str(text).strip())
    if not match:
        raise ValueError(f"cannot read value '{text}'")
    return Fraction(match.group(1)) * _SI_PREFIX[match.group(2)]


def parse_resistance(text):
    """Read a resistance. ``4k7`` and ``4R7`` use the letter as the decimal point."""
    compact = str(text).strip().replace(" ", "")
    match = _SPLIT_RE.match(compact)
    if match:
        whole, symbol, fraction = match.groups()
        return Fraction(f"{whole}.{fraction}") * _SPLIT_MULT[symbol]
    return parse_si(text)


def format_si(value, unit=""):
    """Display a number with the largest SI prefix that keeps it at or above one."""
    number = float(value)
    if number == 0:
        return f"0{unit}"
    for exponent, prefix in _DISPLAY_PREFIXES:
        if abs(number) >= 10**exponent:
            return f"{number / 10**exponent:.4g}{prefix}{unit}"
    return f"{number:.4g}{unit}"


def format_ohms(ohms):
    return format_si(ohms, "Ω")


def decode_bands(colours):
    """Turn 4 or 5 band colours into (ohms, tolerance-percent)."""
    names = ["gray" if name.strip().lower() == "grey" else name.strip().lower()
             for name in colours]
    if len(names) not in (4, 5):
        raise ValueError(f"expected 4 or 5 colours, got {len(names)}")
    *digit_names, multiplier_name, tolerance_name = names
    for name in digit_names:
        if name not in DIGIT_COLOURS:
            raise ValueError(f"'{name}' is not a digit colour")
    if multiplier_name not in MULTIPLIER_COLOURS:
        raise ValueError(f"'{multiplier_name}' is not a multiplier colour")
    if tolerance_name not in TOLERANCE_COLOURS:
        raise ValueError(f"'{tolerance_name}' is not a tolerance colour")
    digits = int("".join(str(DIGIT_COLOURS[name]) for name in digit_names))
    ohms = Fraction(digits) * Fraction(10) ** MULTIPLIER_COLOURS[multiplier_name]
    return ohms, TOLERANCE_COLOURS[tolerance_name]


def encode_bands(ohms, bands=4, tolerance="gold"):
    """Return the colour list for an exact resistance, or raise if it cannot be written."""
    if bands not in (4, 5):
        raise ValueError("bands must be 4 or 5")
    if tolerance not in TOLERANCE_COLOURS:
        raise ValueError(f"'{tolerance}' is not a tolerance colour")
    ohms = Fraction(ohms)
    if ohms <= 0:
        raise ValueError("only positive resistances can be encoded")
    digits = 3 if bands == 5 else 2
    exponent = 0
    mantissa = ohms
    while mantissa >= 10**digits:
        mantissa /= 10
        exponent += 1
    while mantissa < 10**(digits - 1):
        mantissa *= 10
        exponent -= 1
    if mantissa.denominator != 1:
        raise ValueError(f"{format_ohms(ohms)} cannot be written exactly with "
                         f"{bands} bands; try: ohmkit snap {format_ohms(ohms)}")
    if not -2 <= exponent <= 9:
        raise ValueError(f"{format_ohms(ohms)} is outside the 0.01 Ω to 9 GΩ band range")
    if exponent == -2:
        multiplier = "silver"
    elif exponent == -1:
        multiplier = "gold"
    else:
        multiplier = COLOURS[exponent]
    digit_colours = [COLOURS[int(digit)] for digit in str(int(mantissa))]
    return digit_colours + [multiplier, tolerance]


def series_values(series):
    """Return the one-decade preferred values as Fractions in [1, 10)."""
    key = series.upper()
    if key == "E96":
        # IEC 60063: 10**(n/96) rounded to three significant figures.
        return sorted({Fraction(round(10 ** (n / 96) * 100), 100) for n in range(96)})
    if key in E_TABLES:
        return [Fraction(value, 10) for value in E_TABLES[key]]
    raise ValueError(f"unknown series '{series}' (use E12, E24 or E96)")


def _decade(value):
    exponent = 0
    mantissa = Fraction(value)
    while mantissa >= 10:
        mantissa /= 10
        exponent += 1
    while mantissa < 1:
        mantissa *= 10
        exponent -= 1
    return exponent


def nearest_standard(ohms, series="E24", direction="nearest"):
    """Snap to the closest preferred value, or the smallest one at or above (direction='up')."""
    ohms = Fraction(ohms)
    if ohms <= 0:
        raise ValueError("resistance must be positive")
    base = _decade(ohms)
    candidates = [value * Fraction(10) ** exponent
                  for exponent in range(base - 1, base + 3)
                  for value in series_values(series)]
    if direction == "up":
        return min(candidate for candidate in candidates if candidate >= ohms)
    return min(candidates, key=lambda candidate: (abs(candidate - ohms), candidate))


def error_percent(actual, nominal):
    nominal = Fraction(nominal)
    return float((Fraction(actual) - nominal) / nominal * 100)


def divider_output(vin, r1, r2):
    """Output voltage of a two-resistor divider with R2 on the bottom."""
    vin, r1, r2 = Fraction(vin), Fraction(r1), Fraction(r2)
    return vin * r2 / (r1 + r2)


def divider_r2_for(vin, vout, r1):
    """Bottom resistor needed to produce vout from vin with top resistor r1."""
    vin, vout, r1 = Fraction(vin), Fraction(vout), Fraction(r1)
    if not 0 < vout < vin:
        raise ValueError("target voltage must be above 0 V and below the input voltage")
    return r1 * vout / (vin - vout)


def led_resistor(supply, forward, count=1, current=Fraction(20, 1000), series="E24"):
    """Size a series resistor so the LED string never exceeds the target current."""
    supply, forward, current = Fraction(supply), Fraction(forward), Fraction(current)
    drop = supply - count * forward
    if drop <= 0:
        raise ValueError(f"supply {format_si(supply, 'V')} does not exceed "
                         f"{count} LED drop(s) of {format_si(forward, 'V')}")
    ideal = drop / current
    resistor = nearest_standard(ideal, series, direction="up")
    actual_current = drop / resistor
    return {"drop": drop, "ideal": ideal, "resistor": resistor,
            "current": actual_current, "power": drop * actual_current}


def power_dissipation(volts, ohms):
    volts, ohms = Fraction(volts), Fraction(ohms)
    if ohms <= 0:
        raise ValueError("resistance must be positive")
    current = volts / ohms
    return current, volts * current


def recommended_rating(power, derate=2):
    """Smallest standard wattage rating that keeps dissipation at or below 1/derate of it."""
    needed = Fraction(power) * derate
    for rating in WATT_RATINGS:
        if rating >= needed:
            return rating
    raise ValueError("no standard rating is large enough; split the load across resistors")


def format_watts(rating):
    if rating < 1:
        return f"1/{round(1 / rating)} W"
    return f"{float(rating):g} W"


def combine(resistors, mode):
    values = [Fraction(value) for value in resistors]
    if not values:
        raise ValueError("give at least one resistance")
    if any(value <= 0 for value in values):
        raise ValueError("resistances must be positive")
    if mode == "series":
        return sum(values)
    if mode == "parallel":
        return 1 / sum(1 / value for value in values)
    raise ValueError(f"unknown mode '{mode}' (use series or parallel)")


def time_constant(first, second):
    """RC gives R*C, RL gives L/R; both are returned in seconds."""
    tau = Fraction(first) * Fraction(second)
    if tau <= 0:
        raise ValueError("the two components must both be positive")
    return tau


def charge_percent(elapsed, tau):
    """Percentage of the final value reached after `elapsed` seconds."""
    return 100 * (1 - math.exp(-float(elapsed) / float(tau)))


def check_parts(lines, series="E24"):
    """Validate 'REF VALUE' lines. Returns (rows, errors, warnings)."""
    rows, errors, warnings = [], [], []
    first_seen = {}
    for lineno, raw in enumerate(lines, start=1):
        content = raw.split("#", 1)[0].strip()
        if not content:
            continue
        fields = content.split(None, 1)
        if len(fields) < 2:
            errors.append(f"line {lineno}: expected 'REF VALUE', found no value")
            continue
        ref, text = fields
        if ref in first_seen:
            errors.append(f"line {lineno}: duplicate ref {ref} "
                          f"(first on line {first_seen[ref]})")
            continue
        try:
            ohms = parse_resistance(text)
        except ValueError:
            errors.append(f"line {lineno}: cannot read value '{text}' for {ref}")
            continue
        if ohms <= 0:
            errors.append(f"line {lineno}: {ref} must be a positive resistance")
            continue
        first_seen[ref] = lineno
        standard = nearest_standard(ohms, series)
        deviation = error_percent(standard, ohms)
        row = {"line": lineno, "ref": ref, "ohms": ohms,
               "standard": standard, "deviation": deviation}
        rows.append(row)
        if deviation != 0:
            warnings.append(f"line {lineno}: {ref} {format_ohms(ohms)} is not an "
                            f"{series.upper()} value; nearest is "
                            f"{format_ohms(standard)} ({deviation:+.2f}%)")
    return rows, errors, warnings


def cmd_encode(args):
    ohms = parse_resistance(args.value)
    colours = encode_bands(ohms, args.bands, args.tol)
    print(f"{format_ohms(ohms)}: {' '.join(colours)}")
    return 0


def cmd_decode(args):
    ohms, tolerance = decode_bands(args.colours)
    print(f"{' '.join(args.colours)} = {format_ohms(ohms)} ±{float(tolerance):g}%")
    return 0


def cmd_snap(args):
    ohms = parse_resistance(args.value)
    direction = "up" if args.up else "nearest"
    standard = nearest_standard(ohms, args.series, direction)
    print(f"requested {format_ohms(ohms)}, {args.series} {direction}: "
          f"{format_ohms(standard)} ({error_percent(standard, ohms):+.2f}%)")
    return 0


def cmd_divider(args):
    vin = parse_si(args.vin)
    if args.vout is None:
        if args.r1 is None or args.r2 is None:
            raise ValueError("give --r1 and --r2, or --vout and --r1")
        r1, r2 = parse_resistance(args.r1), parse_resistance(args.r2)
        vout = divider_output(vin, r1, r2)
        print(f"Vout = {format_si(vout, 'V')} (ratio {float(vout / vin):.4f})")
        return 0
    if args.r1 is None:
        raise ValueError("--vout needs --r1")
    r1 = parse_resistance(args.r1)
    r2 = divider_r2_for(vin, parse_si(args.vout), r1)
    standard = nearest_standard(r2, args.series)
    achieved = divider_output(vin, r1, standard)
    print(f"R2 = {format_ohms(r2)} exact")
    print(f"nearest {args.series}: {format_ohms(standard)} gives "
          f"{format_si(achieved, 'V')} ({error_percent(achieved, parse_si(args.vout)):+.2f}%)")
    return 0


def cmd_led(args):
    result = led_resistor(parse_si(args.supply), parse_si(args.vf), args.count,
                          parse_si(args.current), args.series)
    print(f"supply {args.supply}, {args.count} x {args.vf} LED, {args.current} target")
    print(f"voltage across resistor: {format_si(result['drop'], 'V')}")
    print(f"ideal resistance: {format_ohms(result['ideal'])}")
    print(f"use {format_ohms(result['resistor'])} ({args.series}, at least the ideal)")
    print(f"current: {format_si(result['current'], 'A')}, "
          f"power: {format_si(result['power'], 'W')}")
    print(f"resistor rating: {format_watts(recommended_rating(result['power']))} "
          f"(2x derating)")
    return 0


def cmd_power(args):
    volts = parse_si(args.volts)
    ohms = parse_resistance(args.ohms)
    current, power = power_dissipation(volts, ohms)
    print(f"current {format_si(current, 'A')}, power {format_si(power, 'W')}")
    print(f"rating: {format_watts(recommended_rating(power))} (2x derating)")
    return 0


def cmd_combine(args):
    values = [parse_resistance(value) for value in args.resistors]
    total = combine(values, args.mode)
    print(f"{args.mode} of {len(values)}: {format_ohms(total)}")
    return 0


def _print_time_constant(label, tau, elapsed_text):
    print(f"{label} time constant: {format_si(float(tau), 's')}")
    for multiple in range(1, 6):
        percent = charge_percent(multiple * tau, tau)
        print(f"  {multiple} tau ({format_si(float(multiple * tau), 's')}): {percent:.1f}%")
    if elapsed_text is not None:
        elapsed = parse_si(elapsed_text)
        print(f"at {format_si(float(elapsed), 's')}: {charge_percent(elapsed, tau):.2f}%")


def cmd_rc(args):
    tau = time_constant(parse_resistance(args.r), parse_si(args.c))
    _print_time_constant("RC", tau, args.time)
    return 0


def cmd_rl(args):
    tau = time_constant(parse_si(args.l), 1 / parse_resistance(args.r))
    _print_time_constant("RL", tau, args.time)
    return 0


def cmd_check(args):
    with open(args.file, encoding="utf-8") as handle:
        lines = handle.readlines()
    rows, errors, warnings = check_parts(lines, args.series)
    if rows:
        print(f"{'line':>4}  {'ref':<8} {'value':>10}  {'standard':>10}  {'dev %':>7}")
        for row in rows:
            print(f"{row['line']:>4}  {row['ref']:<8} {format_ohms(row['ohms']):>10}  "
                  f"{format_ohms(row['standard']):>10}  {row['deviation']:>+7.2f}")
    for message in errors:
        print(f"error: {message}")
    for message in warnings:
        print(f"warning: {message}")
    print(f"{len(rows)} part(s), {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ohmkit", description="Offline resistor and basic circuit calculator.")
    commands = parser.add_subparsers(dest="command", required=True)

    encode = commands.add_parser("encode", help="resistance to colour bands")
    encode.add_argument("value", help="e.g. 4k7, 2.2k, 470R")
    encode.add_argument("--bands", type=int, choices=(4, 5), default=4)
    encode.add_argument("--tol", default="gold", help="tolerance colour (default gold, 5%%)")
    encode.set_defaults(func=cmd_encode)

    decode = commands.add_parser("decode", help="colour bands to resistance")
    decode.add_argument("colours", nargs="+", help="e.g. yellow violet red gold")
    decode.set_defaults(func=cmd_decode)

    snap = commands.add_parser("snap", help="nearest preferred value")
    snap.add_argument("value")
    snap.add_argument("--series", default="E24", choices=("E12", "E24", "E96"))
    snap.add_argument("--up", action="store_true", help="round up to the next value")
    snap.set_defaults(func=cmd_snap)

    divider = commands.add_parser("divider", help="voltage divider output or solve R2")
    divider.add_argument("--vin", required=True, help="input voltage, e.g. 12V")
    divider.add_argument("--r1", help="top resistor")
    divider.add_argument("--r2", help="bottom resistor (forward mode)")
    divider.add_argument("--vout", help="target output voltage (solve mode)")
    divider.add_argument("--series", default="E24", choices=("E12", "E24", "E96"))
    divider.set_defaults(func=cmd_divider)

    led = commands.add_parser("led", help="series resistor for an LED string")
    led.add_argument("--supply", required=True, help="supply voltage, e.g. 9V")
    led.add_argument("--vf", default="2.1V", help="forward voltage per LED")
    led.add_argument("--count", type=int, default=1, help="LEDs in series")
    led.add_argument("--current", default="20mA", help="target current")
    led.add_argument("--series", default="E24", choices=("E12", "E24", "E96"))
    led.set_defaults(func=cmd_led)

    power = commands.add_parser("power", help="current, power and resistor rating")
    power.add_argument("--volts", required=True)
    power.add_argument("--ohms", required=True)
    power.set_defaults(func=cmd_power)

    combine_cmd = commands.add_parser("combine", help="series or parallel total")
    combine_cmd.add_argument("resistors", nargs="+")
    combine_cmd.add_argument("--mode", choices=("series", "parallel"), default="series")
    combine_cmd.set_defaults(func=cmd_combine)

    rc = commands.add_parser("rc", help="RC time constant and charge curve")
    rc.add_argument("--r", required=True, help="resistance, e.g. 10k")
    rc.add_argument("--c", required=True, help="capacitance, e.g. 100uF")
    rc.add_argument("--time", help="optional elapsed time, e.g. 1ms")
    rc.set_defaults(func=cmd_rc)

    rl = commands.add_parser("rl", help="RL time constant and current rise")
    rl.add_argument("--l", required=True, help="inductance, e.g. 10mH")
    rl.add_argument("--r", required=True, help="resistance, e.g. 100")
    rl.add_argument("--time", help="optional elapsed time, e.g. 1ms")
    rl.set_defaults(func=cmd_rl)

    check = commands.add_parser("check", help="lint a plain-text parts file")
    check.add_argument("file", help="lines of 'REF VALUE'; '#' starts a comment")
    check.add_argument("--series", default="E24", choices=("E12", "E24", "E96"))
    check.set_defaults(func=cmd_check)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, ZeroDivisionError) as exc:
        print(f"ohmkit: error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ohmkit: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
