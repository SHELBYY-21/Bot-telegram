"""SQLite ledger today_summary + today_by_staff dashboard queries."""

from pathlib import Path

import pytest

from ce_vault.ledger import Ledger
from ce_vault.theme import Status


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "vault.db")


def _make(ledger: Ledger, **fields):
    return ledger.create_entry(**fields)


def test_empty_summary(ledger: Ledger):
    summary = ledger.today_summary()
    assert summary["tx_count"] == 0
    assert summary["thb"] == 0.0
    assert summary["usdt"] == 0.0
    assert summary["profit_thb"] == 0.0
    assert summary["pending"] == 0
    assert summary["settled"] == 0
    assert summary["cancelled"] == 0


def test_summary_sums_settled_and_pending(ledger: Ledger):
    _make(
        ledger,
        status=Status.SETTLED.value,
        thb=5000.0,
        usdt=125.0,
        buy_rate=40.0,
        sell_rate=40.1,
        profit_pct=0.25,
        staff_id=1,
        staff_name="Alice",
    )
    _make(
        ledger,
        status=Status.WAITING_USDT.value,
        thb=3000.0,
        usdt=74.8,
        buy_rate=40.1,
        sell_rate=40.1,
        profit_pct=0.0,
        staff_id=2,
        staff_name="Bob",
    )
    summary = ledger.today_summary()
    assert summary["tx_count"] == 2
    assert summary["settled"] == 1
    assert summary["pending"] == 1
    assert summary["thb"] == 8000.0
    assert summary["usdt"] == pytest.approx(199.8)
    # 5000 * 0.25 / 100 + 3000 * 0 = 12.50
    assert summary["profit_thb"] == pytest.approx(12.50)


def test_summary_excludes_cancelled_from_totals(ledger: Ledger):
    _make(
        ledger,
        status=Status.CANCELLED.value,
        thb=99999.0,
        usdt=2500.0,
        profit_pct=100.0,
    )
    _make(ledger, status=Status.SETTLED.value, thb=1000.0, usdt=25.0, profit_pct=1.0)
    summary = ledger.today_summary()
    assert summary["cancelled"] == 1
    assert summary["tx_count"] == 1
    assert summary["thb"] == 1000.0
    assert summary["usdt"] == 25.0


def test_by_staff_groups_and_sorts(ledger: Ledger):
    for _ in range(3):
        _make(
            ledger,
            status=Status.SETTLED.value,
            thb=1000.0,
            usdt=25.0,
            profit_pct=1.0,
            staff_id=1,
            staff_name="Alice",
        )
    _make(
        ledger,
        status=Status.SETTLED.value,
        thb=500.0,
        usdt=12.5,
        profit_pct=1.0,
        staff_id=2,
        staff_name="Bob",
    )
    _make(
        ledger,
        status=Status.CANCELLED.value,
        thb=99.0,
        usdt=0,
        profit_pct=0,
        staff_id=2,
        staff_name="Bob",
    )
    rows = ledger.today_by_staff()
    assert [(r["staff_name"], r["tx_count"]) for r in rows] == [
        ("Alice", 3),
        ("Bob", 1),  # Cancelled excluded
    ]
    alice = rows[0]
    assert alice["thb"] == 3000.0
    assert alice["profit_thb"] == pytest.approx(30.0)
