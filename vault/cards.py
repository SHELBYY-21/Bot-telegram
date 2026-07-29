"""Premium card renderer — one card per screen, typography-first."""

from __future__ import annotations

import html
from decimal import Decimal

from vault.models import LedgerRecord, PipelineStatus, ReceiverHistory, TransactionDraft

SEP = "────────────────────────────────"


class CardRenderer:
    BRAND = "CE VAULT"
    SUBTITLE = "Secure Ledger"

    @staticmethod
    def mono(value: str | Decimal | float | int) -> str:
        return f"<code>{html.escape(str(value))}</code>"

    @staticmethod
    def label(text: str) -> str:
        return f"<i>{html.escape(text)}</i>"

    @classmethod
    def header(cls, ledger_id: str | None = None) -> str:
        lines = [
            f"<b>{cls.BRAND}</b>",
            cls.label(cls.SUBTITLE),
        ]
        if ledger_id:
            lines.append(f"{cls.label('Ledger ID')}  {cls.mono(ledger_id)}")
        lines.append(SEP)
        return "\n".join(lines)

    @classmethod
    def status_pipeline(cls, active: PipelineStatus) -> str:
        lines = []
        for status in PipelineStatus.ordered():
            marker = "●"
            text = status.value
            if status == active:
                lines.append(f"<b>{marker} {html.escape(text)}</b>")
            else:
                lines.append(f"{marker} {html.escape(text)}")
        return "\n".join(lines)

    @classmethod
    def receive_card(cls, draft: TransactionDraft) -> str:
        return "\n".join(
            [
                cls.header(draft.ledger_id),
                cls.status_pipeline(draft.status),
                "",
                cls.label("Awaiting input"),
                "",
                cls.label("Send a transfer slip"),
                "or",
                cls.label("Enter USDT amount"),
                "",
                SEP,
            ]
        )

    @classmethod
    def loading_card(cls, ledger_id: str, stage: str, progress: int) -> str:
        bar_filled = max(0, min(progress, 10))
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        return "\n".join(
            [
                cls.header(ledger_id),
                "",
                cls.label("Processing"),
                "",
                f"{cls.mono(stage)}",
                "",
                f"{cls.mono(bar)}  {cls.mono(f'{progress * 10}%')}",
                "",
                SEP,
            ]
        )

    @classmethod
    def ocr_card(cls, draft: TransactionDraft) -> str:
        confidence = draft.ocr_confidence or 0.0
        status = "Verified" if confidence >= 90 else "Review Required"
        lines = [
            cls.header(draft.ledger_id),
            cls.status_pipeline(PipelineStatus.OCR_VERIFIED),
            "",
            f"{cls.label('Vision')}           {cls.mono(f'{confidence:.1f}%')}",
            f"{cls.label('Receiver')}         {html.escape(draft.receiver_name or '—')}",
            f"{cls.label('Bank')}              {html.escape(draft.bank or '—')}",
            f"{cls.label('Last4')}             {cls.mono(draft.last4 or '—')}",
            f"{cls.label('Detected Amount')}  {cls.mono(draft.thb)}",
            f"{cls.label('Status')}            {html.escape(status)}",
        ]
        if draft.duplicate_slip:
            lines.append("")
            lines.append(f"<b>Duplicate slip detected</b>")
        if draft.repeated_receiver:
            lines.append(f"<b>Repeated receiver</b>")
        if draft.low_confidence:
            lines.append(f"<b>Confidence below 90%</b>")
        lines.extend(["", SEP])
        return "\n".join(lines)

    @classmethod
    def transaction_card(cls, draft: TransactionDraft) -> str:
        profit_sign = "+" if draft.profit_pct >= 0 else ""
        lines = [
            cls.header(draft.ledger_id),
            cls.status_pipeline(draft.status),
            "",
            f"{cls.label('THB')}                {cls.mono(f'{draft.thb:,.2f}')}",
            f"{cls.label('USDT')}              {cls.mono(f'{draft.usdt:.4f}')}",
            "",
            f"{cls.label('Buy Rate')}          {cls.mono(draft.buy_rate)}",
            f"{cls.label('Sell Rate')}         {cls.mono(draft.sell_rate)}",
            f"{cls.label('Profit')}            {cls.mono(f'{profit_sign}{draft.profit_pct}%')}",
            "",
            f"{cls.label('Receiver')}         {html.escape(draft.masked_receiver)}",
        ]
        if draft.ocr_confidence is not None:
            lines.append(
                f"{cls.label('Confidence')}       {cls.mono(f'{draft.ocr_confidence:.1f}%')}"
            )
        lines.extend(["", SEP])
        return "\n".join(lines)

    @classmethod
    def history_card(cls, history: ReceiverHistory) -> str:
        return "\n".join(
            [
                cls.header(),
                cls.label("Receiver History"),
                "",
                f"<b>{html.escape(history.masked_account)}</b>",
                "",
                f"{cls.mono(history.transaction_count)} Transactions",
                f"{cls.mono(f'{history.total_thb:,.0f}')} THB",
                f"{cls.mono(f'{history.total_usdt:,.3f}')} USDT",
                "",
                f"{cls.label('First Seen')}        {cls.mono(history.first_seen)}",
                f"{cls.label('Last Seen')}         {cls.mono(history.last_seen)}",
                f"{cls.label('Risk')}              {cls.mono(history.risk.value)}",
                "",
                SEP,
            ]
        )

    @classmethod
    def success_card(cls, record: LedgerRecord) -> str:
        profit_sign = "+" if record.profit_pct >= 0 else ""
        lines = [
            cls.header(record.ledger_id),
            cls.status_pipeline(PipelineStatus.SETTLED),
            "",
            f"<b>SETTLED</b>",
            "",
            f"{cls.label('Ledger ID')}         {cls.mono(record.ledger_id)}",
            f"{cls.label('Profit')}            {cls.mono(f'{profit_sign}{record.profit_pct}%')}",
        ]
        if record.balance_thb is not None and record.balance_usdt is not None:
            lines.extend(
                [
                    "",
                    f"{cls.label('Updated Balance')}",
                    f"{cls.mono(f'{record.balance_thb:,.2f}')} THB",
                    f"{cls.mono(f'{record.balance_usdt:,.4f}')} USDT",
                ]
            )
        lines.extend(["", SEP, "", cls.label("Done.")])
        return "\n".join(lines)

    @classmethod
    def error_card(cls, problem: str, cause: str, action: str) -> str:
        return "\n".join(
            [
                cls.header(),
                cls.label("Error"),
                "",
                f"{cls.label('Problem')}           {html.escape(problem)}",
                f"{cls.label('Cause')}             {html.escape(cause)}",
                f"{cls.label('Action')}            {html.escape(action)}",
                "",
                SEP,
            ]
        )

    @classmethod
    def edit_card(cls, draft: TransactionDraft) -> str:
        return "\n".join(
            [
                cls.header(draft.ledger_id),
                cls.label("Edit Transaction"),
                "",
                f"{cls.label('THB')}                {cls.mono(f'{draft.thb:,.2f}')}",
                f"{cls.label('USDT')}              {cls.mono(f'{draft.usdt:.4f}')}",
                f"{cls.label('Receiver')}         {html.escape(draft.masked_receiver)}",
                "",
                cls.label("Reply with new USDT amount"),
                "or send an updated slip.",
                "",
                SEP,
            ]
        )

    @classmethod
    def delete_card(cls, ledger_id: str) -> str:
        return "\n".join(
            [
                cls.header(ledger_id),
                cls.label("Delete Transaction"),
                "",
                cls.label("This action cannot be undone."),
                "",
                SEP,
            ]
        )

    @classmethod
    def dashboard_card(cls, totals: dict, rates: tuple[Decimal, Decimal, Decimal]) -> str:
        buy, sell, profit = rates
        return "\n".join(
            [
                cls.header(),
                cls.label("Operations Console"),
                "",
                f"{cls.label('Settled')}           {cls.mono(totals['count'])}",
                f"{cls.label('Volume THB')}       {cls.mono(f'{totals['thb']:,.2f}')}",
                f"{cls.label('Volume USDT')}     {cls.mono(f'{totals['usdt']:,.4f}')}",
                "",
                f"{cls.label('Buy Rate')}          {cls.mono(buy)}",
                f"{cls.label('Sell Rate')}         {cls.mono(sell)}",
                f"{cls.label('Spread')}           {cls.mono(f'+{profit}%')}",
                "",
                cls.label("Send slip  ·  USDT amount  ·  /ledger"),
                "",
                SEP,
            ]
        )
