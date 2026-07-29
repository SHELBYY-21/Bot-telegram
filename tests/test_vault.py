import json
import re

import pytest

from cards.confirmation import confirmation_card
from cards.error import error_card
from cards.history import history_card
from cards.ocr import ocr_card
from cards.success import success_card
from cards.base import header, status_line, mono
from db.repository import Repository
from services.ledger import LedgerService, generate_ledger_id, hash_slip
from services.ocr import parse_slip_text, process_slip
from services.rates import calc_profit_pct, thb_to_usdt, get_rates


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path / "test.db")


@pytest.fixture
def ledger(repo):
    return LedgerService(repo)


# --- cards ---

def test_header_contains_vault_branding():
    h = header("LV-20260729-ABCD")
    assert "CE VAULT" in h
    assert "Secure Ledger" in h
    assert "LV-20260729-ABCD" in h


def test_status_line_highlights_active():
    s = status_line("OCR_VERIFIED")
    assert "◉" in s
    assert "OCR VERIFIED" in s
    assert "RECEIVED" in s


def test_confirmation_card_uses_monospace_for_amounts():
    tx = {
        "id": "LV-20260729-ABCD",
        "status": "OCR_VERIFIED",
        "thb": 500.00,
        "usdt": 12.5342,
        "buy_rate": 39.89,
        "sell_rate": 40.00,
        "profit_pct": 0.28,
        "ocr_data": {"bank": "SCB", "last4": "3376", "confidence": 98.6},
    }
    card = confirmation_card(tx)
    assert "<code>" in card
    assert "500.00" in card
    assert "12.5342" in card
    assert "SCB" in card
    assert "3376" in card
    assert "<script>" not in card


def test_ocr_card_shows_confidence_warning():
    tx = {"id": "LV-1"}
    ocr = {"confidence": 85.0, "bank": "SCB", "last4": "3376", "amount": 500}
    card = ocr_card(tx, ocr)
    assert "85.0%" in card
    assert "Below 90%" in card


def test_error_card_structure():
    card = error_card("Duplicate Slip", "Already recorded", "Use different slip")
    assert "Problem" in card
    assert "Cause" in card
    assert "Action" in card
    assert "Duplicate Slip" in card


def test_success_card_minimal():
    card = success_card({"id": "LV-1", "profit_pct": 1.38, "_new_balance": 100.5})
    assert "SETTLED" in card
    assert "Done." in card
    assert "LV-1" in card


def test_history_card_receiver_stats():
    receiver = {
        "bank": "SCB",
        "last4": "3376",
        "tx_count": 52,
        "total_thb": 1286500,
        "total_usdt": 31944,
        "first_seen": "2026-03-18T00:00:00+00:00",
        "last_seen": "2026-07-29T00:00:00+00:00",
    }
    card = history_card(receiver, "LOW")
    assert "52 Transactions" in card
    assert "SCB" in card
    assert "LOW" in card


# --- rates ---

def test_thb_to_usdt():
    assert thb_to_usdt(500.00, 39.89) == pytest.approx(12.5345, abs=0.001)


def test_profit_pct():
    assert calc_profit_pct(39.89, 40.00) == pytest.approx(0.28, abs=0.01)


def test_get_rates_from_repo(repo):
    rates = get_rates(repo)
    assert rates.buy_rate == pytest.approx(39.89)
    assert rates.sell_rate == pytest.approx(40.00)


# --- OCR ---

def test_parse_slip_text_thai():
    text = "SCB Siam Commercial Bank\nถึง นาย สมชาย ใจดี\nxxx3376\nจำนวน 500.00 บาท"
    result = parse_slip_text(text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount == 500.00
    assert result.confidence >= 90


def test_parse_slip_text_english():
    text = "Transfer to account xxxx1234\nAmount 1,250.50 THB\nKBank"
    result = parse_slip_text(text)
    assert result.bank == "KBANK"
    assert result.amount == 1250.50


@pytest.mark.asyncio
async def test_process_slip_mock():
    result = await process_slip(b"fake-image-data")
    assert result.amount is not None
    assert result.bank is not None
    assert result.confidence > 0


# --- ledger ---

def test_generate_ledger_id_format():
    lid = generate_ledger_id()
    assert re.match(r"LV-\d{8}-[A-F0-9]{4}", lid)


def test_hash_slip_deterministic():
    assert hash_slip(b"abc") == hash_slip(b"abc")
    assert hash_slip(b"abc") != hash_slip(b"def")


def test_ledger_slip_flow(ledger):
    staff_id = 12345
    slip = b"test-slip-image-data"
    tx = ledger.start_from_slip(staff_id, slip, "/tmp/slip.jpg")
    assert tx["status"] == "RECEIVED"
    assert tx["staff_id"] == staff_id

    ocr = {
        "amount": 500.00,
        "bank": "SCB",
        "last4": "3376",
        "receiver_name": "นาย สมชาย",
        "confidence": 98.4,
    }
    tx = ledger.apply_ocr(tx["id"], ocr)
    assert tx["status"] == "OCR_VERIFIED"
    assert tx["thb"] == 500.00
    assert tx["usdt"] is not None

    settled = ledger.settle(tx["id"])
    assert settled["status"] == "SETTLED"
    assert settled.get("_new_balance") is not None


def test_duplicate_slip_detection(ledger):
    slip = b"duplicate-slip"
    tx1 = ledger.start_from_slip(1, slip, "")
    tx2 = ledger.start_from_slip(2, slip, "")
    assert tx2["id"] == tx1["id"]
    assert tx2.get("_duplicate")


def test_usdt_first_flow(ledger):
    tx = ledger.start_from_usdt(99, 12.5342)
    assert tx["status"] == "WAITING_USDT"
    assert tx["usdt"] == pytest.approx(12.5342, abs=0.001)

    ocr = {"amount": 500.00, "bank": "SCB", "last4": "3376", "confidence": 95.0}
    tx = ledger.apply_ocr(tx["id"], ocr)
    assert tx["thb"] == 500.00


def test_receiver_history_accumulates(ledger):
    slip = b"slip-for-receiver"
    tx = ledger.start_from_slip(1, slip, "")
    ocr = {"amount": 100.0, "bank": "SCB", "last4": "9999", "confidence": 95.0}
    ledger.apply_ocr(tx["id"], ocr)
    ledger.settle(tx["id"])

    receiver = ledger.get_receiver_history("SCB", "9999")
    assert receiver is not None
    assert receiver["tx_count"] == 1
    assert receiver["total_thb"] == 100.0


def test_cancel_transaction(ledger):
    tx = ledger.start_from_usdt(1, 10.0)
    cancelled = ledger.cancel(tx["id"])
    assert cancelled["status"] == "CANCELLED"


def test_repo_state_round_trip(tmp_path, monkeypatch):
    import cursor_bot

    state_file = tmp_path / "state.json"
    monkeypatch.setattr(cursor_bot, "STATE_FILE", state_file)

    state = cursor_bot.load_state()
    assert state == {}
    settings = cursor_bot.chat_settings(state, 42)
    settings["repository"] = "https://github.com/o/r"
    cursor_bot.save_state(state)

    assert json.loads(state_file.read_text()) == {"42": {"repository": "https://github.com/o/r"}}


def test_legacy_fmt_agent_escapes():
    import cursor_bot

    agent = {
        "id": "bc_1",
        "name": "Fix <script>",
        "status": "RUNNING",
        "source": {"repository": "https://github.com/o/r"},
        "target": {"branchName": "cursor/fix", "prUrl": "https://github.com/o/r/pull/2"},
        "summary": "did things",
    }
    out = cursor_bot.fmt_agent(agent)
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
    assert "bc_1" in out
