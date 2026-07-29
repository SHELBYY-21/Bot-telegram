"""Tests for CE Vault card rendering, rates, OCR heuristics, and ledger."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ce_vault import cards, engine, ocr, rates, status, theme
from ce_vault.ledger import LedgerStore
from ce_vault.rates import RateBook
from ce_vault.status import PipelineStatus


def test_theme_money_and_mask():
    assert theme.money("500") == "500.00"
    assert theme.money("1286500") == "1,286,500.00"
    assert theme.crypto("12.53421") == "12.5342"
    assert theme.pct("1.38") == "+1.38%"
    assert theme.mask_account("3376", "SCB") == "SCB ••••3376"


def test_pipeline_only_active_glows():
    html = status.render_pipeline(PipelineStatus.OCR_VERIFIED)
    assert "● <b>OCR VERIFIED</b>" in html
    assert "○ RECEIVED" in html
    assert "○ WAITING USDT" in html
    assert html.count("●") == 1


def test_transaction_card_is_single_card_with_monospace():
    view = cards.TxnView(
        ledger_id="LED-20260318-A1B2",
        thb="500",
        usdt="12.5342",
        buy_rate="39.89",
        sell_rate="40.00",
        profit_pct="0.28",
        receiver="นายทดสอบ",
        bank="SCB",
        last4="3376",
        confidence="98.6",
        status=PipelineStatus.OCR_VERIFIED,
    )
    out = cards.transaction_card(view)
    assert "CE VAULT" in out
    assert "Secure Ledger" in out
    assert "LED-20260318-A1B2" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB ••••3376" in out
    assert out.count("CE VAULT") == 1


def test_ocr_card_layout():
    out = cards.ocr_card(
        cards.OcrView(
            ledger_id="LED-1",
            vision=98.4,
            receiver="นาย...",
            bank="SCB",
            last4="3376",
            amount="500.00",
            warn=False,
            duplicate=False,
        )
    )
    assert "Vision" in out
    assert "98.4%" in out
    assert "Detected Amount" in out
    assert "Verified" in out


def test_error_card_only_three_fields():
    out = cards.error_card(
        cards.ErrorView(problem="Duplicate slip", cause="Hash match", action="Review ledger")
    )
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Buy Rate" not in out


def test_success_card_minimal():
    out = cards.success_card(
        cards.SuccessView(ledger_id="LED-9", profit_pct="0.28", balance_usdt="100.5")
    )
    assert "SETTLED" in out
    assert "Done." in out
    assert "Updated Balance" in out


def test_history_card():
    from datetime import date

    out = cards.history_card(
        cards.HistoryView(
            receiver="x",
            bank="SCB",
            last4="3376",
            txn_count=52,
            total_thb="1286500",
            total_usdt="31944",
            first_seen=date(2026, 3, 18),
            last_seen=date.today(),
            risk="LOW",
        )
    )
    assert "52 Transactions" in out
    assert "1,286,500.00" in out
    assert "Today" in out
    assert "LOW" in out


def test_rates_thb_to_usdt_matches_desk_example():
    book = RateBook.from_floats(39.89, 40.00)
    usdt = book.thb_to_usdt(500)
    assert usdt == Decimal("12.5345")
    assert book.profit_pct() == Decimal("0.28")
    assert book.usdt_to_thb(usdt) == Decimal("500.00")


def test_heuristic_ocr_thai_slip_text():
    text = """
    โอนเงินสำเร็จ
    ผู้รับ: นายสมชาย ใจดี
    ธนาคาร: SCB ไทยพาณิชย์
    บัญชี xxx3376
    จำนวน 500.00 บาท
    """
    result = ocr.heuristic_ocr(text)
    assert result.amount_thb == Decimal("500.00")
    assert result.last4 == "3376"
    assert result.bank == "SCB"
    assert result.receiver_name is not None
    assert result.confidence >= 90


def test_ledger_duplicate_slip_and_settle(tmp_path):
    store = LedgerStore(tmp_path / "t.db")
    desk = engine.DeskState(store=store, rates=RateBook.from_floats(39.89, 40.00))

    a = store.create(slip_hash="abc", status="RECEIVED")
    store.update(
        a.id,
        thb="500",
        usdt="12.5342",
        buy_rate="39.89",
        sell_rate="40.00",
        profit_pct="0.28",
        receiver_name="นายสมชาย",
        bank="SCB",
        last4="3376",
    )
    store.settle(a.id)

    dup = store.find_by_slip_hash("abc")
    assert dup is not None
    assert dup.id == a.id

    hist = store.receiver_history("SCB", "3376")
    assert hist is not None
    assert hist.txn_count == 1
    assert hist.total_thb == Decimal("500")


@pytest.mark.asyncio
async def test_intake_slip_text_produces_confirmation(tmp_path):
    store = LedgerStore(tmp_path / "t2.db")
    desk = engine.DeskState(store=store, rates=RateBook.from_floats(39.89, 40.00))
    text = "Receiver: นายทดสอบ\nBank: SCB\nAccount ****3376\nTHB 500.00"
    record, card, dup = await engine.intake_slip(
        desk,
        image_bytes=None,
        caption=text,
        staff_id=1,
        staff_name="desk",
        chat_id=1,
    )
    assert not dup
    assert record.thb == Decimal("500.00")
    assert record.usdt == Decimal("12.5345")
    assert "Vision" in card
    conf = engine.confirmation_from_record(store.get(record.id))
    assert "<code>500.00</code>" in conf
    assert "Confirm" not in conf  # buttons are separate


def test_parse_usdt_message():
    assert engine.parse_usdt_message("12.5 USDT") == Decimal("12.5")
    assert engine.parse_usdt_message("hello") is None


def test_usdt_intake(tmp_path):
    store = LedgerStore(tmp_path / "t3.db")
    desk = engine.DeskState(store=store, rates=RateBook.from_floats(39.89, 40.00))
    record, card = engine.intake_usdt(desk, Decimal("12.5345"), staff_id=1, staff_name="a", chat_id=1)
    assert record.thb == Decimal("500.00")
    assert "WAITING USDT" in card or "●" in card


def test_settle_success_card(tmp_path):
    store = LedgerStore(tmp_path / "t4.db")
    desk = engine.DeskState(store=store, rates=RateBook.from_floats(39.89, 40.00))
    record, _ = engine.intake_usdt(desk, Decimal("10"), staff_id=1, staff_name="a", chat_id=1)
    _, card = engine.settle(desk, record.id)
    assert "SETTLED" in card
    assert "Done." in card
