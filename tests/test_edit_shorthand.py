"""Shorthand parser for the EDIT card: +500 -12.5U."""

from ce_vault.ocr import parse_edit_command


def test_long_form_thb():
    assert parse_edit_command("THB 500") == {"thb": 500.0}


def test_long_form_usdt():
    assert parse_edit_command("USDT 12.5") == {"usdt": 12.5}


def test_shorthand_plus_number_is_thb():
    assert parse_edit_command("+500") == {"thb": 500.0}


def test_shorthand_u_suffix_is_usdt():
    assert parse_edit_command("-12.5U") == {"usdt": 12.5}
    assert parse_edit_command("12.5U") == {"usdt": 12.5}


def test_shorthand_combined():
    out = parse_edit_command("+500 -12.5U")
    assert out == {"thb": 500.0, "usdt": 12.5}


def test_bank_and_last4():
    out = parse_edit_command("BANK SCB 3376")
    assert out == {"bank": "SCB", "last4": "3376"}


def test_long_form_wins_over_shorthand():
    """When both are given, the explicit label wins — no double-set."""
    out = parse_edit_command("THB 500 -12.5U")
    assert out["thb"] == 500.0
    assert out["usdt"] == 12.5
