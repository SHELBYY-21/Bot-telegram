"""Ledger orchestration — IDs, quoting, duplicate detection."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ce_vault.config import (
    STATUS_OCR,
    STATUS_RECEIVED,
    STATUS_SETTLED,
    STATUS_WAITING,
    Settings,
)
from ce_vault.db import LedgerStore
from ce_vault.models import OCRResult, Transaction, iso
from ce_vault.services.rates import apply_quote, quote_from_thb, quote_from_usdt


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"LD-{stamp}-{secrets.token_hex(3).upper()}"


def slip_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LedgerService:
    def __init__(self, store: LedgerStore, settings: Settings):
        self.store = store
        self.settings = settings

    def current_rates(self) -> tuple[float, float]:
        buy = float(self.store.get_setting("buy_rate", str(self.settings.buy_rate)))
        sell = float(self.store.get_setting("sell_rate", str(self.settings.sell_rate)))
        return buy, sell

    def set_rates(self, buy: float, sell: float) -> None:
        self.store.set_setting("buy_rate", f"{buy:.4f}")
        self.store.set_setting("sell_rate", f"{sell:.4f}")

    def create_from_slip(
        self,
        *,
        staff: str,
        staff_id: int | None,
        chat_id: int | None,
        image_path: str | None = None,
        slip_hash: str | None = None,
    ) -> Transaction:
        now = iso()
        tx = Transaction(
            ledger_id=new_ledger_id(),
            status=STATUS_RECEIVED,
            staff=staff,
            staff_id=staff_id,
            chat_id=chat_id,
            image_path=image_path,
            slip_hash=slip_hash,
            created_at=now,
            updated_at=now,
        )
        buy, sell = self.current_rates()
        tx.buy_rate = buy
        tx.sell_rate = sell
        return self.store.upsert(tx)

    def create_from_usdt(
        self,
        *,
        usdt: float,
        staff: str,
        staff_id: int | None,
        chat_id: int | None,
    ) -> Transaction:
        buy, sell = self.current_rates()
        quote = quote_from_usdt(usdt, buy, sell)
        now = iso()
        tx = Transaction(
            ledger_id=new_ledger_id(),
            status=STATUS_WAITING,
            staff=staff,
            staff_id=staff_id,
            chat_id=chat_id,
            created_at=now,
            updated_at=now,
        )
        apply_quote(tx, quote)
        return self.store.upsert(tx)

    def apply_ocr(self, tx: Transaction, ocr: OCRResult) -> Transaction:
        tx.receiver_name = ocr.receiver_name or tx.receiver_name
        tx.bank = ocr.bank or tx.bank
        tx.last4 = ocr.last4 or tx.last4
        tx.confidence = ocr.confidence
        tx.ocr_json = json.dumps(ocr.to_dict(), ensure_ascii=False)
        tx.status = STATUS_OCR if ocr.verified or ocr.amount_thb else STATUS_RECEIVED
        tx.updated_at = iso()

        buy, sell = self.current_rates()
        tx.buy_rate = buy
        tx.sell_rate = sell
        if ocr.amount_thb is not None:
            apply_quote(tx, quote_from_thb(ocr.amount_thb, buy, sell))
        return self.store.upsert(tx)

    def requote_thb(self, tx: Transaction, thb: float) -> Transaction:
        buy, sell = self.current_rates()
        apply_quote(tx, quote_from_thb(thb, buy, sell))
        tx.updated_at = iso()
        return self.store.upsert(tx)

    def requote_usdt(self, tx: Transaction, usdt: float) -> Transaction:
        buy, sell = self.current_rates()
        apply_quote(tx, quote_from_usdt(usdt, buy, sell))
        tx.updated_at = iso()
        return self.store.upsert(tx)

    def update_receiver(
        self,
        tx: Transaction,
        *,
        receiver_name: str | None = None,
        bank: str | None = None,
        last4: str | None = None,
    ) -> Transaction:
        if receiver_name is not None:
            tx.receiver_name = receiver_name
        if bank is not None:
            tx.bank = bank.upper()
        if last4 is not None:
            tx.last4 = last4[-4:]
        tx.updated_at = iso()
        return self.store.upsert(tx)

    def confirm(self, tx: Transaction) -> Transaction:
        tx.status = STATUS_WAITING
        tx.updated_at = iso()
        return self.store.upsert(tx)

    def settle(self, tx: Transaction) -> tuple[Transaction, float]:
        tx.status = STATUS_SETTLED
        tx.settled_at = iso()
        tx.updated_at = tx.settled_at
        self.store.upsert(tx)
        delta = float(tx.usdt or 0.0)
        balance = self.store.add_balance(delta)
        return tx, balance

    def void(self, tx: Transaction) -> Transaction:
        tx.status = "VOID"
        tx.updated_at = iso()
        return self.store.upsert(tx)

    def check_duplicate_slip(self, slip_hash: str) -> Transaction | None:
        return self.store.find_by_slip_hash(slip_hash)

    def repeated_receiver(self, bank: str, last4: str) -> int:
        if not bank or not last4:
            return 0
        return self.store.receiver_tx_count(bank, last4)

    def save_image(self, data: bytes, ledger_id: str, suffix: str = ".jpg") -> Path:
        self.settings.images_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.images_dir / f"{ledger_id}{suffix}"
        path.write_bytes(data)
        return path
