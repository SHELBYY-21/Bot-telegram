"""Slip storage backends — Supabase, local disk, null, and selection."""

from pathlib import Path

import httpx
import pytest

from ce_vault.storage import (
    LocalSlipStorage,
    NullSlipStorage,
    SupabaseSlipStorage,
    create_slip_storage,
)

DIGEST = "a" * 64
IMAGE = b"\xff\xd8\xff\xe0 fake jpeg bytes"

ENV_KEYS = [
    "SLIP_STORAGE",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_KEY",
    "SUPABASE_BUCKET",
    "IMAGES_DIR",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# --- local ---------------------------------------------------------------

def test_local_writes_bytes(tmp_path: Path):
    store = LocalSlipStorage(tmp_path)
    ref = store.save(IMAGE, DIGEST)
    assert ref is not None
    written = Path(ref)
    assert written.exists()
    assert written.read_bytes() == IMAGE
    # Partitioned by year/month with the digest as the filename
    assert written.name == f"{DIGEST}.jpg"


def test_local_is_idempotent_for_same_slip(tmp_path: Path):
    store = LocalSlipStorage(tmp_path)
    first = store.save(IMAGE, DIGEST)
    second = store.save(IMAGE, DIGEST)
    assert first == second
    assert len(list(tmp_path.rglob("*.jpg"))) == 1


def test_local_returns_none_on_unwritable_path(tmp_path: Path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("regular file")
    store = LocalSlipStorage(blocker)
    assert store.save(IMAGE, DIGEST) is None


# --- null ----------------------------------------------------------------

def test_null_storage_returns_none():
    assert NullSlipStorage().save(IMAGE, DIGEST) is None


# --- supabase ------------------------------------------------------------

def _supabase_with(handler) -> SupabaseSlipStorage:
    store = SupabaseSlipStorage("https://proj.supabase.co", "secret-key")
    store._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"apikey": "secret-key", "Authorization": "Bearer secret-key"},
    )
    return store


def test_supabase_upload_returns_public_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content"] = request.content
        captured["upsert"] = request.headers.get("x-upsert")
        captured["type"] = request.headers.get("Content-Type")
        return httpx.Response(200, json={"Key": "slips/x"})

    url = _supabase_with(handler).save(IMAGE, DIGEST)

    assert "/storage/v1/object/slips/" in captured["url"]
    assert captured["content"] == IMAGE
    assert captured["upsert"] == "true"  # re-uploading a slip must not 409
    assert captured["type"] == "image/jpeg"
    assert url is not None
    assert url.startswith("https://proj.supabase.co/storage/v1/object/public/slips/")
    assert url.endswith(f"{DIGEST}.jpg")


def test_supabase_returns_none_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "no bucket"})

    assert _supabase_with(handler).save(IMAGE, DIGEST) is None


def test_supabase_returns_none_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    # A storage outage must never block booking a trade.
    assert _supabase_with(handler).save(IMAGE, DIGEST) is None


def test_supabase_honours_custom_bucket():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/object/receipts/" in str(request.url)
        return httpx.Response(200, json={})

    store = SupabaseSlipStorage("https://proj.supabase.co", "k", bucket="receipts")
    store._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert store.save(IMAGE, DIGEST) is not None


# --- factory -------------------------------------------------------------

def test_factory_prefers_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJfake")
    monkeypatch.setenv("IMAGES_DIR", "/tmp/slips")
    assert isinstance(create_slip_storage(), SupabaseSlipStorage)


def test_factory_falls_back_to_local(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path))
    assert isinstance(create_slip_storage(), LocalSlipStorage)


def test_factory_local_override_beats_supabase(monkeypatch, tmp_path):
    monkeypatch.setenv("SLIP_STORAGE", "local")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJfake")
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path))
    assert isinstance(create_slip_storage(), LocalSlipStorage)


def test_factory_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("SLIP_STORAGE", "none")
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path))
    assert isinstance(create_slip_storage(), NullSlipStorage)


def test_factory_null_when_nothing_configured():
    assert isinstance(create_slip_storage(), NullSlipStorage)
