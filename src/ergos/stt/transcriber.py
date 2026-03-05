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
        self._initial_prompt: str | None = "Ergos, sarcasm"  # Bias Whisper to recognize wake word and commands

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
        # initial_prompt conditions Whisper with conversation context,
        # improving accuracy for follow-up questions and domain vocabulary.
        segments_iter, info = model.transcribe(
            audio_float,
            beam_size=5,
            language="en",
            word_timestamps=True,
            initial_prompt=self._initial_prompt,
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

    def transcribe_file(self, filepath: str) -> str:
        """Transcribe an audio file to text.

        Uses faster-whisper's built-in file handling (supports WAV, etc.).

        Args:
            filepath: Path to the audio file.

        Returns:
            Full transcription text.
        """
        model = self._ensure_model()
        segments, _info = model.transcribe(
            filepath, beam_size=5, language="en"
        )
        return " ".join(seg.text.strip() for seg in segments)

    def transcribe_file_segments(
        self, filepath: str
    ) -> list[tuple[float, float, str]]:
        """Transcribe an audio file and return timestamped segments.

        Args:
            filepath: Path to the audio file.

        Returns:
            List of (start_seconds, end_seconds, text) tuples.
        """
        model = self._ensure_model()
        segments, _info = model.transcribe(
            filepath, beam_size=5, language="en"
        )
        return [
            (seg.start, seg.end, seg.text.strip())
            for seg in segments
            if seg.text.strip()
        ]

    @property
    def model_loaded(self) -> bool:
        """Check if the model has been loaded."""
        return self._model is not None

    def set_prompt_context(self, recent_text: str) -> None:
        """Set conversation context for Whisper prompt conditioning.

        Whisper's initial_prompt biases the decoder toward vocabulary and
        phrasing it has recently seen, improving accuracy for follow-up
        questions and domain-specific terms.

        Args:
            recent_text: Recent conversation text (last ~200 chars is optimal).
        """
        # Whisper works best with a concise prompt; trim to last ~200 chars
        if len(recent_text) > 200:
            recent_text = recent_text[-200:]
        # Prepend wake word so Whisper always knows it
        prefix = "Ergos. "
        self._initial_prompt = prefix + recent_text if recent_text.strip() else prefix.strip()

    def close(self) -> None:
        """Release model resources."""
        if self._model is not None:
            logger.info("Releasing Whisper model resources")
            # WhisperModel doesn't have an explicit close method,
            # but clearing reference allows garbage collection
            self._model = None
