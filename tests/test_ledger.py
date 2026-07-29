"""Ledger persistence, duplicates, receiver history."""

from ce_vault.ledger import Ledger, LedgerEntry, new_ledger_id, slip_hash_bytes


def test_ledger_id_format():
    lid = new_ledger_id()
    assert lid.startswith("LED-")
    assert len(lid) >= 14


def test_create_settle_and_receiver_history(tmp_path):
    db = tmp_path / "ledger.db"
    ledger = Ledger(db)
    entry = LedgerEntry(
        ledger_id="LED-TEST-0001",
        status="OCR VERIFIED",
        thb=500,
        usdt=12.5,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        profit_thb=1.375,
        bank="SCB",
        last4="3376",
        receiver_name="นายสมชาย",
        slip_hash="abc123",
        staff_id=1,
        staff_name="ops",
    )
    ledger.create(entry)
    settled = ledger.update("LED-TEST-0001", status="SETTLED", event="settled")
    assert settled is not None
    assert settled.status == "SETTLED"
    assert settled.settled_at

    hist = ledger.receiver_history("SCB", "3376")
    assert hist is not None
    assert hist["tx_count"] == 1
    assert hist["total_thb"] == 500
    assert hist["total_usdt"] == 12.5

    bal = ledger.vault_balance()
    assert bal["thb"] == 500
    assert bal["usdt"] == 12.5


def test_duplicate_slip_hash(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    h = slip_hash_bytes(b"slip-bytes")
    ledger.create(
        LedgerEntry(
            ledger_id="LED-A",
            status="RECEIVED",
            thb=100,
            bank="SCB",
            last4="1111",
            slip_hash=h,
        )
    )
    found = ledger.find_by_slip_hash(h)
    assert found is not None
    assert found.ledger_id == "LED-A"


def test_delete_entry(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    ledger.create(LedgerEntry(ledger_id="LED-DEL", status="RECEIVED", thb=10))
    assert ledger.delete("LED-DEL") is True
    assert ledger.get("LED-DEL") is None


def test_repeat_receiver_count(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    for i in range(3):
        e = LedgerEntry(
            ledger_id=f"LED-{i}",
            status="OCR VERIFIED",
            thb=100,
            usdt=2.5,
            buy_rate=39.89,
            sell_rate=40,
            profit_pct=0.28,
            profit_thb=0.275,
            bank="KBANK",
            last4="9999",
        )
        ledger.create(e)
        ledger.update(e.ledger_id, status="SETTLED", event="settled")
    assert ledger.count_receiver("KBANK", "9999") == 3
