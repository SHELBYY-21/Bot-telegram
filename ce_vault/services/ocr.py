"""OCR service — pluggable Vision with heuristic fallback.

Providers:
  openai    — GPT-4o vision (requires OPENAI_API_KEY)
  heuristic — parse caption / accompanying text patterns
  auto      — openai if key present, else heuristic
  none      — empty result (manual edit required)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ce_vault.config import CONFIDENCE_WARN_THRESHOLD, Settings
from ce_vault.models import OCRResult

logger = logging.getLogger("ce_vault.ocr")

BANK_ALIASES = {
    "SCB": ["scb", "siam commercial", "ไทยพาณิชย์"],
    "KBANK": ["kbank", "kasikorn", "กสิกร"],
    "BBL": ["bbl", "bangkok bank", "กรุงเทพ"],
    "KTB": ["ktb", "krungthai", "กรุงไทย"],
    "BAY": ["bay", "krungsri", "กรุงศรี"],
    "TTB": ["ttb", "tmbthanachart", "ทหารไทย"],
    "GSB": ["gsb", "ออมสิน"],
    "BAAC": ["baac", "ธ.ก.ส", "ธกส"],
}

AMOUNT_RE = re.compile(
    r"(?:THB|บาท|amount|จำนวน)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})|[0-9]+(?:\.[0-9]{1,2}))",
    re.IGNORECASE,
)
LAST4_RE = re.compile(
    r"(?:x{2,}|•{2,}|\*{2,}|\.{2,}|xxxx)?\s*([0-9]{4})\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"(?:ชื่อ|name|ผู้รับ|to|receiver)\s*[:：]?\s*([^\n\r,]{2,60})",
    re.IGNORECASE,
)


class OCRService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def extract(
        self,
        *,
        image_path: Path | None = None,
        caption: str = "",
        hint_text: str = "",
    ) -> OCRResult:
        provider = self.settings.ocr_provider
        if provider == "auto":
            provider = "openai" if self.settings.openai_api_key else "heuristic"
        if provider == "none":
            return OCRResult(warnings=["OCR disabled"])
        if provider == "openai" and image_path and self.settings.openai_api_key:
            try:
                result = await self._openai_vision(image_path, caption or hint_text)
                if result.amount_thb or result.last4 or result.bank:
                    return self._finalize(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("openai OCR failed, falling back: %s", exc)
        return self._finalize(self._heuristic(caption or hint_text))

    def _finalize(self, result: OCRResult) -> OCRResult:
        if result.confidence >= CONFIDENCE_WARN_THRESHOLD and result.amount_thb:
            result.verified = True
        else:
            result.verified = False
        if result.confidence and result.confidence < CONFIDENCE_WARN_THRESHOLD:
            result.warnings.append("Confidence below 90%")
        if not result.amount_thb:
            result.warnings.append("Amount not detected")
        return result

    def _heuristic(self, text: str) -> OCRResult:
        text = (text or "").strip()
        if not text:
            return OCRResult(confidence=0.0, warnings=["No text to parse"])

        bank = _detect_bank(text)
        last4 = _detect_last4(text)
        amount = _detect_amount(text)
        name = _detect_name(text)

        score = 40.0
        if bank:
            score += 15
        if last4:
            score += 20
        if amount is not None:
            score += 20
        if name:
            score += 10
        score = min(score, 99.0)

        return OCRResult(
            receiver_name=name or "",
            bank=bank or "",
            last4=last4 or "",
            amount_thb=amount,
            confidence=score,
            raw_text=text[:2000],
        )

    async def _openai_vision(self, image_path: Path, hint: str) -> OCRResult:
        import base64

        import httpx

        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        suffix = image_path.suffix.lower().lstrip(".") or "jpeg"
        if suffix == "jpg":
            suffix = "jpeg"
        prompt = (
            "Extract Thai bank transfer slip fields as JSON only with keys: "
            "receiver_name, bank (SCB|KBANK|BBL|KTB|BAY|TTB|GSB|BAAC or short code), "
            "last4 (4 digits), amount_thb (number), confidence (0-100). "
            "No markdown."
        )
        if hint:
            prompt += f" Caption hint: {hint[:400]}"

        body = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{suffix};base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 300,
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        data = _parse_json_object(content)
        return OCRResult(
            receiver_name=str(data.get("receiver_name") or ""),
            bank=str(data.get("bank") or "").upper(),
            last4=str(data.get("last4") or "")[-4:],
            amount_thb=_to_float(data.get("amount_thb")),
            confidence=float(data.get("confidence") or 92.0),
            raw_text=content[:2000],
        )


def _detect_bank(text: str) -> str | None:
    lower = text.lower()
    for code, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower:
                return code
        if re.search(rf"\b{code}\b", text, re.IGNORECASE):
            return code
    return None


def _detect_last4(text: str) -> str | None:
    # Prefer masked account patterns
    masked = re.search(
        r"(?:x{2,}|X{2,}|\*{2,}|•{2,}|\.{3,})\s*([0-9]{4})",
        text,
    )
    if masked:
        return masked.group(1)
    # Explicit last4 labels
    labeled = re.search(
        r"(?:last\s*4|ท้าย|ลงท้าย|บัญชี)\s*[:：]?\s*([0-9]{4})",
        text,
        re.IGNORECASE,
    )
    if labeled:
        return labeled.group(1)
    matches = LAST4_RE.findall(text)
    return matches[-1] if matches else None


def _detect_amount(text: str) -> float | None:
    # Prefer lines with currency markers
    for pattern in (
        r"(?:THB|บาท)\s*[:：]?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
        r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?)",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    m = AMOUNT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _detect_name(text: str) -> str | None:
    m = NAME_RE.search(text)
    if m:
        return m.group(1).strip()
    # Thai honorifics
    m = re.search(r"((?:นาย|นาง|นางสาว|คุณ)\s*[^\n\r,]{2,40})", text)
    if m:
        return m.group(1).strip()
    return None


def _parse_json_object(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
