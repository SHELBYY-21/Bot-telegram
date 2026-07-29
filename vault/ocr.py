"""Slip OCR — extract THB amount, receiver, bank, and last4.

Strategy (in order):
1. Structured text / caption parser (always available)
2. Optional Vision API when OCR_API_KEY / OPENAI_API_KEY is set
3. Deterministic demo fixtures for offline testing

Never asks the operator for a buy rate. Amount + receiver identity only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

BANK_ALIASES = {
    "SCB": ("SCB", "SIAM COMMERCIAL", "ไทยพาณิชย์", "SCB Easy"),
    "KBANK": ("KBANK", "KASIKORN", "กสิกร", "K PLUS", "KBank"),
    "BBL": ("BBL", "BANGKOK BANK", "กรุงเทพ"),
    "KTB": ("KTB", "KRUNGTHAI", "กรุงไทย", "Krungthai"),
    "BAY": ("BAY", "KRUNGSRI", "กรุงศรี", "Bay"),
    "TMB": ("TMB", "TTB", "ทหารไทย", "ธนชาต"),
    "GSB": ("GSB", "ออมสิน", "GOVERNMENT SAVINGS"),
    "BAAC": ("BAAC", "ธกส", "เพื่อการเกษตร"),
}


AMOUNT_PATTERNS = [
    re.compile(r"(?:จำนวนเงิน|ยอด|Amount|AMT|THB|บาท)\s*[:：]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", re.I),
    re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})\s*(?:บาท|THB)", re.I),
    re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})\b"),
]

ACCOUNT_PATTERNS = [
    re.compile(r"(?:x{2,}|\*{2,}|•{2,}|X{2,}|={2,})-?(?:x|\*|•|X|=|[0-9]-?)*([0-9]{4})\b", re.I),
    re.compile(r"(?:บัญชี|Account|Acc(?:ount)?\s*No\.?|เลขที่)\s*[:：]?\s*[^\n]*?([0-9]{4})\b", re.I),
    re.compile(r"\b(?:x{3,}|\*{3,}|•{3,})([0-9]{4})\b", re.I),
]

NAME_PATTERNS = [
    re.compile(r"(?:ชื่อ|ผู้รับ|To|Receiver|Account Name)\s*[:：]?\s*(.+)", re.I),
    re.compile(r"(นาย|นาง|นางสาว|น\.ส\.|Mr\.?|Mrs\.?|Ms\.?)\s*.+"),
]


@dataclass
class OCRResult:
    amount_thb: float | None = None
    receiver_name: str | None = None
    bank: str | None = None
    last4: str | None = None
    confidence: float = 0.0
    raw_text: str = ""
    source: str = "parser"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def slip_hash(payload: bytes | str) -> str:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def detect_bank(text: str) -> str | None:
    upper = text.upper()
    for code, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.upper() in upper or alias in text:
                return code
    return None


def _parse_amount(text: str) -> float | None:
    for pattern in AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return round(float(raw), 2)
            except ValueError:
                continue
    return None


def _parse_last4(text: str) -> str | None:
    # Prefer masked forms like xxx-x-x3376-x / ••••3376 / xxx3376
    masked = re.search(
        r"(?:x{2,}|\*{2,}|•{2,}|X{2,})[\sx*\-•=]*([0-9]{4})(?:\b|[\sx*\-•=])",
        text,
        re.I,
    )
    if masked:
        return masked.group(1)
    for pattern in ACCOUNT_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            candidate = matches[-1][-4:]
            # Avoid mistaking integer amounts (e.g. 500) for account tails
            if candidate and not re.search(
                rf"\b{re.escape(candidate)}\s*(?:บาท|THB|\.)", text, re.I
            ):
                return candidate
            if len(matches) > 1:
                return matches[0][-4:]
    return None


def _parse_name(text: str) -> str | None:
    for pattern in NAME_PATTERNS:
        m = pattern.search(text)
        if m:
            name = (m.group(0) if m.lastindex is None else m.group(m.lastindex or 0)).strip()
            name = re.split(r"[\n|/]", name)[0].strip()
            # Strip label prefixes
            name = re.sub(r"^(?:ชื่อ|ผู้รับ|To|Receiver|Account Name)\s*[:：]?\s*", "", name, flags=re.I)
            if 2 <= len(name) <= 80:
                return name
    return None


def parse_slip_text(text: str) -> OCRResult:
    text = (text or "").strip()
    if not text:
        return OCRResult(confidence=0.0, raw_text="", source="parser")

    amount = _parse_amount(text)
    bank = detect_bank(text)
    last4 = _parse_last4(text)
    name = _parse_name(text)

    score = 0.0
    if amount is not None:
        score += 40.0
    if bank:
        score += 25.0
    if last4:
        score += 25.0
    if name:
        score += 10.0

    return OCRResult(
        amount_thb=amount,
        receiver_name=name,
        bank=bank,
        last4=last4,
        confidence=round(score, 1),
        raw_text=text,
        source="parser",
    )


async def vision_ocr(image_bytes: bytes, api_key: str | None = None) -> OCRResult | None:
    """Optional OpenAI-compatible vision pass for slip images."""
    key = api_key or os.environ.get("OCR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None

    base = os.environ.get("OCR_API_BASE", "https://api.openai.com/v1")
    model = os.environ.get("OCR_MODEL", "gpt-4o-mini")
    import base64

    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Extract Thai bank transfer slip fields as JSON only with keys: "
        "amount_thb (number), receiver_name (string), bank (SCB|KBANK|BBL|KTB|BAY|TMB|GSB|BAAC), "
        "last4 (4 digits), confidence (0-100). No prose."
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
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code >= 400:
                return None
            content = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None

    data = _extract_json(content)
    if not data:
        return parse_slip_text(content)

    return OCRResult(
        amount_thb=_as_float(data.get("amount_thb")),
        receiver_name=data.get("receiver_name"),
        bank=data.get("bank"),
        last4=str(data.get("last4") or "")[-4:] or None,
        confidence=float(data.get("confidence") or 92.0),
        raw_text=content,
        source="vision",
    )


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(str(value).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


async def analyze_slip(
    *,
    text: str | None = None,
    image_bytes: bytes | None = None,
    file_unique_id: str | None = None,
) -> tuple[OCRResult, str]:
    """Return (OCRResult, slip_hash). Prefers vision when image + key available."""
    hash_source = image_bytes or (file_unique_id or text or "").encode("utf-8")
    digest = slip_hash(hash_source)

    result: OCRResult | None = None
    if image_bytes:
        result = await vision_ocr(image_bytes)

    if result is None and text:
        result = parse_slip_text(text)
    elif result is None:
        result = OCRResult(confidence=0.0, source="empty")

    # Caption/text can fill gaps left by vision
    if text and result.source == "vision":
        fallback = parse_slip_text(text)
        result = OCRResult(
            amount_thb=result.amount_thb or fallback.amount_thb,
            receiver_name=result.receiver_name or fallback.receiver_name,
            bank=result.bank or fallback.bank,
            last4=result.last4 or fallback.last4,
            confidence=max(result.confidence, fallback.confidence),
            raw_text=result.raw_text or fallback.raw_text,
            source="vision+parser",
        )

    return result, digest


# Deterministic fixture for demos / tests
DEMO_SLIP_TEXT = """
SCB Easy
โอนเงินสำเร็จ
ผู้รับ: นายสมชาย ใจดี
บัญชี: xxx-x-x3376-x
จำนวนเงิน: 500.00 บาท
"""
