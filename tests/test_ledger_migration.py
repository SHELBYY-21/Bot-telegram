"""slip_url column: round-trip plus the migration for pre-existing databases."""

import sqlite3
from pathlib import Path

from ce_vault.ledger import Ledger
from ce_vault.theme import Status


def test_slip_url_round_trips(tmp_path: Path):
    store = Ledger(tmp_path / "vault.db")
    entry = store.create_entry(
        status=Status.OCR_VERIFIED.value,
        slip_file_id="AgACAgUx",
        slip_url="https://proj.supabase.co/storage/v1/object/public/slips/x.jpg",
        slip_hash="hash-1",
        thb=500,
    )
    assert entry["slip_url"].endswith("/slips/x.jpg")
    assert store.get(entry["id"])["slip_url"] == entry["slip_url"]
    # The Telegram handle is kept alongside, not replaced.
    assert entry["slip_file_id"] == "AgACAgUx"


def test_slip_url_defaults_to_none(tmp_path: Path):
    store = Ledger(tmp_path / "vault.db")
    entry = store.create_entry(status=Status.RECEIVED.value, thb=10)
    assert entry["slip_url"] is None


def test_migration_adds_column_to_legacy_db(tmp_path: Path):
    """A vault.db created before slip_url existed must gain the column.

    CREATE TABLE IF NOT EXISTS silently skips an existing table, so without
    the migration the new column would never appear and every insert would
    fail with "no column named slip_url".
    """
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ledger (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            slip_file_id TEXT,
            slip_hash TEXT,
            ocr_json TEXT,
            ocr_confidence REAL,
            receiver_name TEXT,
            bank TEXT,
            last4 TEXT,
            thb REAL,
            usdt REAL,
            buy_rate REAL,
            sell_rate REAL,
            profit_pct REAL,
            staff_id INTEGER,
            staff_name TEXT,
            chat_id INTEGER,
            message_id INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            settled_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    columns = _columns(db)
    assert "slip_url" not in columns  # precondition

    store = Ledger(db)  # opening runs the migration

    assert "slip_url" in _columns(db)
    entry = store.create_entry(status=Status.RECEIVED.value, slip_url="u", thb=1)
    assert entry["slip_url"] == "u"


def test_migration_is_idempotent(tmp_path: Path):
    db = tmp_path / "vault.db"
    Ledger(db)
    Ledger(db)  # second open must not raise "duplicate column name"
    assert _columns(db).count("slip_url") == 1


def _columns(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(ledger)")]
    finally:
        conn.close()
