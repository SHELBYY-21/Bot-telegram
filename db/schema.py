"""SQLite schema for CE VAULT ledger."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank TEXT NOT NULL,
    last4 TEXT NOT NULL,
    name TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    tx_count INTEGER NOT NULL DEFAULT 0,
    total_thb REAL NOT NULL DEFAULT 0,
    total_usdt REAL NOT NULL DEFAULT 0,
    UNIQUE(bank, last4)
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    slip_hash TEXT UNIQUE,
    receiver_id INTEGER,
    staff_id INTEGER NOT NULL,
    thb REAL,
    usdt REAL,
    buy_rate REAL NOT NULL,
    sell_rate REAL NOT NULL,
    profit_pct REAL,
    status TEXT NOT NULL,
    ocr_confidence REAL,
    ocr_data TEXT,
    image_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (receiver_id) REFERENCES receivers(id)
);

CREATE TABLE IF NOT EXISTS balances (
    staff_id INTEGER PRIMARY KEY,
    usdt_balance REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_tx_staff ON transactions(staff_id);
CREATE INDEX IF NOT EXISTS idx_tx_receiver ON transactions(receiver_id);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);
"""
