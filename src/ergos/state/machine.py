"""Conversation state machine with enforced transitions."""

import asyncio
import logging
from typing import Optional

from ergos.state.events import (
    ConversationState,
    StateChangeEvent,
    StateChangeCallback,
)

logger = logging.getLogger(__name__)


# Valid state transitions table
# Format: {from_state: [valid_to_states]}
VALID_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.IDLE: {
        ConversationState.LISTENING,  # Start listening
    },
    ConversationState.LISTENING: {
        ConversationState.PROCESSING,  # Speech ended, start STT/LLM
        ConversationState.IDLE,  # Stop/timeout
    },
    ConversationState.PROCESSING: {
        ConversationState.SPEAKING,  # LLM response ready, start TTS
        ConversationState.LISTENING,  # Barge-in during processing
    },
    ConversationState.SPEAKING: {
        ConversationState.LISTENING,  # TTS complete or barge-in
        ConversationState.IDLE,  # Stop
    },
}


class ConversationStateMachine:
    """
    Manages conversation state with enforced transitions.

    This is the single source of truth for conversation flow.
    Invalid transitions are rejected, and callbacks are notified
    on successful transitions.

    Valid transitions:
        IDLE → LISTENING (start listening)
        LISTENING → PROCESSING (speech ended, start STT/LLM)
        LISTENING → IDLE (stop/timeout)
        PROCESSING → SPEAKING (LLM response ready, start TTS)
        PROCESSING → LISTENING (barge-in during processing)
        SPEAKING → LISTENING (TTS complete or barge-in)
        SPEAKING → IDLE (stop)
    """

    def __init__(self):
        self._state = ConversationState.IDLE
        self._callbacks: list[StateChangeCallback] = []
        self._transition_lock = asyncio.Lock()

    @property
    def state(self) -> ConversationState:
        """Current conversation state."""
        return self._state

    async def transition_to(
        self,
        new_state: ConversationState,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Attempt to transition to a new state.

        Args:
            new_state: The target state to transition to.
            metadata: Optional metadata to include in the event.

        Returns:
            True if the transition was successful, False otherwise.
        """
        async with self._transition_lock:
            if not self._is_valid_transition(self._state, new_state):
                logger.warning(
                    f"Invalid transition: {self._state.value} → {new_state.value}"
                )
                return False

            previous = self._state
            self._state = new_state

            logger.info(f"State transition: {previous.value} → {new_state.value}")

            event = StateChangeEvent(
                previous_state=previous,
                new_state=new_state,
                metadata=metadata,
            )
            await self._notify_callbacks(event)
            return True

    def _is_valid_transition(
        self,
        from_state: ConversationState,
        to_state: ConversationState,
    ) -> bool:
        """Check if a transition is valid."""
        valid_targets = VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid_targets

    def add_callback(self, callback: StateChangeCallback) -> None:
        """Register a callback for state change events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: StateChangeCallback) -> None:
        """Remove a registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _notify_callbacks(self, event: StateChangeEvent) -> None:
        """Notify all registered callbacks of a state change."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    # Convenience methods for common transitions

    async def start_listening(self, metadata: Optional[dict] = None) -> bool:
        """Transition to LISTENING state."""
        return await self.transition_to(ConversationState.LISTENING, metadata)

    async def start_processing(self, metadata: Optional[dict] = None) -> bool:
        """Transition to PROCESSING state."""
        return await self.transition_to(ConversationState.PROCESSING, metadata)

    async def start_speaking(self, metadata: Optional[dict] = None) -> bool:
        """Transition to SPEAKING state."""
        return await self.transition_to(ConversationState.SPEAKING, metadata)

    async def stop(self, metadata: Optional[dict] = None) -> bool:
        """Transition to IDLE state."""
        return await self.transition_to(ConversationState.IDLE, metadata)

    async def reset(self) -> None:
        """
        Force reset to IDLE state.

        This bypasses transition validation and should only be used
        for error recovery or shutdown.
        """
        async with self._transition_lock:
            previous = self._state
            self._state = ConversationState.IDLE
            if previous != ConversationState.IDLE:
                logger.info(f"State reset: {previous.value} → idle")
                event = StateChangeEvent(
                    previous_state=previous,
                    new_state=ConversationState.IDLE,
                    metadata={"reason": "reset"},
                )
                await self._notify_callbacks(event)
