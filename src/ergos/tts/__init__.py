"""TTS package for speech synthesis."""

from .processor import TTSProcessor
from .synthesizer import TTSSynthesizer
from .types import AudioCallback, SynthesisConfig, SynthesisResult

__all__ = [
    "AudioCallback",
    "SynthesisConfig",
    "SynthesisResult",
    "TTSProcessor",
    "TTSSynthesizer",
]
