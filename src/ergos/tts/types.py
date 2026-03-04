"""TTS types for speech synthesis results."""

from dataclasses import dataclass
from typing import Awaitable, Callable

import numpy as np


@dataclass
class SynthesisResult:
    """Result from TTS synthesis."""

    audio_samples: np.ndarray  # Audio samples as numpy array
    sample_rate: int  # Sample rate in Hz (e.g., 24000)
    text: str  # Input text that was synthesized
    duration_ms: float  # Duration of audio in milliseconds


@dataclass
class SynthesisConfig:
    """Configuration for TTS synthesis."""

    voice: str = "af_sarah"  # Voice ID to use (Kokoro)
    speed: float = 1.0  # Speech speed multiplier
    lang: str = "en-us"  # Language code
    speaker_id: int = 0  # CSM speaker ID (ignored by Kokoro and Orpheus)
    temperature: float = 0.9  # CSM/Orpheus sampling temperature (ignored by Kokoro)
    top_k: int = 50  # CSM/Orpheus top-k sampling (ignored by Kokoro)
    orpheus_voice: str = "tara"  # Orpheus voice ID (ignored by Kokoro/CSM)
    # Valid Orpheus voices: tara, leah, jess, leo, dan, mia, zac, zoe


# Type alias for async audio streaming callback
# Receives audio chunk (numpy array) and sample rate
AudioCallback = Callable[[np.ndarray, int], Awaitable[None]]
