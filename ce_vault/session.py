"""Per-chat console session — tracks editable message ids."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChatSession:
    active_ledger_id: str | None = None
    console_message_id: int | None = None
    mode: str = "idle"  # idle | edit | await_usdt
    draft: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, ChatSession] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            raw = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            self._data = {}
            return
        sessions = raw.get("sessions", raw)
        self._data = {}
        for chat_id, payload in sessions.items():
            if isinstance(payload, dict):
                self._data[str(chat_id)] = ChatSession(
                    active_ledger_id=payload.get("active_ledger_id"),
                    console_message_id=payload.get("console_message_id"),
                    mode=payload.get("mode", "idle"),
                    draft=payload.get("draft") or {},
                )

    def save(self) -> None:
        payload = {
            "sessions": {cid: asdict(sess) for cid, sess in self._data.items()}
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def get(self, chat_id: int) -> ChatSession:
        key = str(chat_id)
        if key not in self._data:
            self._data[key] = ChatSession()
        return self._data[key]

    def set(self, chat_id: int, session: ChatSession) -> None:
        self._data[str(chat_id)] = session
        self.save()

    def update(self, chat_id: int, **fields: Any) -> ChatSession:
        sess = self.get(chat_id)
        for k, v in fields.items():
            setattr(sess, k, v)
        self.save()
        return sess
