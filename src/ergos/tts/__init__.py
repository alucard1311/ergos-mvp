"""TTS package for speech synthesis."""

from .synthesizer import TTSSynthesizer
from .types import AudioCallback, SynthesisConfig, SynthesisResult

__all__ = [
    "AudioCallback",
    "SynthesisConfig",
    "SynthesisResult",
    "TTSSynthesizer",
]
