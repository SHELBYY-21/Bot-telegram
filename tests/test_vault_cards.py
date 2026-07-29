from decimal import Decimal

from vault.cards import CardRenderer
from vault.models import PipelineStatus, ReceiverHistory, RiskLevel, TransactionDraft


def _draft(**kwargs) -> TransactionDraft:
    base = dict(
        ledger_id="LDG-20260729-0001",
        thb=Decimal("500.00"),
        usdt=Decimal("12.5342"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40.00"),
        receiver_name="นาย สมชาย ใจดี",
        bank="SCB",
        last4="3376",
        ocr_confidence=98.6,
        status=PipelineStatus.WAITING_USDT,
    )
    base.update(kwargs)
    return TransactionDraft(**base)


def test_header_contains_brand_and_ledger_id():
    text = CardRenderer.header("LDG-20260729-0001")
    assert "CE VAULT" in text
    assert "Secure Ledger" in text
    assert "LDG-20260729-0001" in text


def test_status_pipeline_highlights_active_only():
    text = CardRenderer.status_pipeline(PipelineStatus.OCR_VERIFIED)
    assert "<b>● OCR VERIFIED</b>" in text
    assert "<b>● RECEIVED</b>" not in text
    assert "● RECEIVED" in text


def test_transaction_card_uses_monospace_for_numbers():
    text = CardRenderer.transaction_card(_draft())
    assert "<code>500.00</code>" in text
    assert "<code>12.5342</code>" in text
    assert "<code>39.89</code>" in text
    assert "+1.38%" not in text  # profit is in mono tags
    assert "SCB" in text
    assert "3376" in text


def test_ocr_card_warn_fields():
    text = CardRenderer.ocr_card(
        _draft(ocr_confidence=82.0, low_confidence=True, duplicate_slip=True)
    )
    assert "Review Required" in text
    assert "Duplicate slip detected" in text
    assert "<code>82.0%</code>" in text


def test_error_card_structure():
    text = CardRenderer.error_card("Problem", "Cause", "Action")
    assert "Problem" in text
    assert "Cause" in text
    assert "Action" in text
    assert "CE VAULT" in text


def test_history_card_formats_totals():
    history = ReceiverHistory(
        receiver_name="Test",
        bank="SCB",
        last4="3376",
        transaction_count=52,
        total_thb=Decimal("1286500"),
        total_usdt=Decimal("31944"),
        first_seen="2026-03-18",
        last_seen="Today",
        risk=RiskLevel.LOW,
    )
    text = CardRenderer.history_card(history)
    assert "52" in text
    assert "1,286,500" in text
    assert "LOW" in text
