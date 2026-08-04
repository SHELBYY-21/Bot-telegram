"""Durable storage for slip images.

Until now the bot downloaded a slip, ran OCR on the bytes, and dropped them —
``IMAGES_DIR`` was created but never written to, so the only surviving copy of
a slip lived on Telegram's servers behind a ``file_id``. For a ledger that
books real money that is a thin audit trail: the image is the evidence behind
every row.

Three backends, chosen from the environment:

- **Supabase Storage** when ``SUPABASE_URL`` + a server key are configured.
  Preferred — the bytes outlive both the container and the bot token.
- **Local disk** at ``IMAGES_DIR`` otherwise. Survives restarts only if that
  path is on a volume (on Fly it is; see fly.toml ``[mounts]``).
- **Null** when neither is available, so a misconfigured deploy degrades to
  today's behavior instead of refusing slips.

Saving is best-effort by design: a storage outage must not block an operator
from booking a trade. Failures are logged and return None.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger("ce_vault.storage")

DEFAULT_BUCKET = "slips"


def _object_path(digest: str, ext: str = "jpg") -> str:
    """``YYYY/MM/<sha256>.jpg`` — the digest dedupes re-uploads of one slip."""
    now = datetime.now(timezone.utc)
    return f"{now:%Y/%m}/{digest}.{ext}"


class SlipStorage(Protocol):
    def save(self, image_bytes: bytes, digest: str) -> str | None:
        """Persist the slip; return a durable reference, or None on failure."""
        ...


class NullSlipStorage:
    """No durable copy — the Telegram file_id remains the only reference."""

    def save(self, image_bytes: bytes, digest: str) -> str | None:
        return None


class LocalSlipStorage:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def save(self, image_bytes: bytes, digest: str) -> str | None:
        try:
            target = self.directory / _object_path(digest)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():  # identical slip already stored
                target.write_bytes(image_bytes)
            return str(target)
        except OSError as exc:
            logger.warning("could not write slip to %s: %s", self.directory, exc)
            return None


class SupabaseSlipStorage:
    """Uploads to a Supabase Storage bucket via the storage REST API."""

    def __init__(
        self,
        url: str,
        secret: str,
        bucket: str = DEFAULT_BUCKET,
        timeout: float = 30.0,
    ):
        self.base = url.rstrip("/")
        self.bucket = bucket
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "apikey": secret,
                "Authorization": f"Bearer {secret}",
            },
        )

    def close(self) -> None:
        self._client.close()

    def save(self, image_bytes: bytes, digest: str) -> str | None:
        path = _object_path(digest)
        try:
            resp = self._client.post(
                f"{self.base}/storage/v1/object/{self.bucket}/{path}",
                content=image_bytes,
                headers={
                    "Content-Type": "image/jpeg",
                    # Re-uploading the same slip should not error.
                    "x-upsert": "true",
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("slip upload failed: %s", exc)
            return None

        if resp.status_code >= 400:
            logger.warning(
                "slip upload rejected (%s): %s", resp.status_code, resp.text[:200]
            )
            return None
        return f"{self.base}/storage/v1/object/public/{self.bucket}/{path}"


def create_slip_storage() -> SlipStorage:
    """Pick a backend from the environment. Never raises."""
    from ce_vault.store import _supabase_secret

    backend = (os.environ.get("SLIP_STORAGE") or "").strip().lower()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    secret = _supabase_secret()
    bucket = (os.environ.get("SUPABASE_BUCKET") or "").strip() or DEFAULT_BUCKET
    images_dir = (os.environ.get("IMAGES_DIR") or "").strip()

    if backend == "none":
        logger.info("slip storage: disabled")
        return NullSlipStorage()

    if backend != "local" and url and secret:
        logger.info("slip storage: supabase bucket %r", bucket)
        return SupabaseSlipStorage(url, secret, bucket)

    if images_dir:
        logger.info("slip storage: local %s", images_dir)
        return LocalSlipStorage(images_dir)

    logger.info("slip storage: disabled (no SUPABASE_URL or IMAGES_DIR)")
    return NullSlipStorage()
