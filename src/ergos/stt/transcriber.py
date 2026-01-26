"""WhisperTranscriber wrapper for faster-whisper speech-to-text."""

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import numpy as np

from ergos.stt.types import TranscriptionResult, TranscriptionSegment

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Wrapper around faster-whisper for speech-to-text transcription.

    Provides lazy model loading, audio transcription, and streaming support.
    Uses faster-whisper's CTranslate2-based Whisper implementation for
    efficient inference.
    """

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        """Initialize transcriber configuration.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3).
                        Use .en suffix for English-only models (faster).
            device: Device to run on ("auto", "cpu", "cuda").
                    "auto" lets faster-whisper pick best available.
            compute_type: Precision ("auto", "float16", "int8", "float32").
                          "auto" picks optimal for device.
        """
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: "WhisperModel | None" = None

    def _ensure_model(self) -> "WhisperModel":
        """Lazy load the Whisper model on first use.

        Returns:
            The loaded WhisperModel instance.
        """
        if self._model is None:
            logger.info(
                "Loading Whisper model: %s (device=%s, compute_type=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("Whisper model loaded successfully")
        return self._model

    def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed integers).
            sample_rate: Sample rate of the audio (default 16000 Hz).

        Returns:
            TranscriptionResult with full text and word-level segments.
        """
        # Convert bytes to numpy array (16-bit signed integers)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Normalize to float32 [-1, 1] range for faster-whisper
        audio_float = audio_array.astype(np.float32) / 32768.0

        # Calculate duration in milliseconds
        duration_ms = (len(audio_array) / sample_rate) * 1000

        # Get the model (lazy load if needed)
        model = self._ensure_model()

        # Transcribe with word timestamps for segment-level results
        segments_iter, info = model.transcribe(
            audio_float,
            beam_size=5,
            language="en",
            word_timestamps=True,
        )

        # Build segments list from iterator
        segments: list[TranscriptionSegment] = []
        full_text_parts: list[str] = []

        for segment in segments_iter:
            # Add segment text to full transcription
            full_text_parts.append(segment.text.strip())

            # Extract word-level segments if available
            if segment.words:
                for word in segment.words:
                    segments.append(
                        TranscriptionSegment(
                            text=word.word.strip(),
                            start=word.start,
                            end=word.end,
                            confidence=word.probability,
                        )
                    )
            else:
                # Fall back to segment-level if no word timestamps
                segments.append(
                    TranscriptionSegment(
                        text=segment.text.strip(),
                        start=segment.start,
                        end=segment.end,
                        confidence=0.0,  # No word-level confidence
                    )
                )

        return TranscriptionResult(
            text=" ".join(full_text_parts),
            segments=segments,
            language=info.language,
            duration_ms=duration_ms,
        )

    def transcribe_stream(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> Iterator[TranscriptionSegment]:
        """Transcribe audio and yield segments as they're generated.

        Useful for streaming partial results to caller.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed integers).
            sample_rate: Sample rate of the audio (default 16000 Hz).

        Yields:
            TranscriptionSegment for each word/phrase as it's transcribed.
        """
        # Convert bytes to numpy array (16-bit signed integers)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Normalize to float32 [-1, 1] range for faster-whisper
        audio_float = audio_array.astype(np.float32) / 32768.0

        # Get the model (lazy load if needed)
        model = self._ensure_model()

        # Transcribe with word timestamps
        segments_iter, _info = model.transcribe(
            audio_float,
            beam_size=5,
            language="en",
            word_timestamps=True,
        )

        # Yield segments as they're generated
        for segment in segments_iter:
            if segment.words:
                for word in segment.words:
                    yield TranscriptionSegment(
                        text=word.word.strip(),
                        start=word.start,
                        end=word.end,
                        confidence=word.probability,
                    )
            else:
                yield TranscriptionSegment(
                    text=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    confidence=0.0,
                )

    @property
    def model_loaded(self) -> bool:
        """Check if the model has been loaded."""
        return self._model is not None

    def close(self) -> None:
        """Release model resources."""
        if self._model is not None:
            logger.info("Releasing Whisper model resources")
            # WhisperModel doesn't have an explicit close method,
            # but clearing reference allows garbage collection
            self._model = None
