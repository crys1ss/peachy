"""Unit tests for sound effects and Windows motion reduction checking."""

import pytest

from config.settings import Settings
from core.win32 import get_client_area_animation_enabled
from ui.peachy_popup import should_animate
from ui.sound import SoundManager, get_sound_manager


def test_sound_manager_mute_and_volume(qapp):
    """Verify SoundManager volume scaling, mute state, and bidirectional settings sync."""
    settings = Settings(sound_enabled=True, sound_volume=40)
    mgr = SoundManager(settings=settings)

    assert mgr.get_volume() == 40
    assert not mgr.is_muted

    # Set volume
    mgr.set_volume(80)
    assert mgr.get_volume() == 80
    assert settings.sound_volume == 80

    # Volume bounds clamping
    mgr.set_volume(150)
    assert mgr.get_volume() == 100
    mgr.set_volume(-20)
    assert mgr.get_volume() == 0

    # Mute toggle
    mgr.set_muted(True)
    assert mgr.is_muted
    assert not settings.sound_enabled

    # Play when muted returns False
    assert mgr.play("open") is False


def test_sound_manager_rate_limiting(qapp):
    """Verify SoundManager rate limits calls within 150 ms window."""
    settings = Settings(sound_enabled=True, sound_volume=50)
    mgr = SoundManager(settings=settings)

    # First trigger (whether winsound or QSoundEffect available)
    # Even if audio device is absent or mock, timestamp is recorded
    mgr.play("open")

    # Immediate second trigger must be suppressed by 150 ms rate limit
    assert mgr.play("open") is False


def test_motion_reduction_check():
    """Verify should_animate respects settings.reduce_motion and Win32 animations."""
    # When reduce_motion is True, should_animate is strictly False
    s_reduce = Settings(reduce_motion=True)
    assert should_animate(s_reduce) is False

    # When reduce_motion is False, should_animate queries OS setting
    s_normal = Settings(reduce_motion=False)
    os_anim = get_client_area_animation_enabled()
    assert should_animate(s_normal) == os_anim



def test_sound_manager_rereads_updated_settings(qapp):
    """get_sound_manager(new_settings) re-reads sound_enabled and sound_volume live."""
    s1 = Settings(sound_enabled=True, sound_volume=25)
    mgr1 = get_sound_manager(s1)
    assert mgr1.get_volume() == 25
    assert not mgr1.is_muted

    # Pass updated settings
    s2 = Settings(sound_enabled=False, sound_volume=85)
    mgr2 = get_sound_manager(s2)
    assert mgr2 is mgr1
    assert mgr2.get_volume() == 85
    assert mgr2.is_muted is True
