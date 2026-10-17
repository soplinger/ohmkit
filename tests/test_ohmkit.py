import os
import sys
from fractions import Fraction

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ohmkit import (  # noqa: E402
    charge_percent,
    check_parts,
    combine,
    decode_bands,
    divider_output,
    divider_r2_for,
    encode_bands,
    format_ohms,
    led_resistor,
    main,
    nearest_standard,
    parse_resistance,
    recommended_rating,
    series_values,
    time_constant,
)


def test_parse_resistance_reads_letter_as_decimal_point():
    assert parse_resistance("4k7") == 4700
    assert parse_resistance("4R7") == Fraction(47, 10)
    assert parse_resistance("1M5") == 1_500_000
    assert parse_resistance("470") == 470


def test_parse_resistance_accepts_units_and_spaces():
    assert parse_resistance("2.2 kΩ") == 2200
    assert parse_resistance("100 ohm") == 100
    assert parse_resistance("10R") == 10


@pytest.mark.parametrize("text", ["4q7", "", "k", "4..7", "1 2 3"])
def test_parse_resistance_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_resistance(text)


def test_format_ohms_uses_largest_prefix():
    assert format_ohms(4700) == "4.7kΩ"
    assert format_ohms(1_000_000) == "1MΩ"
    assert format_ohms(240) == "240Ω"


def test_encode_four_band_matches_textbook_colours():
    assert encode_bands(4700, 4) == ["yellow", "violet", "red", "gold"]


@pytest.mark.parametrize("ohms", [10, Fraction(1, 2), 4700, 220, 1_000_000])
def test_encode_then_decode_round_trips(ohms):
    colours = encode_bands(ohms, 4)
    value, tolerance = decode_bands(colours)
    assert value == ohms
    assert tolerance == 5


def test_encode_five_band_and_decode_five_band():
    colours = encode_bands(1000, 5, "brown")
    assert colours == ["brown", "black", "black", "brown", "brown"]
    assert decode_bands(colours) == (1000, 1)


def test_encode_rejects_values_that_bands_cannot_express():
    with pytest.raises(ValueError, match="cannot be written exactly"):
        encode_bands(4750, 4)


def test_decode_rejects_unknown_colour():
    with pytest.raises(ValueError, match="purple"):
        decode_bands(["purple", "red", "red", "gold"])


def test_nearest_standard_picks_closest_value():
    assert nearest_standard(5000, "E12") == 4700
    assert nearest_standard(4700, "E24") == 4700


def test_nearest_standard_round_up_for_led_safety():
    assert nearest_standard(4701, "E24", direction="up") == 5100


def test_e96_table_has_96_distinct_values_in_one_decade():
    values = series_values("E96")
    assert len(values) == 96
    assert Fraction(402, 100) in values
    assert all(1 <= value < 10 for value in values)


def test_divider_output_is_exact():
    assert divider_output(12, 10_000, 4700) == Fraction(12 * 4700, 14700)


def test_divider_solves_bottom_resistor():
    assert divider_r2_for(12, 5, 10_000) == Fraction(50_000, 7)


def test_divider_rejects_target_above_input():
    with pytest.raises(ValueError, match="below the input"):
        divider_r2_for(5, 6, 10_000)


def test_led_resistor_for_two_leds_on_nine_volts():
    result = led_resistor(9, Fraction("2.1"), 2)
    assert result["drop"] == Fraction("4.8")
    assert result["resistor"] == 240
    assert result["current"] == Fraction(1, 50)
    assert result["power"] == Fraction("0.096")


def test_led_resistor_rejects_supply_below_led_drop():
    with pytest.raises(ValueError, match="does not exceed"):
        led_resistor(3, Fraction("2.1"), 2)


def test_combine_series_and_parallel():
    assert combine([10_000, 4700], "series") == 14700
    assert combine([10, 10], "parallel") == 5
    with pytest.raises(ValueError):
        combine([10, 0], "series")


def test_rc_time_constant_and_charge_curve():
    tau = time_constant(10_000, Fraction(1, 10_000))
    assert tau == 1
    assert charge_percent(tau, tau) == pytest.approx(63.21, abs=0.01)


def test_recommended_rating_uses_double_margin():
    assert recommended_rating(Fraction("0.096")) == Fraction(1, 4)
    assert recommended_rating(3) == 10


def test_check_parts_reports_line_numbers_and_warnings():
    lines = [
        "R1 4k7\n",
        "R2 4k7x\n",
        "# a comment line\n",
        "R1 10k\n",
        "R3\n",
        "R4 1k25  # not on E24\n",
    ]
    rows, errors, warnings = check_parts(lines, "E24")
    assert [row["ref"] for row in rows] == ["R1", "R4"]
    assert len(errors) == 3
    assert errors[0].startswith("line 2:")
    assert errors[1].startswith("line 4:") and "first on line 1" in errors[1]
    assert errors[2].startswith("line 5:")
    assert len(warnings) == 1
    assert "nearest is 1.2kΩ" in warnings[0]


def test_check_parts_standard_values_are_clean():
    rows, errors, warnings = check_parts(["R1 4k7\n", "R2 1k\n"], "E24")
    assert len(rows) == 2
    assert errors == []
    assert warnings == []


def test_cli_encode_prints_colours(capsys):
    assert main(["encode", "4k7"]) == 0
    assert "yellow violet red gold" in capsys.readouterr().out


def test_cli_bad_value_returns_error_code(capsys):
    assert main(["encode", "4.75k"]) == 2
    assert "cannot be written exactly" in capsys.readouterr().err


def test_cli_divider_solve_mode_names_nearest_standard(capsys):
    assert main(["divider", "--vin", "12V", "--vout", "5V", "--r1", "10k"]) == 0
    assert "nearest E24: 6.8kΩ" in capsys.readouterr().out


def test_cli_check_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.txt"
    good.write_text("R1 4k7\nR2 10k\n", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("R1 4k7\nR2 huh\n", encoding="utf-8")
    assert main(["check", str(good)]) == 0
    assert main(["check", str(bad)]) == 1
    assert "line 2" in capsys.readouterr().out
