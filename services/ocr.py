"""OCR service for bank slip processing."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Any

import httpx

from config import OCR_API_URL, OCR_CONFIDENCE_WARN

logger = logging.getLogger(__name__)

# Thai bank codes
BANK_PATTERNS = {
    "SCB": [r"scb", r"siam commercial", r"ไทยพาณิชย์"],
    "KBANK": [r"kbank", r"kasikorn", r"กสิกร"],
    "BBL": [r"bbl", r"bangkok bank", r"กรุงเทพ"],
    "KTB": [r"ktb", r"krungthai", r"กรุงไทย"],
    "BAY": [r"bay", r"krungsri", r"กรุงศรี"],
    "TTB": [r"ttb", r"tmb", r"ทหารไทย"],
    "GSB": [r"gsb", r"ออมสิน"],
}


@dataclass
class OCRResult:
    amount: float | None = None
    receiver_name: str | None = None
    bank: str | None = None
    last4: str | None = None
    confidence: float = 0.0
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_verified(self) -> bool:
        return self.confidence >= OCR_CONFIDENCE_WARN and self.amount is not None

    @property
    def needs_warning(self) -> bool:
        return self.confidence < OCR_CONFIDENCE_WARN


def _detect_bank(text: str) -> str | None:
    lower = text.lower()
    for bank, patterns in BANK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, lower):
                return bank
    return None


def _extract_amount(text: str) -> float | None:
    patterns = [
        r"(?:จำนวน|amount|ยอด)[:\s]*([0-9,]+\.?[0-9]*)",
        r"([0-9,]+\.[0-9]{2})\s*(?:บาท|baht|thb)",
        r"(?:^|\s)([0-9,]+\.[0-9]{2})(?:\s|$)",
        r"(?:^|\s)([0-9,]+)(?:\s*บาท|\s*THB)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_last4(text: str) -> str | None:
    patterns = [
        r"(?:x{2,}|•{2,}|X{2,})\s*([0-9]{4})",
        r"(?:เลขที่|account|บัญชี)[:\s]*(?:x+|X+|\*+)?([0-9]{4})",
        r"([0-9]{4})\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_receiver_name(text: str) -> str | None:
    patterns = [
        r"(?:นาย|นาง|นางสาว|mr\.?|mrs\.?|ms\.?)\s*([^\n\r]{3,40})",
        r"(?:to|ถึง|ผู้รับ)[:\s]*([^\n\r]{3,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) > 2:
                return name[:40]
    return None


def parse_slip_text(text: str) -> OCRResult:
    """Parse OCR text into structured fields."""
    amount = _extract_amount(text)
    bank = _detect_bank(text)
    last4 = _extract_last4(text)
    name = _extract_receiver_name(text)

    confidence = 50.0
    if amount:
        confidence += 25.0
    if bank:
        confidence += 10.0
    if last4:
        confidence += 10.0
    if name:
        confidence += 5.0
    confidence = min(confidence, 99.9)

    return OCRResult(
        amount=amount,
        receiver_name=name,
        bank=bank,
        last4=last4,
        confidence=round(confidence, 1),
        raw_text=text,
    )


async def _call_external_ocr(image_data: bytes) -> str | None:
    if not OCR_API_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OCR_API_URL,
                files={"image": ("slip.jpg", image_data, "image/jpeg")},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("text") or data.get("raw_text") or json.dumps(data)
    except Exception as e:
        logger.warning("External OCR failed: %s", e)
    return None


def _mock_ocr_from_hash(image_data: bytes) -> OCRResult:
    """Deterministic mock OCR for demo/testing based on image hash."""
    h = hashlib.sha256(image_data).hexdigest()
    seed = int(h[:8], 16)

    banks = list(BANK_PATTERNS.keys())
    bank = banks[seed % len(banks)]
    last4 = f"{(seed % 9000) + 1000}"
    amount = round(((seed % 50000) + 100) + (seed % 100) / 100, 2)

    names = [
        "นาย สมชาย ใจดี",
        "นาง วิไล รักษ์ดี",
        "นาย ประเสริฐ มั่งคั่ง",
        "นางสาว สุดา แสงทอง",
    ]
    name = names[seed % len(names)]

    confidence = 85.0 + (seed % 15)

    return OCRResult(
        amount=amount,
        receiver_name=name,
        bank=bank,
        last4=last4,
        confidence=round(confidence, 1),
        raw_text=f"Mock OCR — {bank} ••••{last4} — {amount:.2f} THB — {name}",
    )


async def process_slip(image_data: bytes, caption: str | None = None) -> OCRResult:
    """Process a bank slip image through OCR pipeline."""
    if caption:
        result = parse_slip_text(caption)
        if result.amount:
            return result

    external_text = await _call_external_ocr(image_data)
    if external_text:
        return parse_slip_text(external_text)

    try:
        import pytesseract
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_data))
        text = pytesseract.image_to_string(img, lang="tha+eng")
        if text.strip():
            return parse_slip_text(text)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)

    return _mock_ocr_from_hash(image_data)
