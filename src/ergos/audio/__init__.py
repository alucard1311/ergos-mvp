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
from ergos.audio.buffer import (
    AudioBuffer,
    AudioInputStream,
    AudioOutputStream,
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
    "AudioBuffer",
    "AudioInputStream",
    "AudioOutputStream",
]
