"""Vision OCR provider resolution — Grok / OpenAI / explicit overrides."""

import pytest

from ce_vault import ocr
from ce_vault.ocr import (
    GROK_API_BASE,
    GROK_VISION_MODEL,
    OPENAI_API_BASE,
    OPENAI_VISION_MODEL,
    resolve_vision_provider,
)

ENV_KEYS = [
    "OCR_API_KEY",
    "OPENAI_API_KEY",
    "GROK_API_KEY",
    "GROK_MODEL",
    "OCR_API_BASE",
    "OCR_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # The provider logs once per distinct endpoint; reset so each test is
    # independent of ordering.
    ocr._logged_providers.clear()


def test_no_keys_returns_none():
    assert resolve_vision_provider() is None


def test_grok_key_selects_xai_endpoint(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    key, base, model = resolve_vision_provider()
    assert key == "xai-abc"
    assert base == GROK_API_BASE
    assert model == GROK_VISION_MODEL


def test_grok_model_override(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    monkeypatch.setenv("GROK_MODEL", "grok-9-vision")
    _, base, model = resolve_vision_provider()
    assert base == GROK_API_BASE
    assert model == "grok-9-vision"


def test_openai_key_selects_openai_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    key, base, model = resolve_vision_provider()
    assert key == "sk-abc"
    assert base == OPENAI_API_BASE
    assert model == OPENAI_VISION_MODEL


def test_grok_preferred_over_openai(monkeypatch):
    """Grok reads Thai slips better, so it wins when both are configured."""
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    key, base, _ = resolve_vision_provider()
    assert key == "xai-abc"
    assert base == GROK_API_BASE


def test_explicit_ocr_api_key_wins(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "custom-key")
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    key, base, _ = resolve_vision_provider()
    assert key == "custom-key"
    assert base == OPENAI_API_BASE


def test_argument_beats_environment(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    key, _, _ = resolve_vision_provider("passed-in")
    assert key == "passed-in"


def test_base_and_model_overrides_apply_to_any_provider(monkeypatch):
    """Any OpenAI-compatible host stays reachable via OCR_API_BASE."""
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    monkeypatch.setenv("OCR_API_BASE", "https://self-hosted.example/v1/")
    monkeypatch.setenv("OCR_MODEL", "llava")
    _, base, model = resolve_vision_provider()
    assert base == "https://self-hosted.example/v1"  # trailing slash trimmed
    assert model == "llava"


def test_blank_env_values_are_ignored(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "   ")
    monkeypatch.setenv("GROK_API_KEY", "xai-abc")
    key, base, _ = resolve_vision_provider()
    assert key == "xai-abc"
    assert base == GROK_API_BASE


@pytest.mark.asyncio
async def test_vision_ocr_noop_without_provider():
    assert await ocr.vision_ocr(b"\xff\xd8\xff") is None
