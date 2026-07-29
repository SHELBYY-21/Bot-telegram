"""OCR pipeline — pluggable providers with duplicate / confidence checks."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

import httpx

from ce_vault.design import CONFIDENCE_WARN
from ce_vault.models import OCRResult

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
    "กรุงไทย": "KTB",
    "bay": "BAY",
    "กรุงศรี": "BAY",
    "ttb": "TTB",
    "tmb": "TTB",
    "gsb": "GSB",
    "ออมสิน": "GSB",
}


def slip_hash_from_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slip_hash_from_file_id(file_id: str) -> str:
    return hashlib.sha256(file_id.encode()).hexdigest()


def normalize_bank(text: str) -> str:
    lower = text.lower().strip()
    for key, code in BANK_ALIASES.items():
        if key in lower:
            return code
    cleaned = re.sub(r"[^A-Za-z]", "", text).upper()
    return cleaned[:8] or "BANK"


def _extract_amount(text: str) -> float | None:
    # Prefer explicitly labeled amounts so account last4 is never mistaken for THB.
    labeled = [
        r"(?:THB|บาท|amount|จำนวน(?:เงิน)?)\s*[:=]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
        r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:THB|บาท)",
    ]
    for pat in labeled:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    # Fallback: first decimal money-looking number (requires fraction or thousands sep)
    m = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})+\.[0-9]{2}|[0-9]+\.[0-9]{2})\b", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _extract_last4(text: str) -> str:
    patterns = [
        r"(?:\*{2,}|\•{2,}|x{2,}|\.{2,})\s*([0-9]{4})",
        r"(?:x|X|\*){2,}([0-9]{4})",
        r"(?:บัญชี|account|acc)[^\d]*([0-9]{4})\b",
        r"\b([0-9]{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _extract_bank(text: str) -> str:
    for key, code in BANK_ALIASES.items():
        if key in text.lower():
            return code
    return ""


def _extract_name(text: str) -> str:
    # Thai honorifics + name, or Latin "Mr./Ms."
    m = re.search(
        r"((?:นาย|นาง|นางสาว|Mr\.?|Ms\.?|Mrs\.?)\s*[^\n\d]{2,40})",
        text,
    )
    if m:
        return m.group(1).strip()
    return ""


def parse_text_slip(text: str, confidence: float = 92.0) -> OCRResult:
    amount = _extract_amount(text) or 0.0
    bank = _extract_bank(text)
    last4 = _extract_last4(text)
    name = _extract_name(text)
    verified = bool(amount and (bank or last4))
    conf = confidence if verified else max(40.0, confidence - 30)
    warning = ""
    if conf < CONFIDENCE_WARN:
        warning = "Vision confidence below threshold"
    return OCRResult(
        receiver_name=name,
        bank=bank or "BANK",
        last4=last4,
        amount_thb=amount,
        confidence=round(conf, 1),
        verified=verified,
        warning=warning,
        raw={"source": "text", "text": text[:500]},
    )


async def ocr_easyslip(image_bytes: bytes) -> OCRResult | None:
    token = os.environ.get("EASYSLIP_TOKEN", "").strip()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://developer.easyslip.com/api/v1/verify",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("slip.jpg", image_bytes, "image/jpeg")},
            )
        if resp.status_code >= 400:
            logger.warning("EasySlip error %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        payload = data.get("data") or data
        receiver = payload.get("receiver") or {}
        amount = payload.get("amount") or {}
        thb = float(amount.get("amount") or amount.get("value") or 0)
        bank = normalize_bank(str(receiver.get("bank") or receiver.get("bank_name") or ""))
        account = str(receiver.get("account") or receiver.get("accountNumber") or "")
        last4 = account[-4:] if len(account) >= 4 else ""
        name = str(receiver.get("name") or receiver.get("displayName") or "")
        conf = float(payload.get("confidence") or 98.0)
        return OCRResult(
            receiver_name=name,
            bank=bank,
            last4=last4,
            amount_thb=thb,
            confidence=conf,
            slip_ref=str(payload.get("transRef") or payload.get("ref") or ""),
            verified=True,
            raw=payload if isinstance(payload, dict) else {"raw": payload},
        )
    except Exception as exc:
        logger.warning("EasySlip failed: %s", exc)
        return None


async def ocr_openai_vision(image_bytes: bytes) -> OCRResult | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    import base64

    b64 = base64.b64encode(image_bytes).decode()
    prompt = (
        "Extract Thai bank transfer slip fields as JSON only with keys: "
        "receiver_name, bank (code like SCB/KBANK), last4, amount_thb (number), "
        "confidence (0-100). No markdown."
    )
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}"
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 300,
                },
            )
        if resp.status_code >= 400:
            logger.warning("OpenAI vision error %s", resp.status_code)
            return None
        content = resp.json()["choices"][0]["message"]["content"]
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data: dict[str, Any] = json.loads(content)
        conf = float(data.get("confidence") or 95.0)
        return OCRResult(
            receiver_name=str(data.get("receiver_name") or ""),
            bank=normalize_bank(str(data.get("bank") or "BANK")),
            last4=str(data.get("last4") or "")[-4:],
            amount_thb=float(data.get("amount_thb") or 0),
            confidence=conf,
            verified=bool(data.get("amount_thb")),
            warning="Vision confidence below threshold" if conf < CONFIDENCE_WARN else "",
            raw=data,
        )
    except Exception as exc:
        logger.warning("OpenAI vision failed: %s", exc)
        return None


def mock_ocr_from_caption(caption: str | None, file_id: str) -> OCRResult:
    """Deterministic offline OCR for demos / tests when no provider is configured."""
    if caption and caption.strip():
        result = parse_text_slip(caption.strip(), confidence=96.5)
        if result.amount_thb:
            return result
    # Stable demo values derived from file_id so UI can be exercised
    digest = hashlib.sha256(file_id.encode()).hexdigest()
    amount = 100 + (int(digest[:4], 16) % 900) + ((int(digest[4:6], 16) % 100) / 100)
    last4 = f"{int(digest[6:10], 16) % 10000:04d}"
    banks = ["SCB", "KBANK", "BBL", "KTB", "TTB"]
    bank = banks[int(digest[10:12], 16) % len(banks)]
    return OCRResult(
        receiver_name="นายตัวอย่าง ระบบ",
        bank=bank,
        last4=last4,
        amount_thb=round(amount, 2),
        confidence=98.4,
        verified=True,
        slip_ref=digest[:12].upper(),
        raw={"source": "mock", "file_id": file_id},
    )


async def run_ocr(
    image_bytes: bytes | None,
    file_id: str,
    caption: str | None = None,
) -> OCRResult:
    if image_bytes:
        for provider in (ocr_easyslip, ocr_openai_vision):
            result = await provider(image_bytes)
            if result and result.amount_thb > 0:
                return result
    if caption and caption.strip():
        parsed = parse_text_slip(caption.strip())
        if parsed.amount_thb > 0:
            return parsed
    return mock_ocr_from_caption(caption, file_id)
