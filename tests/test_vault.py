import json

import pytest

from config import Settings
from db.ledger import LedgerStore
from services.ocr import OCRService
from services.rates import RateService
from services.transaction import TransactionService
from ui.cards import error_card, ocr_card, success_card, transaction_card
from ui.session import SessionStore
from ui.theme import format_pct, format_thb, format_usdt, mono, status_pipeline


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "vault.db"


@pytest.fixture
def store(db_path):
    return LedgerStore(db_path)


@pytest.fixture
def tx(store):
    rates = RateService(39.89, 40.00)
    ocr = OCRService(provider="mock")
    return TransactionService(store, rates, ocr, staff_name="Tester")


def test_rate_service_from_thb_and_usdt():
    rates = RateService(39.89, 40.00)
    thb_quote = rates.from_thb(500)
    assert thb_quote.thb == 500.0
    assert thb_quote.usdt == 12.5
    assert thb_quote.profit_pct == pytest.approx(0.28, abs=0.01)

    usdt_quote = rates.from_usdt(12.5342)
    assert usdt_quote.usdt == 12.5342
    assert usdt_quote.thb == pytest.approx(501.37, abs=0.01)


def test_ocr_parse_thai_slip_text():
    ocr = OCRService(provider="mock")
    text = (
        "ธนาคารไทยพาณิชย์ SCB\n"
        "โอนเงินให้ นายสมชาย ใจดี\n"
        "เลขบัญชี xxx-x-xx3376\n"
        "จำนวน 500.00 บาท\n"
    )
    parsed = ocr._parse_text(text)
    assert parsed["bank"] == "SCB"
    assert parsed["last4"] == "3376"
    assert parsed["amount_thb"] == 500.0
    assert "นายสมชาย" in parsed["receiver_name"]


@pytest.mark.asyncio
async def test_ocr_process_with_hint():
    ocr = OCRService(provider="mock")
    hint = "ธนาคารไทยพาณิชย์ SCB\nโอนเงินให้ นายทดสอบ\nxxx-3376\nจำนวน 500.00 บาท"
    result = await ocr.process(b"image-bytes", hint=hint)
    assert result.confidence == 98.4
    assert result.verified is True
    assert result.amount_thb == 500.0


def test_ledger_create_settle_and_receiver_history(store, tx):
    from services.ocr import OCRResult

    pending = tx.create_from_thb(1000)
    entry = tx.confirm(pending.ledger_id)
    assert entry.status == "SETTLED"
    assert entry.thb == 1000.0

    ocr = OCRResult(
        receiver_name="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount_thb=500.0,
        confidence=98.6,
        raw_text="slip",
        verified=True,
    )
    pending2 = tx.create_from_ocr(ocr, slip_hash="abc123")
    tx.confirm(pending2.ledger_id)
    history = store.get_receiver("SCB", "3376")
    assert history is not None
    assert history.tx_count == 1
    assert history.total_thb == 500.0
    assert history.risk_level == "LOW"


def test_duplicate_slip_detection(store, tx):
    from services.ocr import OCRResult

    ocr = OCRResult(
        receiver_name="A",
        bank="SCB",
        last4="1111",
        amount_thb=100.0,
        confidence=99.0,
        raw_text="x",
        verified=True,
    )
    tx.create_from_ocr(ocr, slip_hash="dup-hash")
    assert store.slip_exists("dup-hash") is not None


def test_status_pipeline_highlights_active():
    out = status_pipeline("WAITING_USDT")
    assert "● WAITING USDT" in out
    assert "○ RECEIVED" in out
    assert out.count("●") == 1


def test_transaction_card_renders_monospace_numbers(tx):
    pending = tx.create_from_thb(500)
    text = transaction_card(pending)
    assert "<code>" in text
    assert "500.00" in text
    assert "CE VAULT" in text


def test_error_card_structure():
    text = error_card(
        problem="Duplicate slip",
        cause="Already recorded",
        action="Send another slip",
        ledger_id="LV-TEST",
    )
    assert "Problem" in text
    assert "Cause" in text
    assert "Action" in text
    assert "Duplicate slip" in text


def test_success_card(tx, store):
    pending = tx.create_from_thb(250)
    entry = tx.confirm(pending.ledger_id)
    balance = store.totals()
    text = success_card(entry, balance)
    assert "SETTLED" in text
    assert entry.id in text


def test_session_store_round_trip(tmp_path):
    path = tmp_path / "state.json"
    sessions = SessionStore(path)
    from ui.session import ChatSession

    sessions.set(42, ChatSession(message_id=99, ledger_id="LV-1", mode="confirm"))
    loaded = sessions.get(42)
    assert loaded.message_id == 99
    assert loaded.ledger_id == "LV-1"
    assert json.loads(path.read_text())["42"]["mode"] == "confirm"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2")
    monkeypatch.setenv("DEFAULT_BUY_RATE", "39.5")
    cfg = Settings.from_env()
    assert cfg.telegram_token == "token"
    assert cfg.allowed_user_ids == frozenset({1, 2})
    assert cfg.default_buy_rate == 39.5


def test_theme_formatters():
    assert format_thb(1286500) == "1,286,500.00"
    assert format_usdt(31.944) == "31.9440"
    assert format_pct(1.38) == "+1.38%"
    assert "<code>" in mono("12.5342")


def test_parse_amount():
    import bot

    assert bot.parse_amount("12.5342") == ("usdt", 12.5342)
    assert bot.parse_amount("500") == ("thb", 500.0)
    assert bot.parse_amount("500 thb") == ("thb", 500.0)
    assert bot.parse_amount("12.5 usdt") == ("usdt", 12.5)
    assert bot.parse_amount("hello") is None
