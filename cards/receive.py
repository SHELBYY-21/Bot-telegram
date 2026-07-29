"""Receive and loading cards."""

from __future__ import annotations

from typing import Any

from cards.base import SEP, header, status_line


def receive_card(tx: dict[str, Any]) -> str:
  lines = [
      header(tx.get("id")),
      "",
      status_line("RECEIVED"),
      "",
      "Slip received",
      "Processing…",
      SEP,
  ]
  return "\n".join(lines)


def loading_card(ledger_id: str, stage: str = "OCR") -> str:
  lines = [
      header(ledger_id),
      "",
      status_line("RECEIVED"),
      "",
      f"<i>{stage} in progress</i>",
      "▁▂▃▄▅▆▇█",
      SEP,
  ]
  return "\n".join(lines)


def progress_card(ledger_id: str, step: int, total: int, label: str) -> str:
  filled = "█" * step + "░" * (total - step)
  lines = [
      header(ledger_id),
      "",
      f"<i>{label}</i>",
      filled,
      f"{step}/{total}",
      SEP,
  ]
  return "\n".join(lines)
