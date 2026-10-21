"""Unit tests for config/settings.py."""

from pathlib import Path
import json
import pytest

from config.settings import Settings, load_settings, save_settings


def test_settings_defaults():
    """Verify default setting values."""
    s = Settings()
    assert s.hotkey == "Ctrl+Shift+Space"
    assert s.model == "gemini-2.5-flash"
    assert s.pinned is True
    assert s.double_tap_enabled is False
    assert s.double_tap_interval_ms == 280
    assert s.launch_at_startup is False
    assert s.answer_length == "short"
    # Ensure no API key field exists on Settings
    assert not hasattr(s, "api_key")
    assert not hasattr(s, "gemini_api_key")


def test_save_and_load_round_trip(tmp_path: Path):
    """Verify saving settings to JSON and reading them back."""
    settings_file = tmp_path / "settings.json"
    s1 = Settings(
        hotkey="Alt+Q",
        model="gemini-2.5-pro",
        pinned=False,
        double_tap_enabled=True,
        double_tap_interval_ms=350,
        launch_at_startup=True,
        answer_length="detailed",
    )

    save_settings(s1, settings_file)
    assert settings_file.exists()

    s2 = load_settings(settings_file)
    assert s2 == s1


def test_missing_settings_file(tmp_path: Path):
    """Missing settings file should return default Settings without error."""
    missing_path = tmp_path / "nonexistent" / "settings.json"
    s = load_settings(missing_path)
    assert s == Settings()


def test_corrupt_file_recovery(tmp_path: Path):
    """Corrupt settings file should be backed up to .bak and fall back to defaults."""
    settings_file = tmp_path / "settings.json"
    backup_file = tmp_path / "settings.json.bak"

    # Write corrupt JSON
    settings_file.write_text("{ this is not valid json : [[", encoding="utf-8")

    s = load_settings(settings_file)
    # Returns default without crashing
    assert s == Settings()
    # Backup file should have been created
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == "{ this is not valid json : [["


def test_non_dict_json_recovery(tmp_path: Path):
    """JSON that is a list rather than an object should be backed up and recovered."""
    settings_file = tmp_path / "settings.json"
    backup_file = tmp_path / "settings.json.bak"

    settings_file.write_text("[1, 2, 3]", encoding="utf-8")

    s = load_settings(settings_file)
    assert s == Settings()
    assert backup_file.exists()


def test_atomic_save_leaves_no_temp_file(tmp_path: Path):
    """Verify atomic save removes temporary file upon completion."""
    settings_file = tmp_path / "settings.json"
    temp_file = tmp_path / "settings.tmp"

    save_settings(Settings(), settings_file)
    assert settings_file.exists()
    assert not temp_file.exists()


def test_unknown_fields_in_json_are_ignored(tmp_path: Path):
    """Forward-compatibility: extra fields in JSON shouldn't break loading."""
    settings_file = tmp_path / "settings.json"
    data = {
        "hotkey": "Ctrl+Shift+Space",
        "unknown_future_field": "some_value",
    }
    settings_file.write_text(json.dumps(data), encoding="utf-8")

    s = load_settings(settings_file)
    assert s.hotkey == "Ctrl+Shift+Space"
    assert not hasattr(s, "unknown_future_field")
