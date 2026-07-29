"""Backward-compatible tests for legacy bot helpers removed in CE VAULT.

The Cursor API client remains in cursor_api.py; see tests/test_cursor_api.py.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Legacy Cursor bot handlers replaced by CE VAULT")
