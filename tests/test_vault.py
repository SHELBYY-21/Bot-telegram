"""Rate engine + OCR + ledger integration tests."""

import pytest

from ce_vault import flow, ocr
from ce_vault.ledger import Ledger
from ce_vault.models import OCRResult
from ce_vault.rates import profit_pct, quote_from_thb, quote_from_usdt
from ce_vault.theme import TxStatus


def test_quote_from_thb_never_asks_buy_rate(monkeypatch):
    monkeypatch.setenv("BUY_RATE", "39.89")
    monkeypatch.setenv("SELL_RATE", "40.00")
    q = quote_from_thb(500)
    assert q.usdt == pytest.approx(12.5342, rel=1e-4)
    assert q.buy_rate == 39.89
    assert q.sell_rate == 40.00
    assert q.profit_pct == round(profit_pct(39.89, 40.0), 2)


def test_quote_from_usdt(monkeypatch):
    monkeypatch.setenv("BUY_RATE", "40")
    monkeypatch.setenv("SELL_RATE", "40.5")
    q = quote_from_usdt(10)
    assert q.thb == 400.0
    assert q.usdt == 10.0


def test_parse_slip_text_scb():
    text = """
    โอนเงินสำเร็จ
    ธนาคารไทยพาณิชย์ SCB
    ชื่อบัญชี: นายสมชาย ใจดี
    บัญชี xxxx3376
    จำนวน 500.00 บาท
    """
    result = ocr.parse_slip_text(text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == 500.0
    assert "สมชาย" in result.receiver_name
    assert result.confidence >= 90
    assert result.verified


def test_parse_slip_low_confidence_warns():
    result = ocr.parse_slip_text("hello world")
    assert result.confidence < 90
    assert any("below 90" in w.lower() or "not detected" in w.lower() for w in result.warnings)


def test_slip_hash_stable():
    assert ocr.slip_hash(b"abc") == ocr.slip_hash(b"abc")
    assert ocr.slip_hash(b"abc") != ocr.slip_hash(b"abd")


def test_ledger_settle_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BUY_RATE", "39.89")
    monkeypatch.setenv("SELL_RATE", "40.00")
    store = Ledger(tmp_path / "vault.db")
    ocr_result = OCRResult(
        receiver_name="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount_thb=500.0,
        confidence=98.4,
        verified=True,
    )
    tx = flow.build_from_ocr(
        store,
        ocr_result,
        slip_hash="abc123",
        staff_id=1,
        staff_name="Ops",
        chat_id=99,
    )
    assert tx.status == TxStatus.OCR_VERIFIED.value
    assert store.find_by_slip_hash("abc123") is not None

    settled, balance = store.settle(tx.ledger_id)
    assert settled.status == TxStatus.SETTLED.value
    assert balance == pytest.approx(settled.usdt)
    profile = store.receiver_profile("SCB", "3376")
    assert profile is not None
    assert profile.tx_count == 1
    assert profile.total_thb == 500.0
    store.close()


def test_duplicate_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("BUY_RATE", "40")
    monkeypatch.setenv("SELL_RATE", "40")
    store = Ledger(tmp_path / "vault.db")
    tx = flow.build_from_usdt(store, 5.0, staff_id=1, staff_name="A", chat_id=1)
    assert tx.status == TxStatus.WAITING_USDT.value
    store.soft_delete(tx.ledger_id)
    gone = store.get(tx.ledger_id)
    assert gone is not None
    assert gone.status == TxStatus.DELETED.value
    assert gone.deleted_at
    store.close()


def test_apply_thb_edit_recalculates(monkeypatch):
    monkeypatch.setenv("BUY_RATE", "40")
    monkeypatch.setenv("SELL_RATE", "41")
    from ce_vault.models import Transaction

    tx = Transaction(ledger_id="LV-X", thb=100, usdt=2.5, confidence=95)
    flow.apply_thb_edit(tx, 800)
    assert tx.thb == 800
    assert tx.usdt == 20.0
    assert tx.buy_rate == 40
