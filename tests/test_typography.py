"""Design primitives: boxed_title, status_badge, section, divider width."""

import re

from ce_vault.formatting import ledger_id
from ce_vault.typography import (
    BADGE_MAP,
    boxed_title,
    divider,
    section,
    status_badge,
)


def test_boxed_title_uses_rounded_corners():
    out = boxed_title("Confirm Transaction")
    assert "╭" in out and "╮" in out
    assert "╰" in out and "╯" in out
    assert "Confirm Transaction" in out
    # Wrapped in <pre> so Telegram preserves the frame spacing
    assert out.startswith("<pre>")


def test_boxed_title_preserves_case():
    """Author owns case — mixed Title Case / UPPERCASE per mockup."""
    upper = boxed_title("CE VAULT", subtitle="Financial Operations")
    assert "CE VAULT" in upper
    assert "Financial Operations" in upper
    # Title Case must survive verbatim (not be upper-cased into CONFIRM ...)
    mixed = boxed_title("Confirm Transaction")
    assert "Confirm Transaction" in mixed
    assert "CONFIRM TRANSACTION" not in mixed


def test_status_badge_maps_ui_status_names():
    assert "VERIFIED" in status_badge("OCR VERIFIED")
    assert "WAITING" in status_badge("WAITING USDT")
    assert "SETTLED" in status_badge("SETTLED")
    assert "PROCESSING" in status_badge("RECEIVED")
    assert "REVIEW" in status_badge("CANCELLED")


def test_status_badge_right_alignment_carries_value():
    out = status_badge("OCR VERIFIED", right="98.4%")
    assert "VERIFIED" in out
    assert "98.4%" in out
    # Right-hand value is monospaced
    assert "<code>98.4%</code>" in out


def test_section_stacks_label_value():
    out = section("Amount", "500.00 THB")
    # Label / blank / mono value — three-line stack
    lines = out.split("\n")
    assert lines[0] == "<i>Amount</i>"
    assert lines[1] == ""
    assert lines[2] == "<code>500.00 THB</code>"


def test_section_extra_appears_beneath_value():
    out = section("Receiver", "SCB ••••3376", extra="นายสมชาย")
    assert "SCB" in out
    assert "นายสมชาย" in out
    # extra is escaped body text, not monospaced
    assert "<code>นายสมชาย</code>" not in out


def test_divider_matches_mockup_width():
    """Card width in the mockups is 32 chars — divider aligns."""
    assert len(divider()) == 32
    assert divider() == "─" * 32


def test_badge_map_covers_status_pipeline():
    for ui_status in ("RECEIVED", "OCR VERIFIED", "WAITING USDT", "SETTLED"):
        assert ui_status in BADGE_MAP


def test_ledger_id_format_ce_prefix_random_suffix():
    """CE-YYYYMMDD-XXXX; suffix is 4-char no-ambiguity alphanum."""
    ids = {ledger_id() for _ in range(20)}
    for lid in ids:
        assert re.fullmatch(r"CE-\d{8}-[23456789A-HJ-NP-Z]{4}", lid), lid
    # Random suffix ⇒ 20 IDs should not all collide
    assert len(ids) >= 15
