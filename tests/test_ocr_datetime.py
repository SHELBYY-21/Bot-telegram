"""Slip datetime extraction — Thai and English label variants + BE year."""

import pytest

from ce_vault.ocr import parse_slip_text


def test_datetime_thai_label_be_year():
    slip = """
    SCB Easy
    วันที่ 04/08/2569  เวลา 14:32
    จำนวนเงิน: 500.00 บาท
    บัญชี: xxx-x-x3376-x
    """
    result = parse_slip_text(slip)
    # Buddhist 2569 → Gregorian 2026
    assert result.slip_datetime == "2026-08-04T14:32:00"


def test_datetime_english_label():
    slip = "Date: 04/08/2026 at 09:15:30\nAmount 500.00 THB"
    result = parse_slip_text(slip)
    assert result.slip_datetime == "2026-08-04T09:15:30"


def test_datetime_bare_pair():
    slip = "SCB 500.00 บาท\nxxx-x-x3376-x\n04-08-2026 14:32"
    result = parse_slip_text(slip)
    assert result.slip_datetime == "2026-08-04T14:32:00"


def test_datetime_date_only_zero_time():
    slip = "Date: 04/08/2026\nAmount 500.00 THB"
    result = parse_slip_text(slip)
    assert result.slip_datetime == "2026-08-04T00:00:00"


def test_datetime_2digit_year():
    slip = "วันที่ 04/08/26 เวลา 14:32"
    result = parse_slip_text(slip)
    assert result.slip_datetime == "2026-08-04T14:32:00"


def test_datetime_missing_returns_none():
    slip = "SCB Easy\nจำนวนเงิน: 500.00 บาท"
    result = parse_slip_text(slip)
    assert result.slip_datetime is None


@pytest.mark.parametrize("bad", ["32/13/2026 14:32", "04/08/1999", "04/08/2026 25:99"])
def test_datetime_rejects_invalid(bad: str):
    slip = f"วันที่ {bad}\nจำนวนเงิน 500.00 บาท"
    result = parse_slip_text(slip)
    assert result.slip_datetime is None
