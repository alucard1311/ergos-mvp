"""TTS synthesizer wrapper for kokoro-onnx."""

import logging
from collections.abc import AsyncIterator
from typing import Optional

import numpy as np

from .types import SynthesisConfig, SynthesisResult

logger = logging.getLogger(__name__)


class TTSSynthesizer:
    """Wrapper for kokoro-onnx TTS model with lazy loading."""

    def __init__(
        self,
        model_path: str,
        voices_path: str,
    ) -> None:
        """Initialize synthesizer with model and voices paths.

        Args:
            model_path: Path to kokoro-v1.0.onnx model file.
            voices_path: Path to voices-v1.0.bin voices file.
        """
        self._model_path = model_path
        self._voices_path = voices_path
        self._kokoro = None

    def _ensure_model(self):
        """Lazy load the Kokoro model on first use.

        Returns:
            The loaded Kokoro model.
        """
        if self._kokoro is None:
            logger.info(f"Loading TTS model from {self._model_path}...")
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(self._model_path, self._voices_path)
            logger.info("TTS model loaded successfully")
        return self._kokoro

    def synthesize(
        self,
        text: str,
        config: Optional[SynthesisConfig] = None,
    ) -> SynthesisResult:
        """Synthesize speech from text synchronously.

        Args:
            text: The input text to synthesize.
            config: Synthesis configuration (uses defaults if None).

        Returns:
            SynthesisResult with audio samples and metadata.
        """
        if config is None:
            config = SynthesisConfig()

        kokoro = self._ensure_model()

        samples, sample_rate = kokoro.create(
            text,
            voice=config.voice,
            speed=config.speed,
            lang=config.lang,
        )

        # Calculate duration from samples length and sample rate
        duration_ms = (len(samples) / sample_rate) * 1000

        return SynthesisResult(
            audio_samples=samples,
            sample_rate=sample_rate,
            text=text,
            duration_ms=duration_ms,
        )

    async def synthesize_stream(
        self,
        text: str,
        config: Optional[SynthesisConfig] = None,
    ) -> AsyncIterator[tuple[np.ndarray, int]]:
        """Synthesize speech from text with streaming.

        Yields audio chunks as they are generated. kokoro-onnx's
        create_stream() is natively async, no executor needed.

        Args:
            text: The input text to synthesize.
            config: Synthesis configuration (uses defaults if None).

        Yields:
            Tuples of (audio_samples, sample_rate) for each chunk.
        """
        if config is None:
            config = SynthesisConfig()

        kokoro = self._ensure_model()

        stream = kokoro.create_stream(
            text,
            voice=config.voice,
            speed=config.speed,
            lang=config.lang,
        )

        async for samples, sample_rate in stream:
            yield samples, sample_rate

    @property
    def model_loaded(self) -> bool:
        """Check if the model is currently loaded.

        Returns:
            True if model is loaded, False otherwise.
        """
        return self._kokoro is not None

    @property
    def sample_rate(self) -> int:
        """Get the output sample rate.

        Returns:
            The sample rate in Hz (24000 for Kokoro).
        """
        return 24000

    def close(self) -> None:
        """Release model resources."""
        if self._kokoro is not None:
            self._kokoro = None
            logger.info("TTS model released")
