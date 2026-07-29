"""OCR engine for Thai bank transfer slips.

Supports:
- Caption / text slip parsing (always on)
- Optional Vision API when OPENAI_API_KEY is set
- Image perceptual hash for duplicate detection
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ce_vault.theme import CONFIDENCE_WARN_THRESHOLD, to_decimal

BANK_ALIASES = {
    "SCB": ["SCB", "SIAM COMMERCIAL", "ไทยพาณิชย์", "สเมอ"],
    "KBANK": ["KBANK", "KASIKORN", "กสิกร"],
    "BBL": ["BBL", "BANGKOK BANK", "กรุงเทพ"],
    "KTB": ["KTB", "KRUNGTHAI", "กรุงไทย"],
    "BAY": ["BAY", "KRUNGSRI", "กรุงศรี"],
    "TTB": ["TTB", "TMB", "THANACHART", "ทหารไทย"],
    "GSB": ["GSB", "ออมสิน"],
    "BAAC": ["BAAC", "ธกส"],
}


@dataclass
class OcrExtract:
    receiver: str
    bank: str
    last4: str
    amount_thb: Decimal
    confidence: Decimal
    raw: str
    verified: bool
    warning: str | None = None
    provider: str = "heuristic"


def image_hash(data: bytes) -> str:
    """Stable content hash for duplicate slip detection."""
    return hashlib.sha256(data).hexdigest()


def parse_slip_text(text: str) -> OcrExtract:
    """Heuristic parser for Thai transfer slip text / captions."""
    raw = text or ""
    cleaned = raw.replace("\r", "\n")
    confidence = Decimal("72.0")
    hits = 0

    amount = _extract_amount(cleaned)
    if amount is not None:
        hits += 1
        confidence += Decimal("8.0")

    bank = _extract_bank(cleaned)
    if bank:
        hits += 1
        confidence += Decimal("6.0")

    last4 = _extract_last4(cleaned)
    if last4:
        hits += 1
        confidence += Decimal("6.0")

    receiver = _extract_receiver(cleaned)
    if receiver:
        hits += 1
        confidence += Decimal("6.0")

    if hits >= 3:
        confidence = max(confidence, Decimal("90.0"))
    if hits >= 4:
        confidence = max(confidence, Decimal("96.0"))

    confidence = min(confidence, Decimal("99.5"))
    amount = amount if amount is not None else Decimal("0")
    bank = bank or "UNK"
    last4 = last4 or "0000"
    receiver = receiver or "UNKNOWN"

    warning = None
    verified = confidence >= CONFIDENCE_WARN_THRESHOLD and amount > 0 and last4 != "0000"
    if confidence < CONFIDENCE_WARN_THRESHOLD:
        warning = "Confidence below 90% — review before settle"
    if amount <= 0:
        warning = "Amount not detected"
        verified = False

    return OcrExtract(
        receiver=receiver,
        bank=bank,
        last4=last4,
        amount_thb=amount,
        confidence=confidence.quantize(Decimal("0.1")),
        raw=raw,
        verified=verified,
        warning=warning,
        provider="heuristic",
    )


def _extract_amount(text: str) -> Decimal | None:
    patterns = [
        r"(?:จำนวนเงิน|ยอดเงิน|Amount|THB|บาท)\s*[:\-]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)",
        r"([0-9]{1,3}(?:,[0-9]{3})+\.[0-9]{2})\s*(?:บาท|THB)?",
        r"(?<![0-9])([0-9]+\.[0-9]{2})\s*(?:บาท|THB)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return to_decimal(m.group(1))
    # bare number fallback
    m = re.search(r"(?<![0-9.])([1-9][0-9]{2,6}(?:\.[0-9]{2})?)(?![0-9])", text)
    if m:
        return to_decimal(m.group(1))
    return None


def _extract_bank(text: str) -> str | None:
    upper = text.upper()
    for code, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.upper() in upper or alias in text:
                return code
    return None


def _extract_last4(text: str) -> str | None:
    patterns = [
        r"(?:x{2,}|\*{2,}|•{2,}|X{2,})\s*([0-9]{4})",
        r"(?:บัญชี|Account|Acc(?:ount)?\.?)\s*[:\-]?\s*(?:x+|\*+|•+)?\s*([0-9]{4})\b",
        r"(?:ลงท้าย|ท้าย)\s*([0-9]{4})",
        r"(?<![0-9])([0-9]{3}-?[0-9]-?[0-9]{5}-?[0-9])(?![0-9])",  # full TH account
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            if len(digits) >= 4:
                return digits[-4:]
    # any masked account style
    m = re.search(r"[xX*•]{3,}([0-9]{4})", text)
    if m:
        return m.group(1)
    return None


def _extract_receiver(text: str) -> str | None:
    patterns = [
        r"(?:ชื่อบัญชี|ผู้รับ|Receiver|To|ไปยัง)\s*[:\-]?\s*([^\n]+)",
        r"(นาย[^\n]{2,40}|นางสาว[^\n]{2,40}|นาง[^\n]{2,40}|Mr\.?\s+[^\n]{2,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"\s{2,}", " ", name)
            return name[:48]
    return None


async def extract_from_image(
    image_bytes: bytes,
    caption: str | None = None,
) -> OcrExtract:
    """Run OCR. Prefer Vision API when configured; always merge caption signals."""
    caption_result = parse_slip_text(caption or "") if caption else None

    vision_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("VISION_API_KEY")
    vision_result: OcrExtract | None = None
    if vision_key and image_bytes:
        vision_result = await _openai_vision(image_bytes, vision_key)

    if vision_result and vision_result.amount_thb > 0:
        if caption_result and caption_result.amount_thb > 0:
            # Prefer higher confidence; fill gaps from caption
            base = vision_result if vision_result.confidence >= caption_result.confidence else caption_result
            other = caption_result if base is vision_result else vision_result
            return _merge(base, other)
        return vision_result

    if caption_result and caption_result.amount_thb > 0:
        return caption_result

    # Image without useful caption — low confidence stub for manual edit path
    stub = parse_slip_text(caption or "")
    stub.confidence = min(stub.confidence, Decimal("55.0"))
    stub.verified = False
    stub.warning = "Vision unavailable — send caption or Edit amount"
    stub.provider = "fallback"
    return stub


def _merge(primary: OcrExtract, secondary: OcrExtract) -> OcrExtract:
    return OcrExtract(
        receiver=primary.receiver if primary.receiver != "UNKNOWN" else secondary.receiver,
        bank=primary.bank if primary.bank != "UNK" else secondary.bank,
        last4=primary.last4 if primary.last4 != "0000" else secondary.last4,
        amount_thb=primary.amount_thb if primary.amount_thb > 0 else secondary.amount_thb,
        confidence=max(primary.confidence, secondary.confidence),
        raw=primary.raw or secondary.raw,
        verified=primary.verified or secondary.verified,
        warning=primary.warning if primary.confidence <= secondary.confidence else secondary.warning,
        provider=primary.provider,
    )


async def _openai_vision(image_bytes: bytes, api_key: str) -> OcrExtract | None:
    """Optional OpenAI Vision extraction. Soft-fail to heuristic."""
    try:
        import base64
        import json

        import httpx

        b64 = base64.b64encode(image_bytes).decode("ascii")
        model = os.environ.get("VISION_MODEL", "gpt-4o-mini")
        prompt = (
            "Extract Thai bank transfer slip fields as JSON only: "
            '{"receiver":"","bank":"SCB|KBANK|BBL|KTB|BAY|TTB|GSB|BAAC|UNK",'
            '"last4":"0000","amount_thb":0.00,"confidence":0.0}. '
            "confidence 0-100. No prose."
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
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 200,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            if resp.status_code >= 400:
                return None
            content = resp.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return None
            data: dict[str, Any] = json.loads(m.group(0))
            amount = to_decimal(data.get("amount_thb"))
            confidence = to_decimal(data.get("confidence") or 90)
            warning = None
            verified = confidence >= CONFIDENCE_WARN_THRESHOLD and amount > 0
            if confidence < CONFIDENCE_WARN_THRESHOLD:
                warning = "Confidence below 90% — review before settle"
            return OcrExtract(
                receiver=str(data.get("receiver") or "UNKNOWN")[:48],
                bank=str(data.get("bank") or "UNK").upper(),
                last4=re.sub(r"\D", "", str(data.get("last4") or "0000"))[-4:].zfill(4),
                amount_thb=amount,
                confidence=confidence.quantize(Decimal("0.1")),
                raw=content,
                verified=verified,
                warning=warning,
                provider="openai-vision",
            )
    except Exception:
        return None


def detect_repeated_receiver(history: dict[str, Any], *, warn_after: int = 5) -> str | None:
    """Flag receivers that appear frequently in the ledger."""
    count = int(history.get("tx_count") or 0)
    if count >= warn_after:
        return f"Repeated receiver — {count} prior settlements"
    return None
