"""Sound effects manager for Peachy.

Features:
- Preloaded audio via PySide6.QtMultimedia (QSoundEffect) for zero playback latency
- Windows fallback via winsound (SND_FILENAME | SND_ASYNC | SND_NODEFAULT)
- 150 ms rate limiting per sound to prevent audio spam
- Volume scaling and mute toggle
- Resilient: missing or corrupted audio files never raise or crash
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import time
from typing import Dict, Optional

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore

from PySide6.QtCore import QObject, QUrl
try:
    from PySide6.QtMultimedia import QSoundEffect
    HAS_QT_MULTIMEDIA = True
except ImportError:
    QSoundEffect = None  # type: ignore
    HAS_QT_MULTIMEDIA = False

from config.settings import Settings

logger = logging.getLogger(__name__)

SOUND_NAMES = ("open", "capture", "answer", "copy", "error")
RATE_LIMIT_SECONDS = 0.150  # 150 ms minimum between triggers of the same sound


def get_sound_resource_dir() -> Path:
    """Resolve directory containing sound WAV files."""
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
        candidate = base_dir / "resources" / "sounds"
        if candidate.exists():
            return candidate
        exe_dir = Path(sys.executable).resolve().parent
        candidate_exe = exe_dir / "resources" / "sounds"
        if candidate_exe.exists():
            return candidate_exe
    return Path(__file__).resolve().parent.parent / "resources" / "sounds"


class SoundManager(QObject):
    """Manages audio playback, rate-limiting, and volume for UI interactions."""

    def __init__(self, settings: Optional[Settings] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.settings = settings
        self._sound_dir = get_sound_resource_dir()
        self._effects: Dict[str, Optional[QSoundEffect]] = {}
        self._last_played_time: Dict[str, float] = {}

        # Mute state: True if muted or if settings disabled
        self._muted: bool = False
        if settings is not None:
            self._muted = not getattr(settings, "sound_enabled", True)

        # Volume state: 0 to 100
        vol = getattr(settings, "sound_volume", 35) if settings else 35
        self._volume: int = max(0, min(100, int(vol)))

        self._preload_sounds()

    def _preload_sounds(self) -> None:
        """Preload sound effects into memory for instant playback."""
        if not HAS_QT_MULTIMEDIA:
            logger.debug("QtMultimedia not available. SoundManager will use Win32 winsound fallback.")
            return

        for name in SOUND_NAMES:
            file_path = self._sound_dir / f"{name}.wav"
            if file_path.exists():
                try:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(file_path)))
                    effect.setVolume(self._volume / 100.0)
                    self._effects[name] = effect
                except Exception as exc:
                    logger.debug("Could not preload QSoundEffect for '%s': %s", name, exc)
                    self._effects[name] = None
            else:
                self._effects[name] = None

    @property
    def is_muted(self) -> bool:
        """Return True if sound is currently muted."""
        return self._muted

    def set_muted(self, muted: bool) -> None:
        """Toggle audio mute state."""
        self._muted = bool(muted)
        if self.settings is not None:
            self.settings.sound_enabled = not self._muted

    def set_volume(self, volume: int | float) -> None:
        """Set volume percentage (0 to 100)."""
        self._volume = max(0, min(100, int(volume)))
        if self.settings is not None:
            self.settings.sound_volume = self._volume

        qt_vol = self._volume / 100.0
        for effect in self._effects.values():
            if effect is not None:
                try:
                    effect.setVolume(qt_vol)
                except Exception:
                    pass

    def get_volume(self) -> int:
        """Get current volume percentage (0 to 100)."""
        return self._volume

    def update_settings(self, settings: Settings) -> None:
        """Update live settings, applying sound_enabled and sound_volume."""
        self.settings = settings
        if hasattr(settings, "sound_enabled"):
            self._muted = not getattr(settings, "sound_enabled", True)
        if hasattr(settings, "sound_volume"):
            vol = getattr(settings, "sound_volume", 35)
            self.set_volume(vol)

    def play(self, sound_name: str) -> bool:
        """Play a named sound effect with rate limiting and fallback.

        Args:
            sound_name: One of 'open', 'capture', 'answer', 'copy', 'error'.

        Returns:
            True if sound was played, False if muted, rate-limited, or failed.
        """
        if self._muted or self._volume <= 0:
            return False

        now = time.monotonic()
        last_played = self._last_played_time.get(sound_name, 0.0)
        if now - last_played < RATE_LIMIT_SECONDS:
            logger.debug("Sound '%s' suppressed by rate limit (%d ms ago)", sound_name, int((now - last_played) * 1000))
            return False

        # Mark timestamp immediately to rate-limit calls
        self._last_played_time[sound_name] = now

        # 1. Try QtMultimedia QSoundEffect
        effect = self._effects.get(sound_name)
        if effect is not None:
            try:
                if effect.status() != QSoundEffect.Status.Error:
                    effect.setVolume(self._volume / 100.0)
                    effect.play()
                    return True
            except Exception as exc:
                logger.debug("QSoundEffect play failed for '%s': %s", sound_name, exc)

        # 2. Fallback to Win32 winsound
        sound_path = self._sound_dir / f"{sound_name}.wav"
        if not sound_path.exists():
            logger.debug("Sound file '%s' does not exist at %s", sound_name, sound_path)
            return False

        if winsound is not None:
            try:
                flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                winsound.PlaySound(str(sound_path), flags)
                return True
            except Exception as win_exc:
                logger.debug("winsound PlaySound failed for '%s': %s", sound_name, win_exc)

        return False


_GLOBAL_SOUND_MANAGER: Optional[SoundManager] = None


def get_sound_manager(settings: Optional[Settings] = None) -> SoundManager:
    """Return shared global SoundManager instance, updating settings if provided."""
    global _GLOBAL_SOUND_MANAGER
    if _GLOBAL_SOUND_MANAGER is None:
        _GLOBAL_SOUND_MANAGER = SoundManager(settings)
    elif settings is not None:
        _GLOBAL_SOUND_MANAGER.update_settings(settings)
    return _GLOBAL_SOUND_MANAGER
