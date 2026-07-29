"""Ledger ID generation and transaction helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    STATUS_CANCELLED,
    STATUS_OCR_VERIFIED,
    STATUS_RECEIVED,
    STATUS_SETTLED,
    STATUS_WAITING_USDT,
)
from db.repository import Repository
from services.rates import calc_profit_pct, get_rates, thb_to_usdt


def generate_ledger_id() -> str:
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(2).upper()
    return f"LV-{date_part}-{suffix}"


def hash_slip(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_slip_image(data: bytes, ledger_id: str, slips_dir: Path) -> str:
    slips_dir.mkdir(parents=True, exist_ok=True)
    path = slips_dir / f"{ledger_id}.jpg"
    path.write_bytes(data)
    return str(path)


class LedgerService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def start_from_slip(
        self,
        staff_id: int,
        slip_data: bytes,
        image_path: str,
    ) -> dict[str, Any]:
        slip_hash = hash_slip(slip_data)
        existing = self.repo.find_by_slip_hash(slip_hash)
        if existing and existing["status"] != STATUS_CANCELLED:
            existing["_duplicate"] = True
            return existing

        ledger_id = generate_ledger_id()
        rates = get_rates(self.repo)
        return self.repo.create_transaction(
            ledger_id=ledger_id,
            staff_id=staff_id,
            status=STATUS_RECEIVED,
            slip_hash=slip_hash,
            buy_rate=rates.buy_rate,
            sell_rate=rates.sell_rate,
            image_path=image_path,
        )

    def start_from_usdt(self, staff_id: int, usdt: float) -> dict[str, Any]:
        pending = self.repo.get_pending_for_staff(staff_id)
        if pending:
            return self.apply_usdt(pending["id"], usdt)

        ledger_id = generate_ledger_id()
        rates = get_rates(self.repo)
        tx = self.repo.create_transaction(
            ledger_id=ledger_id,
            staff_id=staff_id,
            status=STATUS_WAITING_USDT,
            buy_rate=rates.buy_rate,
            sell_rate=rates.sell_rate,
        )
        return self.apply_usdt(tx["id"], usdt)

    def apply_ocr(
        self,
        ledger_id: str,
        ocr_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        tx = self.repo.get_transaction(ledger_id)
        if not tx:
            return None

        thb = ocr_result.get("amount")
        buy_rate = tx["buy_rate"]
        sell_rate = tx["sell_rate"]
        usdt = tx.get("usdt")

        if thb and not usdt:
            usdt = thb_to_usdt(float(thb), buy_rate)
        elif usdt and not thb:
            from services.rates import usdt_to_thb
            thb = usdt_to_thb(float(usdt), buy_rate)

        receiver_id = None
        bank = ocr_result.get("bank")
        last4 = ocr_result.get("last4")
        if bank and last4:
            receiver = self.repo.find_receiver(bank, last4)
            if receiver:
                ocr_result["_known_receiver"] = True
                ocr_result["_receiver_history"] = receiver

        profit = calc_profit_pct(buy_rate, sell_rate)
        status = STATUS_OCR_VERIFIED if ocr_result.get("confidence", 0) >= 90 else STATUS_RECEIVED

        if tx.get("usdt") and not thb:
            status = STATUS_WAITING_USDT
        elif usdt and thb:
            status = STATUS_OCR_VERIFIED

        return self.repo.update_transaction(
            ledger_id,
            thb=thb,
            usdt=usdt,
            ocr_confidence=ocr_result.get("confidence"),
            ocr_data=ocr_result,
            profit_pct=profit,
            status=status,
        )

    def apply_usdt(self, ledger_id: str, usdt: float) -> dict[str, Any] | None:
        tx = self.repo.get_transaction(ledger_id)
        if not tx:
            return None
        buy_rate = tx["buy_rate"]
        sell_rate = tx["sell_rate"]
        thb = tx.get("thb")
        if not thb:
            from services.rates import usdt_to_thb
            thb = usdt_to_thb(usdt, buy_rate)
        profit = calc_profit_pct(buy_rate, sell_rate)
        status = STATUS_OCR_VERIFIED if tx.get("ocr_data") else STATUS_WAITING_USDT
        if tx.get("ocr_data") and thb:
            status = STATUS_OCR_VERIFIED
        return self.repo.update_transaction(
            ledger_id,
            usdt=round(usdt, 4),
            thb=thb,
            profit_pct=profit,
            status=status,
        )

    def settle(self, ledger_id: str) -> dict[str, Any] | None:
        tx = self.repo.get_transaction(ledger_id)
        if not tx:
            return None
        if not tx.get("thb") or not tx.get("usdt"):
            return None

        ocr = tx.get("ocr_data") or {}
        receiver_id = None
        bank = ocr.get("bank")
        last4 = ocr.get("last4")
        name = ocr.get("receiver_name")
        if bank and last4:
            receiver = self.repo.upsert_receiver(
                bank=bank,
                last4=last4,
                name=name,
                thb=float(tx["thb"]),
                usdt=float(tx["usdt"]),
            )
            receiver_id = receiver["id"]

        profit = tx.get("profit_pct") or calc_profit_pct(tx["buy_rate"], tx["sell_rate"])
        updated = self.repo.update_transaction(
            ledger_id,
            status=STATUS_SETTLED,
            receiver_id=receiver_id,
            profit_pct=profit,
        )
        if updated:
            new_balance = self.repo.adjust_balance(tx["staff_id"], -float(tx["usdt"]))
            updated["_new_balance"] = new_balance
        return updated

    def cancel(self, ledger_id: str) -> dict[str, Any] | None:
        return self.repo.update_transaction(ledger_id, status=STATUS_CANCELLED)

    def get_receiver_history(self, bank: str, last4: str) -> dict[str, Any] | None:
        return self.repo.find_receiver(bank, last4)

    def assess_risk(self, receiver: dict[str, Any]) -> str:
        count = receiver.get("tx_count", 0)
        if count >= 50:
            return "LOW"
        if count >= 10:
            return "MEDIUM"
        return "HIGH"
