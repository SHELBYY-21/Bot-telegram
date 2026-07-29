"""Per-chat session state for in-flight transactions."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from vault.models import PipelineStatus, TransactionDraft


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, PipelineStatus):
        return obj.value
    raise TypeError(f"Unsupported type: {type(obj)}")


@dataclass
class ChatSession:
    draft: TransactionDraft | None = None
    active_message_id: int | None = None
    mode: str = "idle"  # idle | confirm | edit | delete
    pending_delete_id: str | None = None

    def clear(self) -> None:
        self.draft = None
        self.active_message_id = None
        self.mode = "idle"
        self.pending_delete_id = None


class SessionStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.environ.get("SESSION_FILE", "state.json"))
        self._sessions: dict[str, ChatSession] = {}
        self._load()

    def get(self, chat_id: int) -> ChatSession:
        key = str(chat_id)
        if key not in self._sessions:
            self._sessions[key] = ChatSession()
        return self._sessions[key]

    def save(self) -> None:
        payload = {}
        for chat_id, session in self._sessions.items():
            if session.draft is None and session.mode == "idle":
                continue
            payload[chat_id] = {
                "mode": session.mode,
                "active_message_id": session.active_message_id,
                "pending_delete_id": session.pending_delete_id,
                "draft": self._draft_to_dict(session.draft) if session.draft else None,
            }
        self.path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return
        for chat_id, data in raw.items():
            session = ChatSession(
                mode=data.get("mode", "idle"),
                active_message_id=data.get("active_message_id"),
                pending_delete_id=data.get("pending_delete_id"),
            )
            if data.get("draft"):
                session.draft = self._draft_from_dict(data["draft"])
            self._sessions[chat_id] = session

    @staticmethod
    def _draft_to_dict(draft: TransactionDraft) -> dict[str, Any]:
        data = asdict(draft)
        data["status"] = draft.status.value
        data["thb"] = str(draft.thb)
        data["usdt"] = str(draft.usdt)
        data["buy_rate"] = str(draft.buy_rate)
        data["sell_rate"] = str(draft.sell_rate)
        return data

    @staticmethod
    def _draft_from_dict(data: dict[str, Any]) -> TransactionDraft:
        return TransactionDraft(
            ledger_id=data["ledger_id"],
            thb=Decimal(data["thb"]),
            usdt=Decimal(data["usdt"]),
            buy_rate=Decimal(data["buy_rate"]),
            sell_rate=Decimal(data["sell_rate"]),
            receiver_name=data.get("receiver_name", ""),
            bank=data.get("bank", ""),
            last4=data.get("last4", ""),
            ocr_confidence=data.get("ocr_confidence"),
            slip_hash=data.get("slip_hash"),
            slip_file_id=data.get("slip_file_id"),
            staff_id=data.get("staff_id"),
            status=PipelineStatus(data.get("status", PipelineStatus.RECEIVED.value)),
            duplicate_slip=data.get("duplicate_slip", False),
            repeated_receiver=data.get("repeated_receiver", False),
            low_confidence=data.get("low_confidence", False),
            source=data.get("source", "slip"),
            created_at=data.get("created_at", ""),
        )
