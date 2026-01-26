# Audio infrastructure for Ergos
# Audio frame types, buffers, and stream management

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

__all__ = [
    "AudioFrame",
    "AudioChunk",
    "AudioFormat",
    "SAMPLE_RATE",
    "CHANNELS",
    "SAMPLE_WIDTH",
    "CHUNK_SIZE",
    "CHUNK_DURATION_MS",
]
