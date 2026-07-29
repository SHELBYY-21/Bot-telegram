"""Slip OCR extraction for Thai bank transfers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

THAI_BANKS = {
    "scb": "SCB",
    "ไทยพาณิชย์": "SCB",
    "กสิกร": "KBANK",
    "kbank": "KBANK",
    "กรุงเทพ": "BBL",
    "bbl": "BBL",
    "กรุงไทย": "KTB",
    "ktb": "KTB",
    "กรุงศรี": "BAY",
    "bay": "BAY",
    "ทหารไทย": "TTB",
    "ttb": "TTB",
}


@dataclass(frozen=True)
class OCRResult:
    receiver_name: str | None
    bank: str | None
    last4: str | None
    amount_thb: float | None
    confidence: float
    raw_text: str
    verified: bool

    @property
    def masked_receiver(self) -> str | None:
        if self.bank and self.last4:
            return f"{self.bank} ••••{self.last4}"
        return None


class OCRService:
    def __init__(
        self,
        provider: str = "mock",
        google_vision_api_key: str | None = None,
        low_confidence_threshold: float = 90.0,
    ):
        self.provider = provider
        self.google_vision_api_key = google_vision_api_key
        self.low_confidence_threshold = low_confidence_threshold

    @staticmethod
    def hash_image(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    async def process(self, image_bytes: bytes, hint: str | None = None) -> OCRResult:
        if self.provider == "vision" and self.google_vision_api_key:
            text, confidence = await self._vision_ocr(image_bytes)
        else:
            text, confidence = self._mock_ocr(image_bytes, hint)
        parsed = self._parse_text(text)
        verified = confidence >= self.low_confidence_threshold and parsed["amount_thb"] is not None
        return OCRResult(
            receiver_name=parsed["receiver_name"],
            bank=parsed["bank"],
            last4=parsed["last4"],
            amount_thb=parsed["amount_thb"],
            confidence=confidence,
            raw_text=text,
            verified=verified,
        )

    async def _vision_ocr(self, image_bytes: bytes) -> tuple[str, float]:
        import base64

        payload = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image_bytes).decode()},
                    "features": [{"type": "TEXT_DETECTION"}],
                }
            ]
        }
        url = (
            "https://vision.googleapis.com/v1/images:annotate"
            f"?key={self.google_vision_api_key}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        annotations = data["responses"][0].get("textAnnotations", [])
        if not annotations:
            return "", 0.0
        text = annotations[0].get("description", "")
        confidence = 98.0 if text else 0.0
        return text, confidence

    def _mock_ocr(self, image_bytes: bytes, hint: str | None) -> tuple[str, float]:
        digest = hashlib.sha256(image_bytes).hexdigest()
        if hint:
            return hint, 98.4
        # Deterministic mock from image hash for repeatable tests.
        seed = int(digest[:8], 16)
        amount = round(100 + (seed % 9000) / 10, 2)
        last4 = f"{seed % 10000:04d}"
        text = (
            f"ธนาคารไทยพาณิชย์ SCB\n"
            f"โอนเงินให้ นายสมชาย ใจดี\n"
            f"เลขบัญชี xxx-x-xx{last4[-4:]}\n"
            f"จำนวน {amount:,.2f} บาท\n"
            f"สำเร็จ"
        )
        return text, 98.4

    def _parse_text(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        bank = None
        for key, code in THAI_BANKS.items():
            if key in lowered:
                bank = code
                break

        receiver_match = re.search(
            r"(?:โอน(?:เงิน)?(?:ให้|ไปยัง)?|to)\s*([^\n\r\d]{3,80})",
            text,
            re.IGNORECASE,
        )
        receiver_name = receiver_match.group(1).strip() if receiver_match else None

        last4_match = re.search(r"(?:x{2,}[- ]?)?(\d{4})\b", text, re.IGNORECASE)
        last4 = last4_match.group(1) if last4_match else None

        amount = None
        amount_patterns = [
            r"(?:จำนวน|amount|ยอด)\s*[:\s]*([0-9,]+\.?[0-9]*)",
            r"([0-9,]+\.[0-9]{2})\s*(?:บาท|thb|baht)",
            r"฿\s*([0-9,]+\.?[0-9]*)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(",", ""))
                break

        return {
            "receiver_name": receiver_name,
            "bank": bank,
            "last4": last4,
            "amount_thb": amount,
        }

    def save_image(self, image_bytes: bytes, ledger_id: str, images_dir: Path) -> str:
        images_dir.mkdir(parents=True, exist_ok=True)
        path = images_dir / f"{ledger_id}.jpg"
        path.write_bytes(image_bytes)
        return str(path)
