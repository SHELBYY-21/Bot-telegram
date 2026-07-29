"""Slip OCR — vision intake for CE VAULT.

Uses optional OpenAI vision when OPENAI_API_KEY is set; otherwise falls
back to caption / filename heuristics so the console stays usable offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("ce_vault.ocr")

BANK_ALIASES = {
    "scb": "SCB",
    "siam commercial": "SCB",
    "กสิกร": "KBANK",
    "kbank": "KBANK",
    "kasikorn": "KBANK",
    "bbl": "BBL",
    "bangkok bank": "BBL",
    "ktb": "KTB",
    "กรุงไทย": "KTB",
    "bay": "BAY",
    "krungsri": "BAY",
    "ttb": "TTB",
    "tmb": "TTB",
    "gsb": "GSB",
    "ออมสิน": "GSB",
}


@dataclass
class OCRResult:
    receiver: str
    bank: str
    last4: str
    amount: float
    confidence: float
    raw_text: str = ""
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def slip_hash(file_unique_id: str, file_size: int | None = None) -> str:
    payload = f"{file_unique_id}:{file_size or 0}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _normalize_bank(text: str) -> str:
    lower = text.lower()
    for key, code in BANK_ALIASES.items():
        if key in lower:
            return code
    # Bare ticker
    m = re.search(r"\b(SCB|KBANK|BBL|KTB|BAY|TTB|GSB)\b", text, re.I)
    return m.group(1).upper() if m else "UNK"


def _extract_last4(text: str) -> str:
    patterns = [
        r"[xX*•·.]{2,}\s*(\d{4})",
        r"[xX*]{4}(\d{4})",
        r"(?:บัญชี|account|acc|a/c)[^\d]*(\d{4})\b",
        r"(?:last\s*4|last4)[^\d]*(\d{4})",
        r"(\d{3})-?(\d{1})[xX*]{0,6}(\d{4})",
        r"\b\d{6,}(\d{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.groups()[-1]
    # any trailing 4 digits near bank-looking lines
    m = re.search(r"(\d{4})\s*$", text.strip())
    return m.group(1) if m else "0000"


def _extract_amount(text: str) -> float | None:
    patterns = [
        r"(?:จำนวน|amount|amt|เงิน)[^\d]*([\d,]+(?:\.\d{1,2})?)",
        r"([\d,]+\.\d{2})\s*(?:บาท|THB|฿)",
        r"(?:THB|฿)\s*([\d,]+(?:\.\d{1,2})?)",
        r"\b([\d,]+\.\d{2})\b",
        r"\b([\d,]{3,})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                val = float(raw)
                if 1 <= val <= 50_000_000:
                    return val
            except ValueError:
                continue
    return None


def _extract_receiver(text: str) -> str:
    patterns = [
        r"(?:ชื่อ|name|ผู้รับ|to|receiver)\s*[:：]?\s*(.+)",
        r"(นาย|นาง|น\.ส\.|นางสาว|Mr\.|Mrs\.|Ms\.)\s*.+",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            line = m.group(0).strip()
            # trim labels
            line = re.sub(r"^(?:ชื่อ|name|ผู้รับ|to|receiver)\s*[:：]?\s*", "", line, flags=re.I)
            return line[:80]
    # first non-empty line that looks like a name
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 3 and not re.search(r"\d{4,}", s) and "THB" not in s.upper():
            return s[:80]
    return "Unknown"


def parse_text_slip(text: str, base_confidence: float = 92.0) -> OCRResult:
    text = text.strip()
    amount = _extract_amount(text)
    bank = _normalize_bank(text)
    last4 = _extract_last4(text)
    receiver = _extract_receiver(text)

    confidence = base_confidence
    if amount is None:
        amount = 0.0
        confidence -= 25
    if bank == "UNK":
        confidence -= 10
    if last4 == "0000":
        confidence -= 15
    if receiver == "Unknown":
        confidence -= 10
    confidence = max(40.0, min(99.5, confidence))

    return OCRResult(
        receiver=receiver,
        bank=bank,
        last4=last4,
        amount=float(amount or 0),
        confidence=round(confidence, 1),
        raw_text=text[:2000],
        source="text",
    )


async def run_vision_ocr(
    image_bytes: bytes,
    caption: str | None = None,
) -> OCRResult:
    """Try OpenAI vision; fall back to caption heuristics."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            return await _openai_vision(api_key, image_bytes, caption)
        except Exception as e:
            logger.warning("vision OCR failed, falling back: %s", e)

    if caption and caption.strip():
        result = parse_text_slip(caption, base_confidence=88.0)
        result.source = "caption"
        return result

    # Minimal stub so the console can continue — staff edits fields.
    return OCRResult(
        receiver="Pending review",
        bank="UNK",
        last4="0000",
        amount=0.0,
        confidence=55.0,
        raw_text=caption or "",
        source="manual",
    )


async def _openai_vision(api_key: str, image_bytes: bytes, caption: str | None) -> OCRResult:
    import base64

    import httpx

    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Extract Thai bank transfer slip fields as JSON only with keys: "
        "receiver (string), bank (SCB|KBANK|BBL|KTB|BAY|TTB|GSB|UNK), "
        "last4 (4 digits), amount (number THB), confidence (0-100). "
        "No markdown."
    )
    if caption:
        prompt += f" Caption hint: {caption[:200]}"

    body = {
        "model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini"),
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
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    return OCRResult(
        receiver=str(data.get("receiver") or "Unknown")[:80],
        bank=_normalize_bank(str(data.get("bank") or "UNK")),
        last4=str(data.get("last4") or "0000")[-4:].zfill(4),
        amount=float(data.get("amount") or 0),
        confidence=float(data.get("confidence") or 90),
        raw_text=content[:2000],
        source="vision",
    )


def format_receiver_display(bank: str, last4: str, name: str | None = None) -> str:
    masked = f"{bank} ••••{last4}"
    if name and name not in {"Unknown", "Pending review"}:
        short = name if len(name) <= 24 else name[:22] + "…"
        return f"{short} · {masked}"
    return masked
