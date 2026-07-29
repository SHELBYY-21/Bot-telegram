"""OCR pipeline for Thai payment slips.

Uses optional OpenAI Vision when OPENAI_API_KEY is set; otherwise applies a
deterministic heuristic parser suitable for caption / offline verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import httpx

from ce_vault.models import OCRResult

BANK_ALIASES = {
    "SCB": ("SCB", "SIAM COMMERCIAL", "ไทยพาณิชย์", "SIAM COMMERCIAL BANK"),
    "KBANK": ("KBANK", "KASIKORN", "กสิกร"),
    "BBL": ("BBL", "BANGKOK BANK", "กรุงเทพ"),
    "KTB": ("KTB", "KRUNGTHAI", "กรุงไทย"),
    "BAY": ("BAY", "KRUNGSRI", "กรุงศรี"),
    "TTB": ("TTB", "TMBTHANACHART", "ทหารไทย"),
    "GSB": ("GSB", "ออมสิน", "GOVERNMENT SAVINGS"),
}


def slip_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def _detect_bank(text: str) -> str:
    upper = text.upper()
    for code, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.upper() in upper:
                return code
    return ""


def _detect_last4(text: str) -> str:
    # Prefer masked account patterns xxxx3376 / ••••3376 / x3376
    patterns = [
        r"[xX*•∙·]{2,}(\d{4})",
        r"(?:บัญชี|account|acc(?:ount)?\.?|เลขที่)[^\d]{0,12}(\d{4})\b",
        r"\b(\d{4})\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1)
    # Fallback: last standalone 4-digit group that isn't a year-like 20xx
    candidates = re.findall(r"\b(\d{4})\b", text)
    for c in reversed(candidates):
        if not c.startswith("20"):
            return c
    return ""


def _detect_amount(text: str) -> float:
    patterns = [
        r"(?:จำนวน|amount|โอน|transfer)[^\d]{0,20}(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)",
        r"(\d{1,3}(?:,\d{3})*\.\d{2})\s*(?:บาท|THB|฿)",
        r"฿\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)",
        r"\b(\d{1,3}(?:,\d{3})*\.\d{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    # Integer baht amounts
    m = re.search(r"(?:จำนวน|amount)[^\d]{0,20}(\d{2,7})\b", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return 0.0


def _detect_name(text: str) -> str:
    patterns = [
        r"(?:ชื่อ|ผู้รับ|to|receiver|ชื่อบัญชี)\s*[:：]?\s*([^\n\r]+)",
        r"(นาย[^\n\r]+|นางสาว[^\n\r]+|นาง[^\n\r]+|คุณ[^\n\r]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"\s{2,}", " ", name)
            return name[:80]
    return ""


def parse_slip_text(text: str) -> OCRResult:
    """Heuristic OCR parse from plain text (caption or vision transcript)."""
    text = (text or "").strip()
    if not text:
        return OCRResult(confidence=0.0, verified=False, warnings=["Empty slip text"])

    bank = _detect_bank(text)
    last4 = _detect_last4(text)
    amount = _detect_amount(text)
    name = _detect_name(text)

    hits = sum(bool(x) for x in (bank, last4, amount, name))
    confidence = {0: 20.0, 1: 55.0, 2: 78.0, 3: 92.0, 4: 98.4}[hits]

    warnings: list[str] = []
    if confidence < 90:
        warnings.append("Confidence below 90%")
    if not bank:
        warnings.append("Bank not detected")
    if not last4:
        warnings.append("Account last4 not detected")
    if amount <= 0:
        warnings.append("Amount not detected")

    verified = confidence >= 90 and amount > 0 and bool(bank) and bool(last4)
    return OCRResult(
        receiver_name=name,
        bank=bank,
        last4=last4,
        amount_thb=amount,
        confidence=confidence,
        raw_text=text,
        verified=verified,
        warnings=warnings,
    )


async def vision_transcribe(image_bytes: bytes, mime: str = "image/jpeg") -> str | None:
    """Optional OpenAI Vision transcription. Returns None when unavailable."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    import base64

    b64 = base64.b64encode(image_bytes).decode("ascii")
    model = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract Thai bank transfer slip fields as plain text lines: "
                            "receiver name, bank, account last4, amount THB. No commentary."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 400,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception:
        return None


async def analyze_slip(
    image_bytes: bytes,
    *,
    caption: str = "",
    mime: str = "image/jpeg",
) -> tuple[OCRResult, str]:
    """Full OCR path. Returns (result, slip_hash)."""
    digest = slip_hash(image_bytes)
    vision_text = await vision_transcribe(image_bytes, mime=mime)
    combined = "\n".join(x for x in (vision_text or "", caption or "") if x).strip()
    if not combined:
        # Offline / no-vision: still produce a structured low-confidence shell
        # so the operator can Edit. Prefer caption alone if present.
        result = parse_slip_text(caption)
        if not caption:
            result.warnings.append("Vision unavailable — edit required")
            result.confidence = max(result.confidence, 10.0)
        return result, digest

    result = parse_slip_text(combined)
    if vision_text and result.confidence >= 78:
        # Vision path bumps confidence slightly when parse succeeds
        result.confidence = min(99.5, round(result.confidence + 2.0, 1))
        result.verified = result.confidence >= 90 and result.amount_thb > 0
    return result, digest


def ocr_from_dict(data: dict[str, Any]) -> OCRResult:
    return OCRResult.from_dict(data)


def dump_ocr(result: OCRResult) -> dict[str, Any]:
    return json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
