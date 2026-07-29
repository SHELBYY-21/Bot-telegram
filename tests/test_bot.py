import bot


def test_build_app_wires_handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY")
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "slips"))
    monkeypatch.setenv("BUY_RATE", "39.89")
    monkeypatch.setenv("SELL_RATE", "40.00")

    app = bot.build_app()
    assert "ledger" in app.bot_data
    assert "rates" in app.bot_data
    assert "ocr" in app.bot_data
    assert "sessions" in app.bot_data
    # Command + callback + photo + text handlers registered
    assert len(app.handlers[0]) >= 8
