from decimal import Decimal

from vault.ocr import parse_slip_text, slip_hash


SAMPLE_SLIP = """
ธนาคารไทยพาณิชย์ SCB
นาย สมชาย ใจดี
โอนเงิน 500.00 บาท
บัญชี xxxx3376
จำนวน 500.00 THB
"""


def test_parse_slip_text_extracts_fields():
    result = parse_slip_text(SAMPLE_SLIP)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == Decimal("500.00")
    assert result.receiver_name
    assert result.confidence >= 90


def test_slip_hash_is_stable():
    data = b"same-slip-bytes"
    assert slip_hash(data) == slip_hash(data)
    assert slip_hash(b"other") != slip_hash(data)
