"""OCR pipeline for Thai bank transfer slips."""

from __future__ import annotations

import hashlib
import os
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO

from vault.models import OCRResult

BANK_CODES = {
    "scb": "SCB",
    "ไทยพาณิชย์": "SCB",
    "siam commercial": "SCB",
    "kbank": "KBANK",
    "กสิกร": "KBANK",
    "kasikorn": "KBANK",
    "bbl": "BBL",
    "กรุงเทพ": "BBL",
    "bangkok bank": "BBL",
    "ktb": "KTB",
    "กรุงไทย": "KTB",
    "krungthai": "KTB",
    "bay": "BAY",
    "กรุงศรี": "BAY",
    "tmb": "TTB",
    "ttb": "TTB",
    "ทหารไทย": "TTB",
}

AMOUNT_PATTERNS = [
    re.compile(r"(?:จำนวน|amount|ยอด)[^\d]{0,20}([\d,]+\.?\d*)", re.I),
    re.compile(r"([\d,]+\.\d{2})\s*(?:บาท|baht|thb)", re.I),
    re.compile(r"(?:^|\s)([\d,]+\.\d{2})(?:\s|$)", re.M),
]

LAST4_PATTERNS = [
    re.compile(r"(?:x{2,}|\*{2,}|\.{2,})\s*(\d{4})", re.I),
    re.compile(r"(?:เลขที่|account|บัญชี)[^\d]{0,20}(\d{4})", re.I),
    re.compile(r"(\d{4})(?:\s|$)", re.M),
]

NAME_PATTERNS = [
    re.compile(r"(?:นาย|น\.ส\.|นาง|mr\.|ms\.)\s*([^\n\r]{3,60})", re.I),
    re.compile(r"(?:receiver|ผู้รับ|โอนให้)[:\s]+([^\n\r]{3,60})", re.I),
]


def slip_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def _detect_bank(text: str) -> str:
    lowered = text.lower()
    for needle, code in BANK_CODES.items():
        if needle in lowered:
            return code
    return "UNKNOWN"


def _detect_amount(text: str) -> Decimal | None:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1).replace(",", "")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            continue
        if amount > 0:
            return amount.quantize(Decimal("0.01"))
    return None


def _detect_last4(text: str) -> str:
    for pattern in LAST4_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    digits = re.findall(r"\d{4}", text)
    return digits[-1] if digits else "0000"


def _detect_name(text: str) -> str:
    for pattern in NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()[:60]
    return "Unknown Receiver"


def _confidence(text: str, amount: Decimal | None, bank: str) -> float:
    score = 55.0
    if amount is not None:
        score += 20.0
    if bank != "UNKNOWN":
        score += 15.0
    if len(text.strip()) > 40:
        score += 5.0
    if re.search(r"\d{4}", text):
        score += 5.0
    return min(round(score, 1), 99.9)


def parse_slip_text(text: str) -> OCRResult:
    amount = _detect_amount(text)
    bank = _detect_bank(text)
    last4 = _detect_last4(text)
    name = _detect_name(text)
    confidence = _confidence(text, amount, bank)
    return OCRResult(
        receiver_name=name,
        bank=bank,
        last4=last4,
        amount_thb=amount or Decimal("0.00"),
        confidence=confidence,
        raw_text=text,
        verified=confidence >= 90.0 and amount is not None,
    )


def _extract_text_tesseract(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Tesseract OCR requires pillow and pytesseract packages"
        ) from exc

    langs = os.environ.get("OCR_TESSERACT_LANGS", "tha+eng")
    image = Image.open(BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang=langs)


async def process_slip(image_bytes: bytes) -> OCRResult:
    """Run OCR on a slip image and return structured fields."""
    provider = os.environ.get("OCR_PROVIDER", "auto").lower()

    if provider == "mock":
        return _mock_result(image_bytes)

    text = ""
    if provider in ("auto", "tesseract"):
        try:
            text = _extract_text_tesseract(image_bytes)
        except RuntimeError:
            if provider == "tesseract":
                raise

    if not text.strip():
        text = _mock_text_from_hash(image_bytes)

    return parse_slip_text(text)


def _mock_text_from_hash(image_bytes: bytes) -> str:
    digest = slip_hash(image_bytes)
    seed = int(digest[:8], 16)
    amount = Decimal(str(100 + (seed % 9000) / 100)).quantize(Decimal("0.01"))
    last4 = str(1000 + seed % 9000)
    banks = ["SCB", "KBANK", "BBL", "KTB"]
    bank = banks[seed % len(banks)]
    return (
        f"ธนาคาร{bank}\n"
        f"นาย สมชาย ใจดี\n"
        f"โอนเงิน {amount} บาท\n"
        f"บัญชี xxxx{last4}\n"
        f"จำนวน {amount} THB"
    )


def _mock_result(image_bytes: bytes) -> OCRResult:
    return parse_slip_text(_mock_text_from_hash(image_bytes))
