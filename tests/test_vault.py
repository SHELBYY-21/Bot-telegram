"""CE VAULT unit tests — cards, rates, OCR, ledger."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ce_vault.ledger import LedgerEntry, LedgerStore
from ce_vault.ocr import detect_repeated_receiver, image_hash, parse_slip_text
from ce_vault.rates import RateService, profit_pct, quote_from_thb, quote_from_usdt
from ce_vault.theme import money, pct, to_decimal
from ce_vault.ui import (
    ErrorView,
    HistoryView,
    OcrResultView,
    PipelineStatus,
    SuccessView,
    TxDraft,
    card_confirmation,
    card_delete,
    card_edit,
    card_error,
    card_history,
    card_ocr,
    card_success,
    card_transaction,
)
from ce_vault.ui.status import render_pipeline
import bot
import agents_bridge


# --- theme / rates -------------------------------------------------------

def test_money_and_pct_formatting():
    assert money(Decimal("500")) == "500.00"
    assert money("1286500") == "1,286,500.00"
    assert pct(Decimal("1.38")) == "+1.38%"
    assert pct(Decimal("-0.5")) == "-0.50%"
    assert to_decimal("1,234.56") == Decimal("1234.56")


def test_quote_from_thb_matches_spec_example():
    q = quote_from_thb(Decimal("500"), Decimal("39.89"), Decimal("40.00"))
    assert q.thb == Decimal("500.00")
    assert q.usdt == Decimal("12.5000")
    assert q.profit_pct == Decimal("0.28")


def test_quote_from_usdt():
    q = quote_from_usdt(Decimal("12.5342"), Decimal("39.89"), Decimal("40.00"))
    assert q.usdt == Decimal("12.5342")
    assert q.thb == Decimal("501.37")
    assert profit_pct(Decimal("39.89"), Decimal("40.00")) == Decimal("0.28")


def test_rate_service_never_requires_buy_from_user(tmp_path):
    store = LedgerStore(tmp_path / "t.db")
    store.set_rates(Decimal("39.89"), Decimal("40.00"))
    svc = RateService(store)
    q = svc.from_thb(Decimal("500"))
    assert q.buy_rate == Decimal("39.89")
    assert q.sell_rate == Decimal("40.00")
    buy, sell = svc.set(sell=Decimal("40.50"))
    assert buy == Decimal("39.89")
    assert sell == Decimal("40.50")


# --- status / cards ------------------------------------------------------

def test_pipeline_only_one_active_glows():
    out = render_pipeline(PipelineStatus.WAITING_USDT)
    assert out.count("<b>●") == 1
    assert "WAITING USDT" in out
    assert "○ SETTLED" in out
    assert "● OCR VERIFIED" in out  # past, not glowing


def test_transaction_card_layout():
    draft = TxDraft(
        ledger_id="LDG-20260318-A7F2",
        thb=Decimal("500.00"),
        usdt=Decimal("12.5342"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40.00"),
        profit_pct=Decimal("1.38"),
        receiver="นายทดสอบ",
        bank="SCB",
        last4="3376",
        confidence=Decimal("98.6"),
    )
    out = card_confirmation(draft)
    assert "CE VAULT" in out
    assert "LDG-20260318-A7F2" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB ••••3376" in out
    assert "+1.38%" in out
    assert "Confirm" in out


def test_ocr_card_warns_below_90():
    view = OcrResultView(
        ledger_id="LDG-1",
        confidence=Decimal("88.0"),
        receiver="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount_thb=Decimal("500"),
        verified=False,
        warning="Confidence below 90% — review before settle",
    )
    out = card_ocr(view)
    assert "LOW" in out
    assert "Vision" in out
    assert "Detected Amount" in out
    assert "paragraph" not in out.lower()


def test_history_success_error_edit_delete_cards():
    hist = card_history(
        HistoryView(
            receiver_mask="SCB ••••3376",
            tx_count=52,
            total_thb=Decimal("1286500"),
            total_usdt=Decimal("31944"),
            first_seen="2026-03-18",
            last_seen="Today",
            risk="LOW",
        )
    )
    assert "52" in hist
    assert "1,286,500.00" in hist
    assert "LOW" in hist

    ok = card_success(
        SuccessView("LDG-1", Decimal("1.38"), Decimal("99987.4658"))
    )
    assert "SETTLED" in ok
    assert "Done." in ok

    err = card_error(ErrorView("Duplicate slip", "Hash collision", "Resend original"))
    assert "Duplicate slip" in err
    assert "Hash collision" in err
    assert "Resend original" in err
    assert "Problem" in err
    assert "Cause" in err
    assert "Action" in err

    draft = TxDraft(
        ledger_id="LDG-1",
        thb=Decimal("100"),
        usdt=Decimal("2.5"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40"),
        profit_pct=Decimal("0.28"),
        receiver="x",
        bank="SCB",
        last4="3376",
    )
    assert "Edit Entry" in card_edit(draft)
    assert "permanent" in card_delete("LDG-1", "SCB ••••3376")


def test_card_transaction_uses_monospace_numbers():
    draft = TxDraft(
        ledger_id="LDG-1",
        thb=Decimal("500"),
        usdt=Decimal("12.5"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40"),
        profit_pct=Decimal("0.28"),
        receiver="x",
        bank="KBANK",
        last4="1234",
    )
    out = card_transaction(draft)
    assert out.count("<code>") >= 5


# --- OCR -----------------------------------------------------------------

def test_parse_thai_slip_text():
    text = """
    โอนเงินสำเร็จ
    ชื่อบัญชี: นายสมชาย ใจดี
    ธนาคารไทยพาณิชย์ SCB
    บัญชี xxx3376
    จำนวนเงิน: 500.00 บาท
    """
    ocr = parse_slip_text(text)
    assert ocr.bank == "SCB"
    assert ocr.last4 == "3376"
    assert ocr.amount_thb == Decimal("500.00")
    assert "สมชาย" in ocr.receiver
    assert ocr.confidence >= Decimal("90")
    assert ocr.verified is True


def test_ocr_low_confidence_warning():
    ocr = parse_slip_text("hello world")
    assert ocr.confidence < Decimal("90")
    assert ocr.verified is False
    assert ocr.warning is not None


def test_duplicate_hash_stable():
    assert image_hash(b"abc") == image_hash(b"abc")
    assert image_hash(b"abc") != image_hash(b"abd")


def test_repeated_receiver_warning():
    assert detect_repeated_receiver({"tx_count": 2}) is None
    assert "Repeated" in (detect_repeated_receiver({"tx_count": 8}) or "")


# --- ledger --------------------------------------------------------------

def test_ledger_crud_and_receiver_history(tmp_path):
    store = LedgerStore(tmp_path / "ledger.db")
    lid = store.new_ledger_id()
    assert lid.startswith("LDG-")

    entry = LedgerEntry(
        ledger_id=lid,
        status="SETTLED",
        thb=Decimal("500"),
        usdt=Decimal("12.5"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40"),
        profit=Decimal("0.28"),
        receiver="นายทดสอบ",
        bank="SCB",
        last4="3376",
        confidence=Decimal("98.4"),
        staff="ops",
        slip_hash="abc",
        settled_at="2026-07-29T10:00:00Z",
    )
    store.upsert(entry)
    got = store.get(lid)
    assert got is not None
    assert got.thb == Decimal("500")
    assert got.bank == "SCB"

    assert store.find_by_slip_hash("abc").ledger_id == lid

    hist = store.receiver_history("SCB", "3376")
    assert hist["tx_count"] == 1
    assert hist["total_thb"] == Decimal("500")
    assert hist["risk"] == "LOW"

    bal = store.adjust_balance(Decimal("-12.5"))
    assert bal == store.get_balance()
    assert store.delete(lid) is True
    assert store.get(lid) is None


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()


def test_state_round_trip(tmp_path, monkeypatch):
    import json

    state_file = tmp_path / "state.json"
    monkeypatch.setattr(bot, "STATE_FILE", state_file)
    state = bot.load_state()
    assert state == {}
    settings = bot.chat_settings(state, 42)
    settings["repository"] = "https://github.com/o/r"
    bot.save_state(state)
    assert json.loads(state_file.read_text()) == {"42": {"repository": "https://github.com/o/r"}}


def test_load_state_corrupt_file(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json")
    monkeypatch.setattr(bot, "STATE_FILE", state_file)
    assert bot.load_state() == {}


def test_fmt_agent_still_available():
    out = agents_bridge.fmt_agent(
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
