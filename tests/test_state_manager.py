"""Unit tests for core/state_manager.py."""

import pytest
from core.state_manager import AppState, StateManager


def test_initial_state_is_idle():
    """Verify initial state is IDLE."""
    sm = StateManager()
    assert sm.state == AppState.IDLE
    assert sm.is_idle is True
    assert sm.can_activate() is True


def test_valid_lifecycle_transitions():
    """Test standard happy path through states."""
    sm = StateManager()
    state_changes = []
    sm.state_changed.connect(lambda old, new: state_changes.append((old, new)))

    # IDLE -> CAPTURING
    assert sm.request_activation() is True
    assert sm.state == AppState.CAPTURING

    # CAPTURING -> SELECTING
    assert sm.transition_to(AppState.SELECTING) is True
    assert sm.state == AppState.SELECTING

    # SELECTING -> ASKING
    assert sm.transition_to(AppState.ASKING) is True
    assert sm.state == AppState.ASKING

    # ASKING -> THINKING
    assert sm.transition_to(AppState.THINKING) is True
    assert sm.state == AppState.THINKING

    # THINKING -> ANSWERING
    assert sm.transition_to(AppState.ANSWERING) is True
    assert sm.state == AppState.ANSWERING

    # ANSWERING -> IDLE
    assert sm.transition_to(AppState.IDLE) is True
    assert sm.state == AppState.IDLE

    assert len(state_changes) == 6
    assert state_changes[0] == (AppState.IDLE, AppState.CAPTURING)
    assert state_changes[-1] == (AppState.ANSWERING, AppState.IDLE)


def test_error_state_and_retry():
    """Test transitions to and from ERROR state."""
    sm = StateManager(initial_state=AppState.THINKING)

    # THINKING -> ERROR
    assert sm.transition_to(AppState.ERROR) is True
    assert sm.state == AppState.ERROR

    # ERROR -> THINKING (retry)
    assert sm.transition_to(AppState.THINKING) is True
    assert sm.state == AppState.THINKING

    # ERROR -> IDLE (close)
    sm.transition_to(AppState.ERROR)
    assert sm.transition_to(AppState.IDLE) is True
    assert sm.state == AppState.IDLE


def test_invalid_transitions_rejected():
    """Verify illegal transitions are rejected and do not change state."""
    sm = StateManager(initial_state=AppState.IDLE)

    # Cannot jump from IDLE to SELECTING, ASKING, THINKING, or ANSWERING directly
    assert sm.transition_to(AppState.SELECTING) is False
    assert sm.state == AppState.IDLE

    assert sm.transition_to(AppState.ANSWERING) is False
    assert sm.state == AppState.IDLE

    # Transition to CAPTURING
    sm.transition_to(AppState.CAPTURING)
    # Cannot jump from CAPTURING to ASKING directly
    assert sm.transition_to(AppState.ASKING) is False
    assert sm.state == AppState.CAPTURING


def test_activation_ignored_when_not_idle():
    """Verify activation is rejected when state is not IDLE, preventing duplicate overlays."""
    sm = StateManager(initial_state=AppState.SELECTING)
    ignored_signals = []
    sm.activation_ignored.connect(lambda s: ignored_signals.append(s))

    assert sm.can_activate() is False
    assert sm.request_activation() is False
    assert sm.state == AppState.SELECTING
    assert len(ignored_signals) == 1
    assert ignored_signals[0] == AppState.SELECTING


def test_reset_to_idle():
    """Verify reset_to_idle safely returns to IDLE from any state."""
    sm = StateManager(initial_state=AppState.THINKING)
    assert sm.state == AppState.THINKING

    sm.reset_to_idle()
    assert sm.state == AppState.IDLE
    assert sm.is_idle is True

    # Calling when already IDLE is a no-op
    sm.reset_to_idle()
    assert sm.state == AppState.IDLE
