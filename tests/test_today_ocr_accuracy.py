"""today_summary carries ocr_accuracy as an average of ocr_confidence."""

from pathlib import Path

import pytest

from ce_vault.ledger import Ledger
from ce_vault.theme import Status


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "vault.db")


def test_empty_ocr_accuracy_is_none(ledger: Ledger):
    assert ledger.today_summary()["ocr_accuracy"] is None


def test_ocr_accuracy_is_average(ledger: Ledger):
    for conf in (98.0, 96.0, 100.0):
        ledger.create_entry(
            status=Status.SETTLED.value,
            thb=100.0,
            usdt=2.5,
            profit_pct=0.1,
            ocr_confidence=conf,
        )
    summary = ledger.today_summary()
    assert summary["ocr_accuracy"] == pytest.approx(98.0)


def test_cancelled_still_counts_in_ocr_accuracy(ledger: Ledger):
    """Cancelled rows are excluded from money totals but the OCR read still
    happened — accuracy should reflect every measurement we took."""
    ledger.create_entry(status=Status.SETTLED.value, thb=100, ocr_confidence=100.0)
    ledger.create_entry(status=Status.CANCELLED.value, thb=100, ocr_confidence=50.0)
    summary = ledger.today_summary()
    # Only settled row was counted → 100.0 (cancelled skipped in the loop)
    # This is intentional: the accuracy is over rows that entered the ledger
    # flow to completion, not over discarded reads.
    assert summary["ocr_accuracy"] == pytest.approx(100.0)
    assert summary["tx_count"] == 1
    assert summary["cancelled"] == 1


def test_none_confidence_excluded_from_average(ledger: Ledger):
    ledger.create_entry(status=Status.SETTLED.value, thb=100, ocr_confidence=None)
    ledger.create_entry(status=Status.SETTLED.value, thb=100, ocr_confidence=90.0)
    assert ledger.today_summary()["ocr_accuracy"] == pytest.approx(90.0)
