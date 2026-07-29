"""OCR pipeline for Thai bank transfer slips.

Supports:
  1. Structured caption / text paste (fast path for ops)
  2. Heuristic extraction from free text
  3. Optional Vision API when OPENAI_API_KEY is set

Never blocks the console — low confidence surfaces a warning card.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import httpx

from vault.models import OCRResult

CONFIDENCE_WARN = 90.0

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
    "กรุงไทย": "KTB",
    "bay": "BAY",
    "กรุงศรี": "BAY",
    "ttb": "TTB",
    "tmb": "TTB",
    "ออมสิน": "GSB",
    "gsb": "GSB",
}

AMOUNT_RE = re.compile(
    r"(?:amount|thb|บาท|จำนวน|detected\s*amount)[^\d]{0,12}"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.I,
)
AMOUNT_BARE_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})\b")
LAST4_RE = re.compile(
    r"(?:last\s*4|last4|x{2,}|•{2,}|\*{2,}|\.{2,}|xxxx)?\s*(\d{4})\b", re.I
)
RECEIVER_RE = re.compile(
    r"(?:receiver|to|ชื่อ|ผู้รับ|นาย|นาง|น\.ส\.|นส\.)[^\n]{0,40}", re.I
)
BANK_RE = re.compile(
    r"\b(SCB|KBANK|BBL|KTB|BAY|TTB|GSB|KASIKORN|SIAM)\b", re.I
)


def slip_hash_from_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slip_hash_from_file_id(file_id: str) -> str:
    return hashlib.sha256(file_id.encode()).hexdigest()


def _parse_amount(text: str) -> float | None:
    m = AMOUNT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    m = AMOUNT_BARE_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _parse_bank(text: str) -> str | None:
    m = BANK_RE.search(text)
    if m:
        token = m.group(1).upper()
        if token == "KASIKORN":
            return "KBANK"
        if token == "SIAM":
            return "SCB"
        return token
    lower = text.lower()
    for alias, code in BANK_ALIASES.items():
        if alias in lower:
            return code
    return None


def _parse_last4(text: str) -> str | None:
    # Prefer explicit masked forms
    masked = re.search(r"(?:x{2,}|\*{2,}|•{2,}|\.{4})\s*(\d{4})", text, re.I)
    if masked:
        return masked.group(1)
    m = LAST4_RE.findall(text)
    if m:
        return m[-1]
    return None


def _parse_receiver(text: str) -> str | None:
    # Thai honorific lines
    thai = re.search(r"((?:นาย|นาง|น\.ส\.|นส\.|คุณ)\s*[^\n\d]{2,40})", text)
    if thai:
        return thai.group(1).strip()[:48]
    for line in text.splitlines():
        if re.search(r"receiver|ผู้รับ|ชื่อ", line, re.I):
            cleaned = re.sub(r"(?i)receiver|ผู้รับ|ชื่อ\s*:?", "", line).strip(" :-\t")
            if cleaned:
                return cleaned[:48]
    return None


def parse_slip_text(text: str, *, base_confidence: float = 92.0) -> OCRResult:
    """Heuristic OCR from pasted / caption text."""
    text = (text or "").strip()
    if not text:
        return OCRResult(confidence=0.0, status="Unreadable")

    amount = _parse_amount(text)
    bank = _parse_bank(text)
    last4 = _parse_last4(text)
    receiver = _parse_receiver(text)

    hits = sum(x is not None for x in (amount, bank, last4, receiver))
    confidence = round(min(99.5, base_confidence - (4 - hits) * 8 + hits * 1.5), 1)
    if hits == 0:
        confidence = 12.0
        status = "Failed"
    elif confidence < CONFIDENCE_WARN:
        status = "Review"
    else:
        status = "Verified"

    return OCRResult(
        receiver=receiver,
        bank=bank,
        last4=last4,
        amount_thb=amount,
        confidence=confidence,
        raw_text=text[:2000],
        status=status,
    )


async def vision_ocr(image_bytes: bytes, caption: str = "") -> OCRResult:
    """Optional OpenAI Vision extraction. Falls back to caption heuristics."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return parse_slip_text(caption, base_confidence=88.0 if caption else 40.0)

    import base64

    b64 = base64.b64encode(image_bytes).decode()
    prompt = (
        "Extract Thai bank transfer slip fields as JSON only with keys: "
        "receiver, bank (SCB|KBANK|BBL|KTB|BAY|TTB|GSB), last4, amount_thb, confidence (0-100). "
        "No prose."
    )
    body = {
        "model": os.environ.get("OCR_MODEL", "gpt-4o-mini"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 300,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)
        result = OCRResult(
            receiver=data.get("receiver"),
            bank=data.get("bank"),
            last4=str(data.get("last4") or "")[-4:] or None,
            amount_thb=float(data["amount_thb"]) if data.get("amount_thb") is not None else None,
            confidence=float(data.get("confidence") or 95.0),
            raw_text=content[:2000],
            status="Verified" if float(data.get("confidence") or 95) >= CONFIDENCE_WARN else "Review",
        )
        # Merge caption hints if vision missed fields
        if caption:
            hint = parse_slip_text(caption)
            result.receiver = result.receiver or hint.receiver
            result.bank = result.bank or hint.bank
            result.last4 = result.last4 or hint.last4
            result.amount_thb = result.amount_thb if result.amount_thb is not None else hint.amount_thb
        return result
    except Exception:
        return parse_slip_text(caption, base_confidence=70.0)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


async def process_slip(
    *,
    image_bytes: bytes | None = None,
    caption: str = "",
    file_id: str | None = None,
) -> tuple[OCRResult, str]:
    """Run OCR and return (result, slip_hash)."""
    if image_bytes:
        digest = slip_hash_from_bytes(image_bytes)
        result = await vision_ocr(image_bytes, caption=caption)
    else:
        digest = slip_hash_from_file_id(file_id or caption or "empty")
        result = parse_slip_text(caption)
    return result, digest
