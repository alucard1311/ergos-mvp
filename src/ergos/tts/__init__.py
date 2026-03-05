"""TTS package for speech synthesis."""

from .emotion_markup import EmotionMarkupProcessor
from .orpheus_synthesizer import OrpheusSynthesizer
from .processor import TTSProcessor
from .synthesizer import TTSSynthesizer
from .types import AudioCallback, SynthesisConfig, SynthesisResult

__all__ = [
    "AudioCallback",
    "EmotionMarkupProcessor",
    "OrpheusSynthesizer",
    "SynthesisConfig",
    "SynthesisResult",
    "TTSProcessor",
    "TTSSynthesizer",
]
