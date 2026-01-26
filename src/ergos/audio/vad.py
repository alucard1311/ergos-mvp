import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Awaitable
import time

logger = logging.getLogger(__name__)


class VADEventType(Enum):
    """Types of VAD events from client."""
    SPEECH_START = "speech_start"  # User started speaking
    SPEECH_END = "speech_end"  # User stopped speaking
    SPEECH_PROBABILITY = "speech_probability"  # Continuous probability update


@dataclass
class VADEvent:
    """A Voice Activity Detection event from the client."""
    type: VADEventType
    timestamp: float = field(default_factory=time.time)
    probability: Optional[float] = None  # Speech probability (0.0 - 1.0)
    duration_ms: Optional[float] = None  # Duration of speech segment (for SPEECH_END)

    @classmethod
    def speech_start(cls) -> "VADEvent":
        """Create a speech start event."""
        return cls(type=VADEventType.SPEECH_START)

    @classmethod
    def speech_end(cls, duration_ms: float) -> "VADEvent":
        """Create a speech end event with duration."""
        return cls(type=VADEventType.SPEECH_END, duration_ms=duration_ms)

    @classmethod
    def probability(cls, prob: float) -> "VADEvent":
        """Create a probability update event."""
        return cls(type=VADEventType.SPEECH_PROBABILITY, probability=prob)


# Type alias for VAD event callbacks
VADCallback = Callable[[VADEvent], Awaitable[None]]


class VADProcessor:
    """
    Processes VAD events from the client.

    The client (Flutter app) performs actual VAD detection using silero-vad
    and sends events to the server. This processor handles those events
    and triggers appropriate pipeline actions.
    """

    def __init__(self):
        self._callbacks: list[VADCallback] = []
        self._is_speech_active = False
        self._speech_start_time: Optional[float] = None
        self._event_count = 0
        self._last_event: Optional[VADEvent] = None

    def add_callback(self, callback: VADCallback) -> None:
        """Register a callback for VAD events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: VADCallback) -> None:
        """Remove a registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def process_event(self, event: VADEvent) -> None:
        """
        Process a VAD event and notify callbacks.

        Args:
            event: The VAD event to process
        """
        self._event_count += 1
        self._last_event = event

        # Update internal state
        if event.type == VADEventType.SPEECH_START:
            if not self._is_speech_active:
                self._is_speech_active = True
                self._speech_start_time = event.timestamp
                logger.info("VAD: Speech started")

        elif event.type == VADEventType.SPEECH_END:
            if self._is_speech_active:
                self._is_speech_active = False
                duration = event.duration_ms or 0
                logger.info(f"VAD: Speech ended (duration: {duration:.0f}ms)")
                self._speech_start_time = None

        elif event.type == VADEventType.SPEECH_PROBABILITY:
            # Log high probability events for debugging
            if event.probability and event.probability > 0.8:
                logger.debug(f"VAD: High probability {event.probability:.2f}")

        # Notify all callbacks
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"VAD callback error: {e}")

    async def process_raw_event(self, event_type: str, data: dict) -> None:
        """
        Process a raw event from the data channel.

        Args:
            event_type: String event type (e.g., "speech_start")
            data: Additional event data
        """
        try:
            vad_type = VADEventType(event_type)
        except ValueError:
            logger.warning(f"Unknown VAD event type: {event_type}")
            return

        event = VADEvent(
            type=vad_type,
            probability=data.get("probability"),
            duration_ms=data.get("duration_ms"),
        )

        await self.process_event(event)

    @property
    def is_speech_active(self) -> bool:
        """Whether speech is currently detected."""
        return self._is_speech_active

    @property
    def speech_duration_ms(self) -> Optional[float]:
        """Duration of current speech segment in ms, or None if not speaking."""
        if self._is_speech_active and self._speech_start_time:
            return (time.time() - self._speech_start_time) * 1000
        return None

    @property
    def stats(self) -> dict:
        """Get processor statistics."""
        return {
            "event_count": self._event_count,
            "is_speech_active": self._is_speech_active,
            "speech_duration_ms": self.speech_duration_ms,
        }
