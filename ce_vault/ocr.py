"""OCR pipeline for Thai payment slips.

Uses OpenAI Vision when OPENAI_API_KEY is set; otherwise parses structured
caption/text fallback so the desk can still operate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger("ce_vault.ocr")

BANK_ALIASES = {
    "scb": "SCB",
    "siam commercial": "SCB",
    "กสิกร": "KBANK",
    "kbank": "KBANK",
    "kasikorn": "KBANK",
    "bbl": "BBL",
    "bangkok bank": "BBL",
    "กรุงเทพ": "BBL",
    "ktb": "KTB",
    "krungthai": "KTB",
    "กรุงไทย": "KTB",
    "bay": "BAY",
    "krungsri": "BAY",
    "กรุงศรี": "BAY",
    "ttb": "TTB",
    "tmb": "TTB",
    "กสิกรไทย": "KBANK",
    "ไทยพาณิชย์": "SCB",
}


@dataclass
class OcrResult:
    receiver_name: str | None
    bank: str | None
    last4: str | None
    amount_thb: Decimal | None
    confidence: float
    raw_text: str = ""
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.amount_thb is not None:
            data["amount_thb"] = str(self.amount_thb)
        return data


def slip_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def normalize_bank(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower().strip()
    for needle, code in BANK_ALIASES.items():
        if needle in low:
            return code
    # already a short code
    compact = re.sub(r"[^A-Za-z]", "", text).upper()
    if 2 <= len(compact) <= 5:
        return compact
    return text.strip().upper()[:12]


def parse_amount(text: str) -> Decimal | None:
    # Prefer amounts near THB / บาท keywords
    patterns = [
        r"(?:THB|บาท|Amount|จำนวน)[^\d]{0,12}(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
        r"(\d{1,3}(?:,\d{3})+\.\d{2})",
        r"(\d+\.\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return Decimal(m.group(1).replace(",", ""))
            except InvalidOperation:
                continue
    return None


def parse_last4(text: str) -> str | None:
    patterns = [
        r"(?:\*{2,}|\…|\.{3,}|x{2,}|X{2,}|•{2,}|●{2,})[^\d]*(\d{4})",
        r"(?:เลขที่บัญชี|บัญชี|account)[^\d]*(\d{4})\b",
        r"(?:ending|last\s*4)[^\d]*(\d{4})",
        r"(\d{3}-\d{1}-\d{5}-\d)",  # SCB style → take last4 of digits
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            if len(digits) >= 4:
                return digits[-4:]
    # fallback: any xxx-xxx-xxxx style Thai account
    m = re.search(r"\b\d{3}-?\d{1}-?\d{5}-?\d\b", text)
    if m:
        return re.sub(r"\D", "", m.group(0))[-4:]
    return None


def parse_receiver(text: str) -> str | None:
    patterns = [
        r"(?:ชื่อบัญชี|ผู้รับ|To|Receiver|Account name)\s*[:：]?\s*([^\n]+)",
        r"(นาย|นาง|นางสาว|Mr\.|Ms\.|Mrs\.)\s*([^\n,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            if m.lastindex == 2:
                return f"{m.group(1)}{m.group(2)}".strip()[:80]
            return m.group(1).strip()[:80]
    return None


def parse_bank(text: str) -> str | None:
    return normalize_bank(text)


def heuristic_ocr(text: str) -> OcrResult:
    amount = parse_amount(text)
    last4 = parse_last4(text)
    receiver = parse_receiver(text)
    bank = parse_bank(text)

    hits = sum(1 for x in (amount, last4, receiver, bank) if x)
    confidence = {0: 20.0, 1: 55.0, 2: 78.0, 3: 91.0, 4: 98.4}[hits]

    return OcrResult(
        receiver_name=receiver,
        bank=bank,
        last4=last4,
        amount_thb=amount,
        confidence=confidence,
        raw_text=text,
        source="heuristic",
    )


async def vision_ocr(
    *,
    image_bytes: bytes,
    api_key: str,
    model: str = "gpt-4o-mini",
    mime: str = "image/jpeg",
) -> OcrResult:
    import base64

    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Extract Thai bank transfer slip fields as strict JSON with keys: "
        "receiver_name (string), bank (short code e.g. SCB/KBANK/BBL/KTB/BAY/TTB), "
        "last4 (4 digits), amount_thb (number), confidence (0-100). "
        "No markdown."
    )
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 300,
        "temperature": 0,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    data = _extract_json(content)
    amount = data.get("amount_thb")
    try:
        amount_d = Decimal(str(amount)) if amount is not None else None
    except InvalidOperation:
        amount_d = None

    conf = float(data.get("confidence") or 90.0)
    return OcrResult(
        receiver_name=(data.get("receiver_name") or None),
        bank=normalize_bank(data.get("bank")),
        last4=str(data.get("last4") or "")[-4:] or None,
        amount_thb=amount_d,
        confidence=conf,
        raw_text=content,
        source="vision",
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


async def run_ocr(
    *,
    image_bytes: bytes | None = None,
    caption: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    mime: str = "image/jpeg",
) -> OcrResult:
    if image_bytes and api_key:
        try:
            return await vision_ocr(image_bytes=image_bytes, api_key=api_key, model=model, mime=mime)
        except Exception:
            logger.exception("vision OCR failed — falling back to heuristic")

    text = (caption or "").strip()
    if not text and image_bytes:
        # No vision key: staff must supply structured caption; return low-confidence stub
        return OcrResult(
            receiver_name=None,
            bank=None,
            last4=None,
            amount_thb=None,
            confidence=35.0,
            raw_text="",
            source="pending",
        )
    return heuristic_ocr(text)
