"""SQLite ledger — rates, balance, lifecycle, receivers."""

from ce_vault.ledger import Ledger
from ce_vault.theme import Status


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
        receiver_name="นายสมชาย",
        thb=500,
        usdt=12.5,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        staff_id=1,
    )
    assert a["id"].startswith("CE-")
    assert store.find_by_slip_hash("hash-1")["id"] == a["id"]

    settled = store.record_settlement(a["id"])
    assert settled["status"] == Status.SETTLED.value
    assert store.get_balance() == 487.5

    hist = store.receiver_history("SCB", "3376")
    assert hist is not None
    assert hist["tx_count"] == 1
    assert hist["total_thb"] == 500


def test_delete_entry(tmp_path):
    store = Ledger(tmp_path / "vault.db")
    e = store.create_entry(status=Status.RECEIVED.value, thb=10)
    assert store.delete(e["id"]) is True
    assert store.get(e["id"]) is None
