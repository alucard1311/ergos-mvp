"""Speech-to-text (STT) package for Ergos voice assistant."""

from ergos.stt.processor import STTProcessor
from ergos.stt.transcriber import WhisperTranscriber
from ergos.stt.types import (
    TranscriptionCallback,
    TranscriptionResult,
    TranscriptionSegment,
)

__all__ = [
    "TranscriptionSegment",
    "TranscriptionResult",
    "TranscriptionCallback",
    "WhisperTranscriber",
    "STTProcessor",
]
