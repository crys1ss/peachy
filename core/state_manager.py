"""Explicit Finite State Machine (FSM) governing Peachy application lifecycle.

Guarantees single overlay activation and enforces valid state transitions:
IDLE -> CAPTURING -> SELECTING -> ASKING -> THINKING -> ANSWERING / ERROR -> IDLE
"""

from __future__ import annotations

from enum import Enum, auto
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class AppState(Enum):
    """Discrete states of the Peachy assistant."""

    IDLE = "IDLE"
    CAPTURING = "CAPTURING"
    SELECTING = "SELECTING"
    ASKING = "ASKING"
    THINKING = "THINKING"
    ANSWERING = "ANSWERING"
    ERROR = "ERROR"


# Allowed state transitions: {from_state: {valid_to_states}}
_VALID_TRANSITIONS: dict[AppState, set[AppState]] = {
    AppState.IDLE: {AppState.CAPTURING},
    AppState.CAPTURING: {AppState.SELECTING, AppState.IDLE},
    AppState.SELECTING: {AppState.ASKING, AppState.IDLE},
    AppState.ASKING: {AppState.THINKING, AppState.IDLE},
    AppState.THINKING: {AppState.ANSWERING, AppState.ERROR, AppState.IDLE},
    AppState.ANSWERING: {AppState.THINKING, AppState.CAPTURING, AppState.IDLE},
    AppState.ERROR: {AppState.THINKING, AppState.IDLE},
}


class StateManager(QObject):
    """Central finite state machine for Peachy.

    Emits state_changed(old_state, new_state) and ensures activation is only
    honored when state is IDLE.
    """

    state_changed = Signal(AppState, AppState)
    activation_ignored = Signal(AppState)

    def __init__(self, parent: Optional[QObject] = None, initial_state: AppState = AppState.IDLE):
        super().__init__(parent)
        self._state: AppState = initial_state

    @property
    def state(self) -> AppState:
        """Current application state."""
        return self._state

    @property
    def is_idle(self) -> bool:
        """True if application is currently in IDLE state."""
        return self._state == AppState.IDLE

    def can_activate(self) -> bool:
        """Returns True only when the application is IDLE and ready for a new capture."""
        return self._state == AppState.IDLE

    def request_activation(self) -> bool:
        """Request to begin screen capture.

        Returns True if activation was accepted (state transitioned from IDLE to CAPTURING).
        Returns False if ignored because another capture/ask flow is already active.
        """
        if not self.can_activate():
            logger.info("Activation ignored: current state is %s (must be IDLE)", self._state.value)
            self.activation_ignored.emit(self._state)
            return False

        return self.transition_to(AppState.CAPTURING)

    def transition_to(self, new_state: AppState) -> bool:
        """Attempt to transition the application to new_state.

        Returns True if transition was valid and accepted, False if rejected.
        """
        if new_state == self._state:
            logger.debug("State transition to same state %s ignored.", new_state.value)
            return True

        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            logger.warning(
                "Invalid state transition rejected: %s -> %s",
                self._state.value,
                new_state.value,
            )
            return False

        old_state = self._state
        self._state = new_state
        logger.info("State transition: %s -> %s", old_state.value, new_state.value)
        self.state_changed.emit(old_state, new_state)
        return True

    def reset_to_idle(self) -> None:
        """Force a safe reset to IDLE state from any state."""
        if self._state == AppState.IDLE:
            return

        old_state = self._state
        self._state = AppState.IDLE
        logger.info("Forced reset to IDLE from %s", old_state.value)
        self.state_changed.emit(old_state, AppState.IDLE)

    def resume_conversation(self) -> None:
        """Transition into ANSWERING state when resuming a saved conversation from history."""
        if self._state == AppState.ANSWERING:
            return

        old_state = self._state
        self._state = AppState.ANSWERING
        logger.info("Resumed active conversation: %s -> ANSWERING", old_state.value)
        self.state_changed.emit(old_state, AppState.ANSWERING)
