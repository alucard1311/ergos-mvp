"""Ergos audio infrastructure."""

from ergos.audio.types import (
    AudioFrame,
    AudioChunk,
    AudioFormat,
    SAMPLE_RATE,
    CHANNELS,
    SAMPLE_WIDTH,
    CHUNK_SIZE,
    CHUNK_DURATION_MS,
)
from ergos.audio.buffer import (
    AudioBuffer,
    AudioInputStream,
    AudioOutputStream,
)
from ergos.audio.vad import (
    VADEvent,
    VADEventType,
    VADProcessor,
)
from ergos.audio.pipeline import (
    AudioPipeline,
    PipelineState,
)

__all__ = [
    # Types
    "AudioFrame",
    "AudioChunk",
    "AudioFormat",
    # Constants
    "SAMPLE_RATE",
    "CHANNELS",
    "SAMPLE_WIDTH",
    "CHUNK_SIZE",
    "CHUNK_DURATION_MS",
    # Buffers
    "AudioBuffer",
    "AudioInputStream",
    "AudioOutputStream",
    # VAD
    "VADEvent",
    "VADEventType",
    "VADProcessor",
    # Pipeline
    "AudioPipeline",
    "PipelineState",
]
