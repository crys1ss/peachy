"""Peachy application settings management.

Settings are stored at %APPDATA%\\Peachy\\settings.json using atomic file operations.
The API key is NEVER stored here (Windows Credential Manager / keyring is used instead).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Application user settings with sensible defaults."""

    hotkey: str = "Ctrl+Shift+Space"
    model: str = "gemini-3.8-flash"
    pinned: bool = True
    double_tap_enabled: bool = False
    double_tap_interval_ms: int = 280
    launch_at_startup: bool = False
    answer_length: str = "short"  # "short" or "detailed"


def get_default_settings_dir() -> Path:
    """Return the platform settings directory for Peachy."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base_dir = Path(appdata)
    else:
        base_dir = Path.home() / ".config"
    return base_dir / "Peachy"


def get_default_settings_path() -> Path:
    """Return the default settings.json file path."""
    return get_default_settings_dir() / "settings.json"


def load_settings(path: Path | str | None = None) -> Settings:
    """Load settings from path or default location.

    If file is missing: returns default Settings.
    If file is corrupt or unreadable: backs it up to .bak and returns default Settings.
    Never crashes.
    """
    settings_path = Path(path) if path is not None else get_default_settings_path()

    if not settings_path.exists():
        logger.info("Settings file not found at %s. Using defaults.", settings_path)
        return Settings()

    try:
        content = settings_path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"Settings JSON root must be an object, got {type(data).__name__}")

        # Filter only known fields of Settings
        known_fields = {f.name for f in Settings.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return Settings(**filtered_data)
    except Exception as exc:
        logger.warning(
            "Failed to load settings from %s (%s). Creating backup and restoring defaults.",
            settings_path,
            exc,
        )
        backup_path = settings_path.with_suffix(".json.bak")
        try:
            shutil.copy2(settings_path, backup_path)
            logger.info("Corrupt settings backed up to %s", backup_path)
        except Exception as backup_exc:
            logger.error("Failed to backup corrupt settings file: %s", backup_exc)

        return Settings()


def save_settings(settings: Settings, path: Path | str | None = None) -> None:
    """Atomically save settings to disk using a temporary file and os.replace."""
    settings_path = Path(path) if path is not None else get_default_settings_path()

    settings_dir = settings_path.parent
    settings_dir.mkdir(parents=True, exist_ok=True)

    temp_path = settings_path.with_suffix(".tmp")
    data = asdict(settings)

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, settings_path)
        logger.debug("Settings successfully saved to %s", settings_path)
    except Exception as exc:
        logger.error("Failed to save settings atomically to %s: %s", settings_path, exc)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise
