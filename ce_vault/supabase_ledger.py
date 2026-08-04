"""Supabase-backed ledger — maps CE VAULT cards onto the existing Bot-telegram schema.

Canonical row shape returned to the bot matches the SQLite ledger:
  id, status, slip_file_id, slip_hash, ocr_confidence, receiver_name, bank, last4,
  thb, usdt, buy_rate, sell_rate, profit_pct, staff_id, staff_name, chat_id, ...

DB statuses: ocr_success | waiting_admin | completed | cancelled
UI statuses: RECEIVED | OCR VERIFIED | WAITING USDT | SETTLED | CANCELLED
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ce_vault.formatting import ledger_id as make_ledger_id
from ce_vault.theme import RECEIVER_REPEAT_HOURS, Status

logger = logging.getLogger("ce_vault.supabase")

STATUS_TO_DB = {
    Status.RECEIVED.value: "ocr_success",
    Status.OCR_VERIFIED.value: "ocr_success",
    Status.WAITING_USDT.value: "waiting_admin",
    Status.SETTLED.value: "completed",
    Status.CANCELLED.value: "cancelled",
    Status.ERROR.value: "cancelled",
    Status.EDITING.value: "waiting_admin",
    # passthrough if already DB values
    "ocr_success": "ocr_success",
    "waiting_admin": "waiting_admin",
    "completed": "completed",
    "cancelled": "cancelled",
}

STATUS_TO_UI = {
    "ocr_success": Status.OCR_VERIFIED.value,
    "waiting_admin": Status.WAITING_USDT.value,
    "completed": Status.SETTLED.value,
    "cancelled": Status.CANCELLED.value,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _account_hash(bank: str | None, last4: str | None) -> str | None:
    if not bank or not last4:
        return None
    raw = f"{bank.upper().strip()}:{(last4 or '')[-4:]}"
    return hashlib.sha256(raw.encode()).hexdigest()


class SupabaseLedger:
    """PostgREST client using the service role key (server-side only)."""

    def __init__(self, url: str, service_key: str, timeout: float = 30.0):
        self.base = url.rstrip("/") + "/rest/v1"
        self._client = httpx.Client(
            base_url=self.base,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase {resp.status_code}: {resp.text[:400]}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- mapping ---------------------------------------------------------

    @staticmethod
    def _to_ui(row: dict | None) -> dict | None:
        if not row:
            return None
        status_db = row.get("status") or "ocr_success"
        return {
            "id": row.get("ledger_ref") or row.get("id"),
            "uuid": row.get("id"),
            "status": STATUS_TO_UI.get(status_db, Status.RECEIVED.value),
            "status_db": status_db,
            "slip_file_id": row.get("slip_image_url"),
            "slip_url": row.get("slip_image_url"),
            "slip_hash": row.get("slip_hash"),
            "ocr_confidence": _num(row.get("ocr_confidence")),
            "receiver_name": row.get("receiver_name"),
            "bank": row.get("receiver_bank"),
            "last4": row.get("receiver_last4"),
            "thb": _num(row.get("thb_amount")),
            "usdt": _num(row.get("usdt_amount")),
            "buy_rate": _num(row.get("buy_rate")),
            "sell_rate": _num(row.get("sell_rate")),
            "profit_pct": _num(row.get("profit_percent")),
            "staff_id": None,
            "staff_name": None,
            "admin_id": row.get("admin_id"),
            "chat_id": row.get("chat_id"),
            "message_id": None,
            "notes": row.get("note"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "settled_at": row.get("updated_at") if status_db == "completed" else None,
        }

    # --- rates / balance -------------------------------------------------

    def get_rates(self) -> tuple[float, float]:
        rows = self._request(
            "GET",
            "/rates",
            params={"select": "sell_rate,market_usdt_rate", "order": "created_at.desc", "limit": "1"},
        )
        if not rows:
            return 39.89, 40.0
        buy = float(rows[0]["market_usdt_rate"] or 0)
        sell = float(rows[0]["sell_rate"] or 0)
        if buy <= 0:
            buy = 39.89
        if sell <= 0:
            sell = 40.0
        return buy, sell

    def set_rates(self, buy: float, sell: float, updated_by: int | None = None) -> None:
        admin_id = self._resolve_admin_id(updated_by, name=None) if updated_by else None
        self._request(
            "POST",
            "/rates",
            json={
                "sell_rate": sell,
                "market_usdt_rate": buy,
                "set_by_admin_id": admin_id,
            },
        )

    def get_balance(self) -> float:
        # Sum admin holdings as USDT float
        rows = self._request("GET", "/admins", params={"select": "holding_usdt"})
        return round(sum(float(r.get("holding_usdt") or 0) for r in (rows or [])), 4)

    def set_balance(self, value: float) -> None:
        # Park global float on first admin row (ops desk default)
        rows = self._request(
            "GET", "/admins", params={"select": "id", "order": "created_at.asc", "limit": "1"}
        )
        if not rows:
            raise RuntimeError("No admins row to store USDT balance")
        self._request(
            "PATCH",
            "/admins",
            params={"id": f"eq.{rows[0]['id']}"},
            json={"holding_usdt": value, "updated_at": _utcnow()},
        )

    def adjust_balance(self, delta: float) -> float:
        current = self.get_balance()
        new = round(current + delta, 4)
        self.set_balance(new)
        return new

    # --- admins ----------------------------------------------------------

    def _resolve_admin_id(self, telegram_user_id: int | None, name: str | None) -> str:
        if telegram_user_id:
            rows = self._request(
                "GET",
                "/admins",
                params={
                    "select": "id",
                    "telegram_user_id": f"eq.{telegram_user_id}",
                    "limit": "1",
                },
            )
            if rows:
                return rows[0]["id"]
            created = self._request(
                "POST",
                "/admins",
                json={
                    "name": name or f"Staff {telegram_user_id}",
                    "telegram_user_id": telegram_user_id,
                    "holding_usdt": 0,
                },
            )
            return created[0]["id"]
        rows = self._request(
            "GET", "/admins", params={"select": "id", "order": "created_at.asc", "limit": "1"}
        )
        if not rows:
            created = self._request(
                "POST",
                "/admins",
                json={"name": "CE VAULT Desk", "telegram_user_id": 0, "holding_usdt": 0},
            )
            return created[0]["id"]
        return rows[0]["id"]

    def list_admin_telegram_ids(self) -> set[int]:
        rows = self._request("GET", "/admins", params={"select": "telegram_user_id"})
        return {int(r["telegram_user_id"]) for r in (rows or []) if r.get("telegram_user_id") is not None}

    # --- ledger ids ------------------------------------------------------

    def next_ledger_id(self) -> str:
        """Random ``CE-YYYYMMDD-XXXX`` — see Ledger.next_ledger_id notes."""
        return make_ledger_id()

    def _lookup_uuid(self, entry_id: str) -> str | None:
        """Accept either ledger_ref (CE-… or legacy LV-…) or raw UUID."""
        if len(entry_id) == 36 and entry_id.count("-") == 4:
            return entry_id
        rows = self._request(
            "GET",
            "/transactions",
            params={"select": "id", "ledger_ref": f"eq.{entry_id}", "limit": "1"},
        )
        return rows[0]["id"] if rows else None

    # --- CRUD ------------------------------------------------------------

    def create_entry(self, **fields: Any) -> dict:
        ledger_ref = fields.get("id") or self.next_ledger_id()
        admin_id = self._resolve_admin_id(fields.get("staff_id"), fields.get("staff_name"))
        status_ui = fields.get("status", Status.RECEIVED.value)
        status_db = STATUS_TO_DB.get(status_ui, "ocr_success")

        thb = fields.get("thb") or 0
        usdt = fields.get("usdt") or 0
        buy = fields.get("buy_rate") or 0
        sell = fields.get("sell_rate") or 0
        profit = fields.get("profit_pct") or 0

        payload = {
            "admin_id": admin_id,
            "type": "THB_DEPOSIT",
            "thb_amount": thb,
            "usdt_amount": usdt,
            "expected_usdt": usdt,
            "sell_rate": sell,
            "buy_rate": buy,
            "cost_per_unit": buy,
            "sell_value_thb": thb,
            "net_profit_thb": round(float(thb) * float(profit) / 100.0, 2) if profit else 0,
            "profit_percent": profit,
            # Prefer the durable Storage URL; the Telegram file_id is only a
            # handle into Telegram's cache and cannot be fetched by anything
            # other than this bot.
            "slip_image_url": fields.get("slip_url") or fields.get("slip_file_id"),
            "slip_hash": fields.get("slip_hash"),
            "ocr_confidence": fields.get("ocr_confidence"),
            "receiver_name": fields.get("receiver_name"),
            "receiver_bank": fields.get("bank"),
            "receiver_last4": fields.get("last4"),
            "ledger_ref": ledger_ref,
            "chat_id": fields.get("chat_id"),
            "note": fields.get("notes"),
            "status": status_db,
        }
        rows = self._request("POST", "/transactions", json=payload)
        return self._to_ui(rows[0])  # type: ignore[index]

    def get(self, entry_id: str) -> dict | None:
        if len(entry_id) == 36 and entry_id.count("-") == 4:
            rows = self._request(
                "GET",
                "/transactions",
                params={"select": "*", "id": f"eq.{entry_id}", "limit": "1"},
            )
            return self._to_ui(rows[0]) if rows else None
        rows = self._request(
            "GET",
            "/transactions",
            params={"select": "*", "ledger_ref": f"eq.{entry_id}", "limit": "1"},
        )
        return self._to_ui(rows[0]) if rows else None

    def update(self, entry_id: str, **fields: Any) -> dict | None:
        uuid = self._lookup_uuid(entry_id)
        if not uuid:
            return None
        patch: dict[str, Any] = {"updated_at": _utcnow()}
        if "status" in fields:
            patch["status"] = STATUS_TO_DB.get(fields["status"], fields["status"])
        if "thb" in fields:
            patch["thb_amount"] = fields["thb"]
            patch["sell_value_thb"] = fields["thb"]
        if "usdt" in fields:
            patch["usdt_amount"] = fields["usdt"]
            patch["expected_usdt"] = fields["usdt"]
        if "buy_rate" in fields:
            patch["buy_rate"] = fields["buy_rate"]
            patch["cost_per_unit"] = fields["buy_rate"]
        if "sell_rate" in fields:
            patch["sell_rate"] = fields["sell_rate"]
        if "profit_pct" in fields:
            patch["profit_percent"] = fields["profit_pct"]
            thb = fields.get("thb")
            if thb is None:
                current = self.get(entry_id)
                thb = (current or {}).get("thb") or 0
            patch["net_profit_thb"] = round(float(thb) * float(fields["profit_pct"]) / 100.0, 2)
        if "receiver_name" in fields:
            patch["receiver_name"] = fields["receiver_name"]
        if "bank" in fields:
            patch["receiver_bank"] = fields["bank"]
        if "last4" in fields:
            patch["receiver_last4"] = fields["last4"]
        if "slip_url" in fields or "slip_file_id" in fields:
            patch["slip_image_url"] = fields.get("slip_url") or fields.get("slip_file_id")
        if "slip_hash" in fields:
            patch["slip_hash"] = fields["slip_hash"]
        if "ocr_confidence" in fields:
            patch["ocr_confidence"] = fields["ocr_confidence"]
        if "notes" in fields:
            patch["note"] = fields["notes"]
        rows = self._request(
            "PATCH", "/transactions", params={"id": f"eq.{uuid}"}, json=patch
        )
        return self._to_ui(rows[0]) if rows else self.get(entry_id)

    def delete(self, entry_id: str) -> bool:
        uuid = self._lookup_uuid(entry_id)
        if not uuid:
            return False
        self._request("DELETE", "/transactions", params={"id": f"eq.{uuid}"})
        return True

    def list_recent(self, limit: int = 10) -> list[dict]:
        rows = self._request(
            "GET",
            "/transactions",
            params={
                "select": "*",
                "order": "created_at.desc",
                "limit": str(limit),
                "status": "neq.cancelled",
            },
        )
        return [self._to_ui(r) for r in (rows or []) if r]  # type: ignore[misc]

    def find_by_slip_hash(self, slip_hash: str) -> dict | None:
        if not slip_hash:
            return None
        rows = self._request(
            "GET",
            "/transactions",
            params={
                "select": "*",
                "slip_hash": f"eq.{slip_hash}",
                "status": "neq.cancelled",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        return self._to_ui(rows[0]) if rows else None

    # --- receivers -------------------------------------------------------

    def receiver_history(self, bank: str | None, last4: str | None) -> dict | None:
        key = _account_hash(bank, last4)
        if not key:
            return None
        rows = self._request(
            "GET",
            "/receivers",
            params={"select": "*", "account_hash": f"eq.{key}", "limit": "1"},
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "bank": r.get("bank") or bank,
            "last4": r.get("account_last4") or last4,
            "name": r.get("receiver_name"),
            "tx_count": int(r.get("total_transactions") or 0),
            "total_thb": float(r.get("total_amount_thb") or 0),
            "total_usdt": float(r.get("total_usdt") or 0),
            "first_seen": r.get("first_transaction_at"),
            "last_seen": r.get("last_transaction_at"),
            "risk": "HIGH"
            if int(r.get("total_transactions") or 0) >= 50
            else ("MED" if int(r.get("total_transactions") or 0) >= 20 else "LOW"),
        }

    def is_repeat_receiver(
        self, bank: str | None, last4: str | None, hours: int = RECEIVER_REPEAT_HOURS
    ) -> bool:
        if not bank or not last4:
            return False
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self._request(
            "GET",
            "/transactions",
            params={
                "select": "id",
                "receiver_bank": f"eq.{bank}",
                "receiver_last4": f"eq.{last4}",
                "created_at": f"gte.{cutoff}",
                "status": "neq.cancelled",
                "limit": "1",
            },
        )
        return bool(rows)

    def record_settlement(self, entry_id: str) -> dict | None:
        entry = self.get(entry_id)
        if not entry:
            return None
        uuid = entry.get("uuid") or self._lookup_uuid(entry_id)
        if not uuid:
            return None

        now = _utcnow()
        usdt = float(entry.get("usdt") or 0)
        thb = float(entry.get("thb") or 0)
        bank = entry.get("bank")
        last4 = entry.get("last4")
        name = entry.get("receiver_name")
        ledger_ref = entry.get("id")

        rows = self._request(
            "PATCH",
            "/transactions",
            params={"id": f"eq.{uuid}"},
            json={"status": "completed", "updated_at": now},
        )

        # Debit admin holding
        if entry.get("admin_id"):
            admin = self._request(
                "GET",
                "/admins",
                params={"select": "id,holding_usdt", "id": f"eq.{entry['admin_id']}", "limit": "1"},
            )
            if admin:
                holding = float(admin[0].get("holding_usdt") or 0) - usdt
                self._request(
                    "PATCH",
                    "/admins",
                    params={"id": f"eq.{admin[0]['id']}"},
                    json={"holding_usdt": round(holding, 4), "updated_at": now},
                )

        # Upsert receiver dossier
        key = _account_hash(bank, last4)
        if key and bank and last4:
            existing = self._request(
                "GET",
                "/receivers",
                params={"select": "*", "account_hash": f"eq.{key}", "limit": "1"},
            )
            if existing:
                r = existing[0]
                self._request(
                    "PATCH",
                    "/receivers",
                    params={"id": f"eq.{r['id']}"},
                    json={
                        "receiver_name": name or r.get("receiver_name"),
                        "total_transactions": int(r.get("total_transactions") or 0) + 1,
                        "total_amount_thb": float(r.get("total_amount_thb") or 0) + thb,
                        "total_usdt": float(r.get("total_usdt") or 0) + usdt,
                        "max_amount_thb": max(float(r.get("max_amount_thb") or 0), thb),
                        "last_amount_thb": thb,
                        "last_transaction_at": now,
                        "last_ledger_ref": ledger_ref,
                    },
                )
                receiver_id = r["id"]
            else:
                created = self._request(
                    "POST",
                    "/receivers",
                    json={
                        "account_hash": key,
                        "bank": bank,
                        "receiver_name": name,
                        "account_last4": last4,
                        "total_transactions": 1,
                        "total_amount_thb": thb,
                        "total_usdt": usdt,
                        "max_amount_thb": thb,
                        "last_amount_thb": thb,
                        "first_transaction_at": now,
                        "last_transaction_at": now,
                        "last_ledger_ref": ledger_ref,
                        "status": "normal",
                    },
                )
                receiver_id = created[0]["id"]
            self._request(
                "PATCH",
                "/transactions",
                params={"id": f"eq.{uuid}"},
                json={"receiver_id": receiver_id},
            )

        return self._to_ui(rows[0]) if rows else self.get(entry_id)

    # --- dashboard -------------------------------------------------------

    def today_summary(self) -> dict:
        start, end = _day_bounds_utc()
        rows = self._request(
            "GET",
            "/transactions",
            params={
                "select": "status,thb_amount,usdt_amount,net_profit_thb,profit_percent,ocr_confidence",
                "created_at": f"gte.{start}",
                "and": f"(created_at.lt.{end})",
            },
        ) or []
        counts = {
            "tx_count": 0,
            "cancelled": 0,
            "pending": 0,
            "settled": 0,
            "thb": 0.0,
            "usdt": 0.0,
            "profit_thb": 0.0,
            "ocr_accuracy": None,
        }
        conf_sum = 0.0
        conf_n = 0
        for row in rows:
            status_db = row.get("status") or ""
            if status_db == "cancelled":
                counts["cancelled"] += 1
                continue
            counts["tx_count"] += 1
            thb = float(row.get("thb_amount") or 0)
            usdt = float(row.get("usdt_amount") or 0)
            profit_thb = row.get("net_profit_thb")
            if profit_thb is None:
                # Fall back to percent-derived profit for rows written before
                # net_profit_thb was populated.
                pct = float(row.get("profit_percent") or 0)
                profit_thb = round(thb * pct / 100.0, 2)
            counts["thb"] += thb
            counts["usdt"] += usdt
            counts["profit_thb"] += float(profit_thb)
            if status_db == "completed":
                counts["settled"] += 1
            else:
                counts["pending"] += 1
            if row.get("ocr_confidence") is not None:
                conf_sum += float(row["ocr_confidence"])
                conf_n += 1
        counts["thb"] = round(counts["thb"], 2)
        counts["usdt"] = round(counts["usdt"], 4)
        counts["profit_thb"] = round(counts["profit_thb"], 2)
        if conf_n:
            counts["ocr_accuracy"] = round(conf_sum / conf_n, 2)
        return counts

    def today_by_staff(self) -> list[dict]:
        """Per-admin totals for today.

        The Supabase schema tracks the operator as ``admin_id``; there is no
        Telegram-side ``staff_id`` field on transactions (see _to_ui — it's
        always None), so we aggregate by admin_id and hydrate the display
        name from /admins.
        """
        start, end = _day_bounds_utc()
        rows = self._request(
            "GET",
            "/transactions",
            params={
                "select": "admin_id,thb_amount,usdt_amount,net_profit_thb,profit_percent,status",
                "created_at": f"gte.{start}",
                "and": f"(created_at.lt.{end},status.neq.cancelled)",
            },
        ) or []
        agg: dict[str, dict] = {}
        for row in rows:
            admin_id = row.get("admin_id") or "—"
            bucket = agg.setdefault(
                admin_id,
                {"admin_id": admin_id, "tx_count": 0, "thb": 0.0, "usdt": 0.0, "profit_thb": 0.0},
            )
            bucket["tx_count"] += 1
            thb = float(row.get("thb_amount") or 0)
            usdt = float(row.get("usdt_amount") or 0)
            profit_thb = row.get("net_profit_thb")
            if profit_thb is None:
                pct = float(row.get("profit_percent") or 0)
                profit_thb = round(thb * pct / 100.0, 2)
            bucket["thb"] += thb
            bucket["usdt"] += usdt
            bucket["profit_thb"] += float(profit_thb)

        # Hydrate names in a single query
        ids = [a for a in agg if a and a != "—"]
        names: dict[str, str] = {}
        if ids:
            admins = self._request(
                "GET",
                "/admins",
                params={
                    "select": "id,telegram_username,telegram_first_name",
                    "id": f"in.({','.join(ids)})",
                },
            ) or []
            for a in admins:
                names[str(a["id"])] = (
                    a.get("telegram_username")
                    or a.get("telegram_first_name")
                    or str(a["id"])[:8]
                )

        out = []
        for admin_id, bucket in agg.items():
            out.append(
                {
                    "staff_id": admin_id,
                    "staff_name": names.get(str(admin_id), "—" if admin_id == "—" else str(admin_id)[:8]),
                    "tx_count": bucket["tx_count"],
                    "thb": round(bucket["thb"], 2),
                    "usdt": round(bucket["usdt"], 4),
                    "profit_thb": round(bucket["profit_thb"], 2),
                }
            )
        out.sort(key=lambda b: b["tx_count"], reverse=True)
        return out


def _day_bounds_utc(now: datetime | None = None) -> tuple[str, str]:
    """Same shape as ledger._day_bounds_utc — duplicated here to keep the
    Supabase module self-contained (avoid a cross-module import of a private)."""
    import os

    tz_name = os.environ.get("TIMEZONE", "Asia/Bangkok")
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = now or datetime.now(tz)
    local = now.astimezone(tz)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
