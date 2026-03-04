"""Conversation state machine with enforced transitions."""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from ergos.state.events import (
    ConversationState,
    StateChangeEvent,
    StateChangeCallback,
)

# Type alias for barge-in callbacks (e.g., clear TTS buffer)
BargeInCallback = Callable[[], Awaitable[None]]

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
        ConversationState.SPEAKING_AND_LISTENING,  # NEW: voice detected while AI is speaking
    },
    ConversationState.SPEAKING_AND_LISTENING: {  # NEW: full-duplex state
        ConversationState.LISTENING,   # speech_end -> full barge-in
        ConversationState.SPEAKING,    # speech_end -> user stopped quickly, resume speaking
        ConversationState.IDLE,        # stop / error recovery
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
        SPEAKING → SPEAKING_AND_LISTENING (voice detected while AI is speaking)
        SPEAKING_AND_LISTENING → LISTENING (user continues — full barge-in)
        SPEAKING_AND_LISTENING → SPEAKING (user stopped quickly — resume)
        SPEAKING_AND_LISTENING → IDLE (stop / error recovery)
    """

    def __init__(self):
        self._state = ConversationState.IDLE
        self._callbacks: list[StateChangeCallback] = []
        self._barge_in_callbacks: list[BargeInCallback] = []
        self._transition_lock = asyncio.Lock()

    @property
    def state(self) -> ConversationState:
        """Current conversation state."""
        return self._state

    @property
    def stats(self) -> dict:
        """Get state machine statistics."""
        return {
            "current_state": self._state.value,
            "callback_count": len(self._callbacks),
            "barge_in_callback_count": len(self._barge_in_callbacks),
        }

    @property
    def is_interruptible(self) -> bool:
        """Whether barge-in is currently possible."""
        return self._state in (
            ConversationState.SPEAKING,
            ConversationState.PROCESSING,
            ConversationState.SPEAKING_AND_LISTENING,
        )

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

    # Barge-in support

    async def barge_in(self) -> bool:
        """
        Handle barge-in (user interrupting AI).

        - If SPEAKING: clears buffers, transitions to LISTENING
        - If PROCESSING: transitions to LISTENING
        - Otherwise: no-op, returns False

        Returns True if barge-in was executed.
        """
        if self._state in (ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
            # First invoke barge-in callbacks to clear buffers
            for callback in self._barge_in_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.error(f"Barge-in callback error: {e}")

            # Then transition to LISTENING
            await self.transition_to(
                ConversationState.LISTENING,
                metadata={"trigger": "barge_in"}
            )
            logger.info("Barge-in: interrupted speaking, now listening")
            return True

        elif self._state == ConversationState.PROCESSING:
            await self.transition_to(
                ConversationState.LISTENING,
                metadata={"trigger": "barge_in"}
            )
            logger.info("Barge-in: interrupted processing, now listening")
            return True

        return False

    def add_barge_in_callback(self, callback: BargeInCallback) -> None:
        """Register callback to be invoked on barge-in (e.g., clear TTS buffer)."""
        self._barge_in_callbacks.append(callback)

    def remove_barge_in_callback(self, callback: BargeInCallback) -> None:
        """Remove a barge-in callback."""
        if callback in self._barge_in_callbacks:
            self._barge_in_callbacks.remove(callback)
