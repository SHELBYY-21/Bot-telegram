"""SQLite schema for CE VAULT ledger."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id TEXT PRIMARY KEY,
    slip_hash TEXT UNIQUE,
    receiver TEXT,
    bank TEXT,
    last4 TEXT,
    thb REAL NOT NULL,
    usdt REAL NOT NULL,
    buy_rate REAL NOT NULL,
    sell_rate REAL NOT NULL,
    profit_pct REAL NOT NULL,
    staff TEXT NOT NULL,
    status TEXT NOT NULL,
    ocr_confidence REAL,
    ocr_payload TEXT,
    image_path TEXT,
    created_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS receivers (
    bank TEXT NOT NULL,
    last4 TEXT NOT NULL,
    receiver_name TEXT,
    tx_count INTEGER NOT NULL DEFAULT 0,
    total_thb REAL NOT NULL DEFAULT 0,
    total_usdt REAL NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    PRIMARY KEY (bank, last4)
);

CREATE TABLE IF NOT EXISTS slip_index (
    slip_hash TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ledger_id) REFERENCES ledger(id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger(status);
CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_receivers_last_seen ON receivers(last_seen);
"""


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
