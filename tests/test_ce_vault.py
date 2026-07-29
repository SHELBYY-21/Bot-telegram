"""Tests for CE VAULT card system, rates, OCR, and ledger."""

from __future__ import annotations

import pytest

from ce_vault import cards, rates
from ce_vault.design import LedgerStatus
from ce_vault.ledger import Ledger
from ce_vault.ocr import format_receiver_display, parse_text_slip, slip_hash


def test_status_rail_glows_only_active():
    out = cards.status_rail(LedgerStatus.WAITING_USDT)
    assert "● <b>WAITING USDT</b>" in out
    assert "○ SETTLED" in out
    assert "● RECEIVED" in out  # completed steps stay filled
    assert "● OCR VERIFIED" in out


def test_transaction_card_monospace_and_single_card():
    out = cards.transaction_card(
        ledger_id="LV-TEST01",
        thb=500.0,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        receiver="SCB ••••3376",
        confidence=98.6,
    )
    assert "CE VAULT" in out
    assert "LV-TEST01" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB" in out
    assert out.count("CE VAULT") == 1


def test_ocr_card_warns_below_90():
    out = cards.ocr_card(
        ledger_id="LV-1",
        vision=85.0,
        receiver="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount=500.0,
    )
    assert "⚠" in out
    assert "Review" in out


def test_error_card_only_three_fields():
    out = cards.error_card(problem="P", cause="C", action="A")
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Profit" not in out


def test_success_card_minimal():
    out = cards.success_card(ledger_id="LV-9", profit_pct=1.38, balance_usdt=31_944.0)
    assert "SETTLED" in out
    assert "Done." in out
    assert "31,944.0000" in out or "31944" in out.replace(",", "")


def test_history_card_layout():
    out = cards.history_card(
        receiver="SCB ••••3376",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18",
        last_seen="Today",
        risk="LOW",
    )
    assert "52 Transactions" in out
    assert "LOW" in out


def test_quote_from_thb_matches_buy_division():
    q = rates.quote_from_thb(500.0, sell=40.0)
    assert q.buy_rate == pytest.approx(39.89, rel=1e-3)
    assert q.usdt == pytest.approx(500.0 / q.buy_rate, rel=1e-4)
    assert q.profit_pct > 0


def test_quote_from_usdt_roundtrip():
    q = rates.quote_from_usdt(12.5342, sell=40.0)
    assert q.usdt == 12.5342
    assert q.thb > 0


def test_parse_text_slip_thai_bank():
    text = """
    ชื่อ นายสมชาย ใจดี
    SCB xxxx3376
    จำนวน 500.00 บาท
    """
    result = parse_text_slip(text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount == 500.0
    assert result.confidence >= 90


def test_slip_hash_stable():
    assert slip_hash("abc", 100) == slip_hash("abc", 100)
    assert slip_hash("abc", 100) != slip_hash("abc", 101)


def test_format_receiver_display():
    assert format_receiver_display("SCB", "3376") == "SCB ••••3376"


def test_ledger_create_settle_and_history(tmp_path):
    db = tmp_path / "test.db"
    ledger = Ledger(db)
    entry = ledger.create(
        staff_id=1,
        staff_name="ops",
        status=LedgerStatus.RECEIVED,
        receiver="นายสมชาย",
        bank="SCB",
        last4="3376",
        thb=500,
        usdt=12.53,
        buy_rate=39.89,
        sell_rate=40.0,
        profit=0.28,
        slip_hash="abc123",
    )
    assert entry["ledger_id"].startswith("LV-")
    ledger.update(entry["ledger_id"], status=LedgerStatus.SETTLED)
    stats = ledger.receiver_stats("3376")
    assert stats["tx_count"] == 1
    assert float(stats["total_thb"]) == 500
    assert ledger.find_by_slip_hash("abc123") is not None
    assert ledger.risk_for("3376") == "LOW"


def test_ledger_duplicate_slip_detection(tmp_path):
    ledger = Ledger(tmp_path / "dup.db")
    ledger.create(slip_hash="same", last4="1111", bank="SCB", thb=100, status=LedgerStatus.SETTLED)
    assert ledger.find_by_slip_hash("same")["last4"] == "1111"


def test_agent_card_escapes_html():
    out = cards.agent_card(
        {
            "id": "bc_1",
            "name": "Fix <script>",
            "status": "RUNNING",
            "source": {"repository": "https://github.com/o/r"},
            "target": {"branchName": "cursor/fix", "prUrl": "https://github.com/o/r/pull/2"},
            "summary": "did things",
        }
    )
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
    assert "bc_1" in out
    assert "RUNNING" in out
