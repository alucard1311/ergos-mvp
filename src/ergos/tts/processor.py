"""TTS processor with sentence chunking and streaming audio."""

import logging
from dataclasses import dataclass, field

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

    # Sentence boundary characters
    sentence_endings: str = ".!?"

    # Internal state (not init parameters)
    _buffer: str = field(default="", init=False)
    _audio_callbacks: list[AudioCallback] = field(default_factory=list, init=False)

    async def receive_token(self, token: str) -> None:
        """Receive a token from LLM and process when sentence complete.

        This method is designed to be registered as a token callback
        with LLMProcessor.add_token_callback().

        Args:
            token: A text token from the LLM stream.
        """
        self._buffer += token

        # Check for sentence boundary
        if self._has_complete_sentence():
            sentence = self._extract_sentence()
            if sentence.strip():
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
        """
        preview = text[:50] + "..." if len(text) > 50 else text
        logger.debug(f"TTS: Synthesizing '{preview}'")

        async for samples, sample_rate in self.synthesizer.synthesize_stream(
            text, self.config
        ):
            for callback in self._audio_callbacks:
                try:
                    await callback(samples, sample_rate)
                except Exception as e:
                    logger.error(f"Audio callback error: {e}")

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
