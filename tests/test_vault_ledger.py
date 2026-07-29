from decimal import Decimal

from vault.ledger import LedgerStore
from vault.models import PipelineStatus


def test_ledger_round_trip_and_duplicate(tmp_path):
    db = LedgerStore(tmp_path / "ledger.db")
    ledger_id = db.next_ledger_id()
    record = {
        "ledger_id": ledger_id,
        "slip_hash": "abc123",
        "receiver_name": "Test",
        "bank": "SCB",
        "last4": "3376",
        "thb": "500.00",
        "usdt": "12.5342",
        "buy_rate": "39.89",
        "sell_rate": "40.00",
        "profit_pct": "0.28",
        "ocr_confidence": 98.6,
        "staff_id": 1,
        "source": "slip",
    }
    saved = db.insert_settled(record)
    assert saved.status == PipelineStatus.SETTLED.value
    assert saved.balance_thb == Decimal("500.00")
    assert db.slip_exists("abc123")
    assert db.get(ledger_id) is not None

    history = db.receiver_history("SCB", "3376")
    assert history is not None
    assert history.transaction_count == 1
    assert history.total_thb == Decimal("500.00")


def test_next_ledger_id_increments(tmp_path):
    db = LedgerStore(tmp_path / "ledger.db")
    first = db.next_ledger_id()
    db.insert_settled(
        {
            "ledger_id": first,
            "thb": "100.00",
            "usdt": "2.5000",
            "buy_rate": "40.00",
            "sell_rate": "40.10",
            "profit_pct": "0.25",
            "receiver_name": "A",
            "bank": "SCB",
            "last4": "1111",
            "source": "usdt",
        }
    )
    second = db.next_ledger_id()
    assert first != second
    assert first.rsplit("-", 1)[0] == second.rsplit("-", 1)[0]
