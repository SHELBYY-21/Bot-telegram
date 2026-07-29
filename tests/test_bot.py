"""Bot-level helpers and auth for CE VAULT console."""

import bot
from vault.theme import Status


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()


def test_parse_status():
    assert bot.parse_status("OCR VERIFIED") == Status.OCR_VERIFIED
    assert bot.parse_status("WAITING USDT") == Status.WAITING_USDT
    assert bot.parse_status("nope") == Status.RECEIVED


def test_tx_card_text_uses_entry_fields():
    entry = {
        "id": "LV-20260729-0001",
        "status": "OCR VERIFIED",
        "thb": 500,
        "usdt": 12.5,
        "buy_rate": 39.89,
        "sell_rate": 40.0,
        "profit_pct": 0.28,
        "bank": "SCB",
        "last4": "3376",
        "ocr_confidence": 98.4,
    }
    text = bot.tx_card_text(entry)
    assert "LV-20260729-0001" in text
    assert "<code>500.00</code>" in text
    assert "<b>● OCR VERIFIED</b>" in text


def test_usdt_amount_regex():
    assert bot.USDT_AMOUNT_RE.match("12.5")
    assert bot.USDT_AMOUNT_RE.match("12.5 USDT")
    assert bot.USDT_AMOUNT_RE.match("usdt 12")
    assert not bot.USDT_AMOUNT_RE.match("hello")
