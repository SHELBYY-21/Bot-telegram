"""CE VAULT unit tests — cards, rates, ledger, OCR, auth."""

from __future__ import annotations

import json

import bot
import bot_agents
from ce_vault import cards
from ce_vault.design import CONFIDENCE_WARN
from ce_vault.ledger import Ledger, new_ledger_id
from ce_vault.models import OCRResult, ReceiverHistory, Transaction
from ce_vault.ocr import mock_ocr_from_caption, parse_text_slip, slip_hash_from_bytes
from ce_vault.rates import quote_from_thb, quote_from_usdt


# --- Auth / agents backward compat ----------------------------------------


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()


def test_fmt_agent_escapes_and_includes_fields():
    agent = {
        "id": "bc_1",
        "name": "Fix <script>",
        "status": "RUNNING",
        "source": {"repository": "https://github.com/o/r"},
        "target": {"branchName": "cursor/fix", "prUrl": "https://github.com/o/r/pull/2"},
        "summary": "did things",
    }
    out = bot_agents.fmt_agent(agent)
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
    assert "bc_1" in out
    assert "RUNNING" in out


def test_fmt_agent_minimal():
    out = bot_agents.fmt_agent({"id": "bc_2"})
    assert "bc_2" in out
    assert "UNKNOWN" in out


def test_agents_state_round_trip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(bot_agents, "STATE_FILE", state_file)
    state = bot_agents.load_state()
    assert state == {}
    settings = bot_agents.chat_settings(state, 42)
    settings["repository"] = "https://github.com/o/r"
    bot_agents.save_state(state)
    assert json.loads(state_file.read_text()) == {"42": {"repository": "https://github.com/o/r"}}


def test_load_state_corrupt_file(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json")
    monkeypatch.setattr(bot_agents, "STATE_FILE", state_file)
    assert bot_agents.load_state() == {}


# --- Rates ----------------------------------------------------------------


def test_quote_from_thb(monkeypatch):
    monkeypatch.setenv("BUY_RATE", "39.89")
    monkeypatch.setenv("SELL_RATE", "40.00")
    q = quote_from_thb(500.0)
    assert q.thb == 500.0
    assert q.usdt == 12.5
    assert q.buy_rate == 39.89
    assert q.sell_rate == 40.0
    assert q.profit_pct == round(((40 - 39.89) / 39.89) * 100, 2)
    assert q.profit_thb == 1.38


def test_quote_from_usdt(monkeypatch):
    monkeypatch.setenv("BUY_RATE", "39.89")
    monkeypatch.setenv("SELL_RATE", "40.00")
    q = quote_from_usdt(12.5)
    assert q.thb == 500.0
    assert q.usdt == 12.5


# --- Cards ----------------------------------------------------------------


def test_confirmation_card_monospace_and_single_glow():
    tx = Transaction(
        ledger_id="LD-20260318-A7F2",
        status="WAITING USDT",
        thb=500.0,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=1.38,
        bank="SCB",
        last4="3376",
        confidence=98.6,
    )
    out = cards.confirmation_card(tx)
    assert "CE VAULT" in out
    assert "Secure Ledger" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "<b>● WAITING USDT</b>" in out
    assert "○ RECEIVED" in out
    assert "○ SETTLED" in out
    # Only one glowing status
    assert out.count("<b>●") == 1


def test_ocr_card_warn():
    ocr = OCRResult(
        receiver_name="นายทดสอบ ยาวมากจนควรตัดชื่อ",
        bank="SCB",
        last4="3376",
        amount_thb=500.0,
        confidence=85.0,
        verified=True,
    )
    out = cards.ocr_card("LD-1", ocr, warn=True)
    assert "Vision" in out
    assert "Low Confidence" in out
    assert "Confidence below 90%" in out
    assert "…" in out  # truncated name


def test_error_card_only_three_fields():
    out = cards.error_card("Problem X", "Cause Y", "Action Z")
    assert "Problem" in out and "Problem X" in out
    assert "Cause" in out and "Cause Y" in out
    assert "Action" in out and "Action Z" in out


def test_history_card():
    hist = ReceiverHistory(
        bank="SCB",
        last4="3376",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18T00:00:00Z",
        last_seen="2026-07-29T00:00:00Z",
        risk="LOW",
    )
    out = cards.history_card(hist)
    assert "SCB ••••3376" in out
    assert "52" in out
    assert "LOW" in out


def test_success_card_minimal():
    out = cards.success_card("LD-9", 1.38, 9999.0, 1.38)
    assert "SETTLED" in out
    assert "Done." in out
    assert "Updated Balance" in out


# --- Ledger ---------------------------------------------------------------


def test_ledger_crud_and_duplicate(tmp_path):
    db = Ledger(tmp_path / "vault.db")
    lid = new_ledger_id()
    tx = Transaction(
        ledger_id=lid,
        status="OCR VERIFIED",
        thb=500,
        usdt=12.5,
        bank="SCB",
        last4="3376",
        slip_hash="abc123",
        staff_id=1,
    )
    db.create(tx)
    assert db.get(lid).thb == 500
    assert db.find_by_slip_hash("abc123").ledger_id == lid

    tx.status = "SETTLED"
    tx.settled_at = "2026-07-29T12:00:00Z"
    db.update(tx)
    hist = db.receiver_history("SCB", "3376")
    assert hist.tx_count == 1
    assert hist.total_thb == 500

    bal = db.adjust_balance(-12.5)
    assert bal == -12.5
    assert db.delete(lid) is True
    assert db.get(lid) is None


# --- OCR ------------------------------------------------------------------


def test_parse_text_slip_thai():
    text = "นายสมชาย ใจดี\nSCB xxxx3376\nจำนวน 500.00 บาท"
    result = parse_text_slip(text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == 500.0
    assert result.receiver_name.startswith("นาย")


def test_mock_ocr_stable():
    a = mock_ocr_from_caption(None, "file_abc")
    b = mock_ocr_from_caption(None, "file_abc")
    assert a.amount_thb == b.amount_thb
    assert a.last4 == b.last4
    assert a.confidence >= CONFIDENCE_WARN


def test_slip_hash_bytes():
    assert slip_hash_from_bytes(b"hello") == slip_hash_from_bytes(b"hello")
    assert slip_hash_from_bytes(b"hello") != slip_hash_from_bytes(b"world")
