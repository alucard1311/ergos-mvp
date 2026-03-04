"""TTS processor with sentence chunking and streaming audio."""

import asyncio
import logging
from dataclasses import dataclass, field

from .emotion_markup import EmotionMarkupProcessor
from .synthesizer import TTSSynthesizer
from .types import AudioCallback, SynthesisConfig

logger = logging.getLogger(__name__)


@dataclass
class TTSProcessor:
    """Processor that buffers LLM tokens and streams synthesized audio.

    Receives tokens from the LLM processor, buffers them until a complete
    sentence is detected, then synthesizes and streams audio to registered
    callbacks. Supports barge-in by clearing the buffer.
    """

    synthesizer: TTSSynthesizer
    config: SynthesisConfig = field(default_factory=SynthesisConfig)

    # TTS engine name — controls emotion markup activation
    # "orpheus" enables EmotionMarkupProcessor; all others get passthrough
    engine: str = "kokoro"

    # Sentence boundary characters
    sentence_endings: str = ".!?"

    # Internal state (not init parameters)
    _emotion_markup: EmotionMarkupProcessor = field(default_factory=EmotionMarkupProcessor, init=False)
    _buffer: str = field(default="", init=False)
    _audio_callbacks: list[AudioCallback] = field(default_factory=list, init=False)
    _cancelled: bool = field(default=False, init=False)  # Cancellation flag for synthesis
    _synthesis_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)  # Serialize synthesis calls
    _is_synthesizing: bool = field(default=False, init=False)  # Track if synthesis is in progress
    _total_audio_duration_ms: float = field(default=0.0, init=False)  # Track total audio generated

    async def receive_token(self, token: str) -> None:
        """Receive a token from LLM and process when sentence complete.

        This method is designed to be registered as a token callback
        with LLMProcessor.add_token_callback().

        Args:
            token: A text token from the LLM stream.
        """
        self._buffer += token
        logger.debug(f"TTS: Received token, buffer now: '{self._buffer[:50]}...'")

        # Check for sentence boundary
        if self._has_complete_sentence():
            sentence = self._extract_sentence()
            if sentence.strip():
                logger.info(f"TTS: Complete sentence, synthesizing: '{sentence[:50]}...'")
                await self._synthesize_and_stream(sentence)

    def _has_complete_sentence(self) -> bool:
        """Check if buffer contains a complete sentence.

        Returns:
            True if a sentence ending is found at end or followed by space.
        """
        for char in self.sentence_endings:
            if char in self._buffer:
                # Make sure there's content after the ending (or it's at end)
                idx = self._buffer.rfind(char)
                # Allow for trailing space or end of buffer
                if idx == len(self._buffer) - 1 or self._buffer[idx + 1] == " ":
                    return True
        return False

    def _extract_sentence(self) -> str:
        """Extract first complete sentence from buffer.

        Returns:
            The extracted sentence including its ending punctuation.
        """
        earliest_idx = len(self._buffer)
        for char in self.sentence_endings:
            idx = self._buffer.find(char)
            if idx != -1 and idx < earliest_idx:
                earliest_idx = idx

        if earliest_idx < len(self._buffer):
            sentence = self._buffer[: earliest_idx + 1]
            self._buffer = self._buffer[earliest_idx + 1 :].lstrip()
            return sentence
        return ""

    async def _synthesize_and_stream(self, text: str) -> None:
        """Synthesize text and stream audio to callbacks.

        Args:
            text: The text to synthesize.

        Note:
            Uses a lock to serialize synthesis calls. This prevents multiple
            concurrent syntheses which could lead to orphaned background tasks
            in kokoro-onnx (its create_stream creates async tasks that continue
            running even when the consumer stops iterating).

            Respects the _cancelled flag. If cancel() is called during
            synthesis, this method will stop yielding audio chunks.
            Also handles CancelledError from external task cancellation.
        """
        # Apply emotion markup preprocessing (Orpheus only; Kokoro/CSM get passthrough)
        text = self._emotion_markup.process(text, engine=self.engine)

        preview = text[:50] + "..." if len(text) > 50 else text
        logger.debug(f"TTS: Synthesizing '{preview}'")

        # Skip if already cancelled
        if self._cancelled:
            logger.debug("TTS: Skipping synthesis - already cancelled")
            return

        async with self._synthesis_lock:
            # Double-check cancellation after acquiring lock
            if self._cancelled:
                logger.debug("TTS: Skipping synthesis - cancelled while waiting for lock")
                return

            self._is_synthesizing = True
            try:
                async for samples, sample_rate in self.synthesizer.synthesize_stream(
                    text, self.config
                ):
                    # Check cancellation before processing each chunk
                    if self._cancelled:
                        logger.info("TTS: Synthesis cancelled, stopping stream")
                        return

                    # Track audio duration
                    chunk_duration_ms = (len(samples) / sample_rate) * 1000
                    self._total_audio_duration_ms += chunk_duration_ms

                    for callback in self._audio_callbacks:
                        try:
                            await callback(samples, sample_rate)
                        except Exception as e:
                            logger.error(f"Audio callback error: {e}")
            except asyncio.CancelledError:
                logger.info("TTS: Synthesis task was cancelled")
                raise  # Re-raise to properly handle cancellation
            finally:
                self._is_synthesizing = False

    async def flush(self) -> None:
        """Synthesize any remaining text in buffer.

        Call this after LLM generation completes to ensure any
        partial sentence in the buffer gets synthesized.
        """
        if self._buffer.strip():
            await self._synthesize_and_stream(self._buffer)
            self._buffer = ""

    def clear_buffer(self) -> None:
        """Clear text buffer (for barge-in).

        Call this when the user interrupts (barge-in) to discard
        any pending text that hasn't been synthesized yet.
        """
        self._buffer = ""
        logger.debug("TTS: Buffer cleared")

    async def cancel(self) -> None:
        """Cancel ongoing TTS synthesis.

        Call this on barge-in to stop audio generation immediately.
        Sets the cancellation flag which is checked by _synthesize_and_stream.

        The synthesis lock ensures that any ongoing synthesis will complete
        its current chunk before checking the cancellation flag. New synthesis
        calls will see the flag and exit early.

        NOTE: This is async to allow for a brief yield to let pending operations
        notice the cancellation flag.
        """
        self._cancelled = True
        self._buffer = ""
        logger.info("TTS: Synthesis cancelled")

        # Yield to allow any pending synthesis to check the cancellation flag
        await asyncio.sleep(0)

    def reset_cancellation(self) -> None:
        """Reset the cancellation flag.

        Call this when starting a new utterance to allow synthesis.
        """
        self._cancelled = False

    # Callback registration methods

    def add_audio_callback(self, callback: AudioCallback) -> None:
        """Register a callback for audio output.

        Args:
            callback: Async function called with (samples, sample_rate).
        """
        self._audio_callbacks.append(callback)

    def remove_audio_callback(self, callback: AudioCallback) -> None:
        """Remove an audio callback.

        Args:
            callback: The callback to remove.
        """
        if callback in self._audio_callbacks:
            self._audio_callbacks.remove(callback)

    # Stats and monitoring

    @property
    def stats(self) -> dict:
        """Get processor statistics.

        Returns:
            Dictionary with processor state information.
        """
        return {
            "buffer_length": len(self._buffer),
            "audio_callbacks": len(self._audio_callbacks),
            "model_loaded": self.synthesizer.model_loaded,
        }

    @property
    def buffer(self) -> str:
        """Get current text buffer (read-only).

        Returns:
            The current buffered text awaiting synthesis.
        """
        return self._buffer

    @property
    def is_synthesizing(self) -> bool:
        """Check if synthesis is currently in progress."""
        return self._is_synthesizing

    @property
    def total_audio_duration_ms(self) -> float:
        """Get total audio duration generated in current session."""
        return self._total_audio_duration_ms

    def reset_audio_tracking(self) -> None:
        """Reset audio duration tracking for new utterance."""
        self._total_audio_duration_ms = 0.0
