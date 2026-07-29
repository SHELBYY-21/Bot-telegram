"""Per-chat session state for message editing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChatSession:
    message_id: int | None = None
    ledger_id: str | None = None
    mode: str = "idle"  # idle | confirm | edit | delete
    card: str | None = None


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self._data = {}

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2))

    def get(self, chat_id: int) -> ChatSession:
        raw = self._data.get(str(chat_id), {})
        return ChatSession(
            message_id=raw.get("message_id"),
            ledger_id=raw.get("ledger_id"),
            mode=raw.get("mode", "idle"),
            card=raw.get("card"),
        )

    def set(self, chat_id: int, session: ChatSession) -> None:
        self._data[str(chat_id)] = asdict(session)
        self.save()

    def clear(self, chat_id: int) -> None:
        self._data.pop(str(chat_id), None)
        self.save()
