"""Tests for Settings new v2 fields and validation clamping."""

from __future__ import annotations

import json
from pathlib import Path
from config.settings import Settings, load_settings, save_settings


def test_settings_v2_defaults():
    """All 7 new fields from REDESIGN.md section 7 have correct defaults."""
    s = Settings()
    assert s.display_name == ""
    assert s.accent == "peach"
    assert s.font_scale == 100
    assert s.sidebar_collapsed is False
    assert s.main_window_geometry == ""
    assert s.close_to_tray is True
    assert s.fallback_models_enabled is True


def test_settings_v2_round_trip(tmp_path: Path):
    """Saving and loading custom v2 settings values preserves all fields."""
    settings_file = tmp_path / "settings.json"

    custom = Settings(
        display_name="Zidane",
        accent="coral",
        font_scale=110,
        sidebar_collapsed=True,
        main_window_geometry="AQAAABkAAABzAAA...",
        close_to_tray=False,
        fallback_models_enabled=False,
    )
    save_settings(custom, settings_file)

    loaded = load_settings(settings_file)
    assert loaded.display_name == "Zidane"
    assert loaded.accent == "coral"
    assert loaded.font_scale == 110
    assert loaded.sidebar_collapsed is True
    assert loaded.main_window_geometry == "AQAAABkAAABzAAA..."
    assert loaded.close_to_tray is False
    assert loaded.fallback_models_enabled is False


def test_settings_v2_validation_clamping(tmp_path: Path):
    """Unknown accent and font_scale values are clamped to defaults."""
    settings_file = tmp_path / "settings.json"

    invalid_data = {
        "accent": "neon-purple",  # Invalid
        "font_scale": 999,        # Invalid
        "display_name": "Test User",
        "sidebar_collapsed": True,
        "close_to_tray": "not-a-bool",  # Should be converted to bool True
        "unknown_custom_field": "disallowed",
    }
    settings_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    loaded = load_settings(settings_file)
    assert loaded.accent == "peach"  # Clamped to default
    assert loaded.font_scale == 100  # Clamped to default
    assert loaded.display_name == "Test User"
    assert loaded.sidebar_collapsed is True
    assert loaded.close_to_tray is True
    assert not hasattr(loaded, "unknown_custom_field")


def test_settings_v2_valid_accents_and_scales(tmp_path: Path):
    """All supported accents (peach, coral, rose, lavender) and font scales (90, 100, 110, 125) are accepted."""
    settings_file = tmp_path / "settings.json"

    for acc in ("peach", "coral", "rose", "lavender"):
        settings_file.write_text(json.dumps({"accent": acc}), encoding="utf-8")
        assert load_settings(settings_file).accent == acc

    for scale in (90, 100, 110, 125):
        settings_file.write_text(json.dumps({"font_scale": scale}), encoding="utf-8")
        assert load_settings(settings_file).font_scale == scale
