"""OCR pipeline — vision extraction, confidence, slip fingerprinting."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

logger = logging.getLogger("ce_vault.ocr")

BANK_ALIASES = {
    "SCB": ("SCB", "SIAM COMMERCIAL", "ไทยพาณิชย์"),
    "KBANK": ("KBANK", "KASIKORN", "กสิกร"),
    "BBL": ("BBL", "BANGKOK BANK", "กรุงเทพ"),
    "KTB": ("KTB", "KRUNGTHAI", "กรุงไทย"),
    "BAY": ("BAY", "KRUNGSRI", "กรุงศรี"),
    "TTB": ("TTB", "TMB", "THANACHART", "ทหารไทย"),
    "GSB": ("GSB", "ออมสิน"),
    "BAAC": ("BAAC", "ธกส"),
}


@dataclass
class OcrResult:
    receiver_name: str | None = None
    bank: str | None = None
    last4: str | None = None
    amount: float | None = None
    confidence: float = 0.0
    raw_text: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    source: str = "heuristic"

    @property
    def verified(self) -> bool:
        return (
            self.amount is not None
            and self.amount > 0
            and bool(self.last4)
            and self.confidence >= 90.0
        )


ExtractFn = Callable[[bytes, str], OcrResult]


class OcrService:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        warn_below: float = 90.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.warn_below = warn_below
        self._client = http_client
        self._owns_client = http_client is None

    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def extract(self, image_bytes: bytes, mime: str = "image/jpeg") -> OcrResult:
        if self.api_key:
            try:
                return await self._extract_vision(image_bytes, mime)
            except Exception as exc:
                logger.warning("vision OCR failed, falling back: %s", exc)
        return extract_heuristic(image_bytes)

    async def _extract_vision(self, image_bytes: bytes, mime: str) -> OcrResult:
        client = await self._client_get()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        prompt = (
            "Extract Thai bank transfer slip fields. Return ONLY JSON with keys: "
            "receiver_name (string), bank (SCB|KBANK|BBL|KTB|BAY|TTB|GSB|BAAC or other), "
            "last4 (4 digits), amount (number THB), confidence (0-100), raw_text (string)."
        )
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"vision API {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        bank = normalize_bank(str(data.get("bank") or ""))
        last4 = normalize_last4(str(data.get("last4") or ""))
        amount = _safe_float(data.get("amount"))
        confidence = float(data.get("confidence") or 0)
        return OcrResult(
            receiver_name=(str(data.get("receiver_name") or "").strip() or None),
            bank=bank,
            last4=last4,
            amount=amount,
            confidence=confidence,
            raw_text=str(data.get("raw_text") or ""),
            fields=data,
            source="vision",
        )


def normalize_bank(text: str) -> str | None:
    upper = text.upper()
    for code, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.upper() in upper or alias in text:
                return code
    cleaned = re.sub(r"[^A-Z]", "", upper)
    return cleaned[:8] or None


def normalize_last4(text: str) -> str | None:
    digits = re.findall(r"\d", text)
    if len(digits) >= 4:
        return "".join(digits[-4:])
    return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace(" ", ""))
    except ValueError:
        return None


_AMOUNT_RE = re.compile(
    r"(?:THB|บาท|AMOUNT|จำนวน)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})|[0-9]+\.[0-9]{2})",
    re.IGNORECASE,
)
_LAST4_RE = re.compile(r"(?:x{2,}|\*{2,}|•{2,}|\.{2,}|xxxx)?\s*([0-9]{4})\b", re.IGNORECASE)
_NAME_RE = re.compile(r"(นาย|นาง|นางสาว|先生|MISS|MR\.?|MS\.?)\s*([^\n\d]{2,40})", re.IGNORECASE)


def extract_from_text(text: str) -> OcrResult:
    """Parse structured or free-text slip descriptions (also used when vision unavailable)."""
    bank = normalize_bank(text)
    last4 = None
    m_last = _LAST4_RE.search(text)
    if m_last:
        last4 = m_last.group(1)
    else:
        last4 = normalize_last4(text)

    amount = None
    amounts = [float(x.replace(",", "")) for x in _AMOUNT_RE.findall(text)]
    if amounts:
        amount = max(amounts)

    name = None
    m_name = _NAME_RE.search(text)
    if m_name:
        name = f"{m_name.group(1)}{m_name.group(2)}".strip()

    # Explicit key: value lines
    for line in text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            k = key.strip().lower()
            v = val.strip()
            if k in {"receiver", "name", "ผู้รับ"} and v:
                name = v
            elif k in {"bank", "ธนาคาร"} and v:
                bank = normalize_bank(v) or bank
            elif k in {"last4", "account", "บัญชี"} and v:
                last4 = normalize_last4(v) or last4
            elif k in {"amount", "thb", "จำนวน"} and v:
                amount = _safe_float(v) or amount

    confidence = 40.0
    if amount:
        confidence += 25
    if bank:
        confidence += 15
    if last4:
        confidence += 15
    if name:
        confidence += 5

    return OcrResult(
        receiver_name=name,
        bank=bank,
        last4=last4,
        amount=amount,
        confidence=min(confidence, 99.0),
        raw_text=text,
        source="text",
    )


def extract_heuristic(image_bytes: bytes) -> OcrResult:
    """Without vision API: attempt UTF-8 decode of embedded text; else low-confidence stub."""
    try:
        text = image_bytes.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    printable = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    if len(printable.strip()) > 20:
        result = extract_from_text(printable)
        result.source = "embedded"
        return result
    return OcrResult(
        confidence=35.0,
        raw_text="",
        source="unavailable",
        fields={"note": "Vision API not configured"},
    )


def parse_usdt_amount(text: str) -> float | None:
    text = text.strip()
    m = re.match(
        r"^(?:USDT|usdt)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USDT|usdt)?$",
        text,
    )
    if m:
        return float(m.group(1))
    m2 = re.match(r"^([0-9]+(?:\.[0-9]+)?)$", text)
    if m2:
        return float(m2.group(1))
    return None


def parse_edit_command(text: str) -> dict[str, Any]:
    """Parse edit corrections: THB 500 | USDT 12.5 | BANK SCB 3376"""
    out: dict[str, Any] = {}
    upper = text.strip()
    m_thb = re.search(r"\bTHB\s*([0-9]+(?:\.[0-9]+)?)", upper, re.IGNORECASE)
    if m_thb:
        out["thb"] = float(m_thb.group(1))
    m_usdt = re.search(r"\bUSDT\s*([0-9]+(?:\.[0-9]+)?)", upper, re.IGNORECASE)
    if m_usdt:
        out["usdt"] = float(m_usdt.group(1))
    m_bank = re.search(
        r"\bBANK\s+([A-Za-z]+)\s+([0-9]{4})\b",
        upper,
        re.IGNORECASE,
    )
    if m_bank:
        out["bank"] = normalize_bank(m_bank.group(1)) or m_bank.group(1).upper()
        out["last4"] = m_bank.group(2)
    return out
