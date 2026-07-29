"""Tests for slip OCR parser."""

import pytest

from vault.ocr import DEMO_SLIP_TEXT, analyze_slip, parse_slip_text, slip_hash


def test_parse_demo_slip():
    result = parse_slip_text(DEMO_SLIP_TEXT)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == 500.0
    assert result.receiver_name and "สมชาย" in result.receiver_name
    assert result.confidence >= 90.0


def test_parse_empty():
    result = parse_slip_text("")
    assert result.amount_thb is None
    assert result.confidence == 0.0


def test_slip_hash_stable():
    assert slip_hash(b"abc") == slip_hash(b"abc")
    assert slip_hash(b"abc") != slip_hash(b"abd")


@pytest.mark.asyncio
async def test_analyze_slip_text_only():
    result, digest = await analyze_slip(text=DEMO_SLIP_TEXT, file_unique_id="x")
    assert result.amount_thb == 500.0
    assert len(digest) == 64
