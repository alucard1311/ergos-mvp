"""STT types for speech-to-text transcription results."""

from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class TranscriptionSegment:
    """A segment of transcribed speech (word or phrase level)."""

    text: str
    start: float  # Start time in seconds
    end: float  # End time in seconds
    confidence: float = 1.0  # Confidence score [0, 1]


@dataclass
class TranscriptionResult:
    """Complete transcription result from speech-to-text."""

    text: str  # Full transcribed text
    segments: list[TranscriptionSegment] = field(default_factory=list)
    language: str = "en"  # Detected/specified language
    duration_ms: float = 0.0  # Audio duration in milliseconds


# Type alias for async transcription callbacks
TranscriptionCallback = Callable[[TranscriptionResult], Awaitable[None]]
