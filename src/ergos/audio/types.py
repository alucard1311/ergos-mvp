from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# Audio format constants - standardized for the pipeline
SAMPLE_RATE = 16000  # 16kHz - standard for speech recognition
CHANNELS = 1  # Mono
SAMPLE_WIDTH = 2  # 16-bit (2 bytes per sample)
CHUNK_SIZE = 480  # 30ms at 16kHz (16000 * 0.03)
CHUNK_DURATION_MS = 30  # milliseconds per chunk


class AudioFormat(Enum):
    """Supported audio formats."""
    PCM_16KHZ_MONO = "pcm_16khz_mono"  # Raw PCM, 16kHz, mono, 16-bit
    OPUS = "opus"  # Opus codec (for WebRTC)


@dataclass
class AudioFrame:
    """A single frame of audio data."""
    data: bytes
    timestamp: float = field(default_factory=time.time)
    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS
    format: AudioFormat = AudioFormat.PCM_16KHZ_MONO

    @property
    def duration_ms(self) -> float:
        """Duration of this frame in milliseconds."""
        samples = len(self.data) // (SAMPLE_WIDTH * self.channels)
        return (samples / self.sample_rate) * 1000

    @property
    def sample_count(self) -> int:
        """Number of samples in this frame."""
        return len(self.data) // (SAMPLE_WIDTH * self.channels)

    def __len__(self) -> int:
        """Return byte length of audio data."""
        return len(self.data)


@dataclass
class AudioChunk:
    """A chunk of audio with metadata for pipeline processing."""
    frame: AudioFrame
    sequence: int  # Sequence number for ordering
    is_speech: Optional[bool] = None  # VAD classification if available

    @property
    def data(self) -> bytes:
        return self.frame.data

    @property
    def timestamp(self) -> float:
        return self.frame.timestamp
