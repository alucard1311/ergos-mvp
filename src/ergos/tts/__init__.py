"""TTS package for speech synthesis."""

from .orpheus_synthesizer import OrpheusSynthesizer
from .processor import TTSProcessor
from .synthesizer import KokoroSynthesizer, TTSSynthesizer
from .types import AudioCallback, SynthesisConfig, SynthesisResult

__all__ = [
    "AudioCallback",
    "KokoroSynthesizer",
    "OrpheusSynthesizer",
    "SynthesisConfig",
    "SynthesisResult",
    "TTSProcessor",
    "TTSSynthesizer",
]
