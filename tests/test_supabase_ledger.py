"""Supabase ledger mapping tests (httpx MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from vault.supabase_ledger import STATUS_TO_DB, STATUS_TO_UI, SupabaseLedger
from vault.theme import Status


def make_store(handler) -> SupabaseLedger:
    store = SupabaseLedger("https://example.supabase.co", "service-key")
    store._client = httpx.Client(
        base_url="https://example.supabase.co/rest/v1",
        headers={
            "apikey": "service-key",
            "Authorization": "Bearer service-key",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        transport=httpx.MockTransport(handler),
    )
    return store


def test_status_mapping_roundtrip():
    assert STATUS_TO_DB[Status.WAITING_USDT.value] == "waiting_admin"
    assert STATUS_TO_UI["completed"] == Status.SETTLED.value
    assert STATUS_TO_DB[Status.CANCELLED.value] == "cancelled"


def test_get_rates_uses_market_as_buy():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rates")
        return httpx.Response(
            200,
            json=[{"sell_rate": "37.5", "market_usdt_rate": "33.54"}],
        )

    store = make_store(handler)
    buy, sell = store.get_rates()
    store.close()
    assert buy == 33.54
    assert sell == 37.5


def test_create_entry_payload_and_ui_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/admins") and request.method == "GET":
            return httpx.Response(
                200, json=[{"id": "admin-1", "telegram_user_id": 1}]
            )
        if path.endswith("/transactions") and request.method == "GET":
            # next_ledger_id lookup
            return httpx.Response(200, json=[])
        if path.endswith("/transactions") and request.method == "POST":
            captured["body"] = json.loads(request.content)
            body = dict(captured["body"])
            body["id"] = "11111111-1111-1111-1111-111111111111"
            body["created_at"] = "2026-07-29T00:00:00+00:00"
            body["updated_at"] = body["created_at"]
            return httpx.Response(201, json=[body])
        return httpx.Response(500, text=f"unexpected {request.method} {path}")

    store = make_store(handler)
    entry = store.create_entry(
        status=Status.OCR_VERIFIED.value,
        thb=500,
        usdt=12.5,
        buy_rate=33.54,
        sell_rate=37.5,
        profit_pct=11.81,
        bank="SCB",
        last4="3376",
        staff_id=1,
        staff_name="Desk",
        slip_hash="abc",
        ocr_confidence=98.4,
    )
    store.close()

    assert captured["body"]["type"] == "THB_DEPOSIT"
    assert captured["body"]["status"] == "ocr_success"
    assert captured["body"]["receiver_bank"] == "SCB"
    assert captured["body"]["ledger_ref"].startswith("LV-")
    assert entry["bank"] == "SCB"
    assert entry["status"] == Status.OCR_VERIFIED.value
    assert entry["thb"] == 500.0


def test_find_by_slip_hash():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "slip_hash" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "ledger_ref": "LV-20260729-0002",
                    "status": "waiting_admin",
                    "thb_amount": 100,
                    "usdt_amount": 2.5,
                    "sell_rate": 40,
                    "buy_rate": 39,
                    "profit_percent": 2.5,
                    "receiver_bank": "SCB",
                    "receiver_last4": "3376",
                    "slip_hash": "dup",
                }
            ],
        )

    store = make_store(handler)
    found = store.find_by_slip_hash("dup")
    store.close()
    assert found is not None
    assert found["id"] == "LV-20260729-0002"
    assert found["status"] == Status.WAITING_USDT.value
