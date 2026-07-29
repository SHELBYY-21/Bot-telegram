"""Tests for SQLite ledger."""

from vault.ledger import Ledger
from vault.theme import Status


def test_rates_and_balance_roundtrip(tmp_path):
    store = Ledger(tmp_path / "vault.db")
    buy, sell = store.get_rates()
    assert buy > 0 and sell > 0
    store.set_rates(39.5, 40.1, updated_by=1)
    assert store.get_rates() == (39.5, 40.1)
    store.set_balance(1000)
    assert store.get_balance() == 1000.0
    assert store.adjust_balance(-12.5) == 987.5


def test_ledger_lifecycle_and_duplicate_slip(tmp_path):
    store = Ledger(tmp_path / "vault.db")
    store.set_balance(500)

    a = store.create_entry(
        status=Status.OCR_VERIFIED.value,
        slip_hash="hash-1",
        bank="SCB",
        last4="3376",
        receiver_name="Somchai",
        thb=500,
        usdt=12.5,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        staff_id=1,
    )
    assert a["id"].startswith("LV-")
    assert store.find_by_slip_hash("hash-1")["id"] == a["id"]

    store.update(a["id"], status=Status.WAITING_USDT.value)
    settled = store.record_settlement(a["id"])
    assert settled["status"] == Status.SETTLED.value
    assert store.get_balance() == 487.5

    hist = store.receiver_history("SCB", "3376")
    assert hist["tx_count"] == 1
    assert hist["total_thb"] == 500.0

    b = store.create_entry(
        status=Status.RECEIVED.value,
        bank="SCB",
        last4="3376",
        thb=100,
        usdt=2.5,
    )
    assert store.is_repeat_receiver("SCB", "3376")

    assert store.delete(b["id"]) is True
    assert store.get(b["id"]) is None


def test_sequential_ledger_ids(tmp_path):
    store = Ledger(tmp_path / "vault.db")
    first = store.create_entry(thb=1, usdt=0.01)
    second = store.create_entry(thb=2, usdt=0.02)
    assert first["id"] != second["id"]
    assert first["id"].rsplit("-", 1)[0] == second["id"].rsplit("-", 1)[0]
