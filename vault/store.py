"""Ledger store protocol + factory (SQLite local / Supabase remote)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Protocol

from vault.ledger import Ledger

logger = logging.getLogger("ce_vault.store")


class LedgerStore(Protocol):
    def get_rates(self) -> tuple[float, float]: ...
    def set_rates(self, buy: float, sell: float, updated_by: int | None = None) -> None: ...
    def get_balance(self) -> float: ...
    def set_balance(self, value: float) -> None: ...
    def create_entry(self, **fields: Any) -> dict: ...
    def get(self, entry_id: str) -> dict | None: ...
    def update(self, entry_id: str, **fields: Any) -> dict | None: ...
    def delete(self, entry_id: str) -> bool: ...
    def list_recent(self, limit: int = 10) -> list[dict]: ...
    def find_by_slip_hash(self, slip_hash: str) -> dict | None: ...
    def receiver_history(self, bank: str | None, last4: str | None) -> dict | None: ...
    def is_repeat_receiver(self, bank: str | None, last4: str | None, hours: int = 24) -> bool: ...
    def record_settlement(self, entry_id: str) -> dict | None: ...


def create_ledger() -> LedgerStore:
    """Pick backend from env. Prefer Supabase when URL + service key exist."""
    backend = (os.environ.get("LEDGER_BACKEND") or "").strip().lower()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    ).strip()

    want_supabase = backend in ("supabase", "remote") or (not backend and url and key)
    if want_supabase:
        if not url or not key:
            raise SystemExit(
                "LEDGER_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        from vault.supabase_ledger import SupabaseLedger

        logger.info("ledger backend: supabase (%s)", url)
        return SupabaseLedger(url, key)

    path = Path(os.environ.get("LEDGER_DB", "data/vault.db"))
    logger.info("ledger backend: sqlite (%s)", path)
    return Ledger(path)
