"""TTS processor with sentence chunking and streaming audio."""

import asyncio
import logging
import re
from dataclasses import dataclass, field

import numpy as np

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

    # Silence gap between sentences (ms) for natural pacing
    inter_sentence_pause_ms: int = 120

    # Internal state (not init parameters)
    _emotion_markup: EmotionMarkupProcessor = field(default_factory=EmotionMarkupProcessor, init=False)
    _buffer: str = field(default="", init=False)
    _audio_callbacks: list[AudioCallback] = field(default_factory=list, init=False)
    _cancelled: bool = field(default=False, init=False)  # Cancellation flag for synthesis
    _synthesis_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)  # Serialize synthesis calls
    _is_synthesizing: bool = field(default=False, init=False)  # Track if synthesis is in progress
    _total_audio_duration_ms: float = field(default=0.0, init=False)  # Track total audio generated
    _inside_think: bool = field(default=False, init=False)  # Track <think> blocks

    async def receive_token(self, token: str) -> None:
        """Receive a token from LLM and process when sentence complete.

        This method is designed to be registered as a token callback
        with LLMProcessor.add_token_callback().
        Filters out <think>...</think> reasoning blocks from Qwen3.

        Args:
            token: A text token from the LLM stream.
        """
        self._buffer += token

        # Filter out <think>...</think> blocks (Qwen3 reasoning)
        if "<think>" in self._buffer:
            self._inside_think = True
        if self._inside_think:
            # Check if the closing tag has arrived
            if "</think>" in self._buffer:
                # Strip the entire think block
                self._buffer = re.sub(
                    r"<think>.*?</think>", "", self._buffer, flags=re.DOTALL
                )
                self._inside_think = False
            else:
                # Still inside think block, don't process yet
                return
        logger.debug(f"TTS: Received token, buffer now: '{self._buffer[:50]}...'")

        # Check for sentence boundary
        if self._has_complete_sentence():
            sentence = self._extract_sentence()
            if sentence.strip():
                logger.info(f"TTS: Complete sentence, synthesizing: '{sentence[:50]}...'")
                await self._synthesize_and_stream(sentence)

    # Minimum characters of actual text (letters/digits) before synthesizing.
    # Prevents tiny fragments like "..." or "*sighs*" from being synthesized
    # individually, which is slow on Orpheus and produces garbled audio.
    _MIN_SPEAKABLE_CHARS: int = 20

    def _has_complete_sentence(self) -> bool:
        """Check if buffer contains a complete sentence ready to synthesize.

        Uses _find_sentence_boundary() which scans forward through boundaries
        until finding one with enough speakable content.

        Returns:
            True if a synthesizable sentence is found.
        """
        return self._find_sentence_boundary() >= 0

    def _find_next_raw_boundary(self, buf: str, from_pos: int = 0) -> int:
        """Find the next sentence-ending boundary at or after from_pos.

        Returns:
            Index of the sentence-ending character, or -1 if none found.
        """
        earliest_idx = -1
        for char in self.sentence_endings:
            idx = buf.find(char, from_pos)
            if idx == -1:
                continue
            # Must be at end or followed by space
            if idx < len(buf) - 1 and buf[idx + 1] != " ":
                continue
            # For dots, skip past consecutive dots (ellipsis)
            if char == ".":
                while idx + 1 < len(buf) and buf[idx + 1] == ".":
                    idx += 1
                # If at buffer end, more dots might be coming
                if idx == len(buf) - 1:
                    dot_start = idx
                    while dot_start > 0 and buf[dot_start - 1] == ".":
                        dot_start -= 1
                    if idx - dot_start >= 2:
                        continue
            if earliest_idx < 0 or idx < earliest_idx:
                earliest_idx = idx
        return earliest_idx

    def _find_sentence_boundary(self) -> int:
        """Find a sentence boundary with enough speakable text.

        Scans forward through sentence boundaries. If the first boundary's
        text has fewer than _MIN_SPEAKABLE_CHARS alphanumeric characters,
        continues to the next boundary and checks the cumulative text.
        This prevents short opening sentences (e.g., "Here's one.") from
        blocking synthesis of all subsequent text.

        Returns:
            Index of the chosen sentence-ending character, or -1 if none found.
        """
        buf = self._buffer
        search_from = 0
        while search_from < len(buf):
            idx = self._find_next_raw_boundary(buf, search_from)
            if idx < 0:
                return -1
            # Check speakable content from start of buffer to this boundary
            candidate = buf[: idx + 1]
            speakable = sum(1 for c in candidate if c.isalnum())
            if speakable >= self._MIN_SPEAKABLE_CHARS:
                return idx
            # Not enough content yet, scan forward to next boundary
            search_from = idx + 1
        return -1

    def _extract_sentence(self) -> str:
        """Extract text up to the first viable sentence boundary.

        Uses _find_sentence_boundary() (same as _has_complete_sentence)
        so the check and extraction always agree on the split point.

        Returns:
            The extracted text including its ending punctuation.
        """
        idx = self._find_sentence_boundary()
        if idx < 0:
            return ""
        sentence = self._buffer[: idx + 1]
        self._buffer = self._buffer[idx + 1 :].lstrip()
        return sentence

    async def _synthesize_and_stream(self, text: str, is_final: bool = False) -> None:
        """Synthesize text and stream audio to callbacks.

        Strips leading/trailing whitespace and skips empty/whitespace-only text
        to avoid sending garbage to the TTS engine.

        Args:
            text: The text to synthesize.
            is_final: If True, skip inter-sentence silence (last sentence).

        Note:
            Uses a lock to serialize synthesis calls. This prevents multiple
            concurrent syntheses which could lead to orphaned background tasks
            in kokoro-onnx (its create_stream creates async tasks that continue
            running even when the consumer stops iterating).

            Respects the _cancelled flag. If cancel() is called during
            synthesis, this method will stop yielding audio chunks.
            Also handles CancelledError from external task cancellation.
        """
        # Strip whitespace — LLM output often starts with \n\n
        text = text.strip()
        if not text:
            logger.debug("TTS: Skipping empty text after stripping")
            return

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
            last_sample_rate = 0
            try:
                async for samples, sample_rate in self.synthesizer.synthesize_stream(
                    text, self.config
                ):
                    # Check cancellation before processing each chunk
                    if self._cancelled:
                        logger.info("TTS: Synthesis cancelled, stopping stream")
                        return

                    last_sample_rate = sample_rate

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

            # Insert silence between sentences for natural pacing (skip after final sentence)
            if not is_final and not self._cancelled and self.inter_sentence_pause_ms > 0 and last_sample_rate > 0:
                n_silence = int(last_sample_rate * self.inter_sentence_pause_ms / 1000)
                # Comfort noise at -62dBFS instead of digital silence
                noise_amplitude = 0.0008
                silence = np.random.normal(0, noise_amplitude, n_silence).astype(np.float32)
                silence = np.clip(silence, -noise_amplitude * 4, noise_amplitude * 4)
                for callback in self._audio_callbacks:
                    try:
                        await callback(silence, last_sample_rate)
                    except Exception as e:
                        logger.error(f"Audio callback error (silence): {e}")

    async def flush(self) -> None:
        """Synthesize any remaining text in buffer.

        Call this after LLM generation completes to ensure any
        partial sentence in the buffer gets synthesized.
        Strips any incomplete <think> blocks that were never closed
        (e.g., when the LLM hit max_tokens mid-reasoning).
        """
        # If still inside a think block that never closed, discard it
        if self._inside_think:
            # Strip the incomplete <think> block from buffer
            idx = self._buffer.find("<think>")
            if idx != -1:
                self._buffer = self._buffer[:idx]
            else:
                self._buffer = ""
            self._inside_think = False
            logger.info("TTS: Stripped incomplete <think> block at flush")

        # Also strip any complete think blocks that might remain
        self._buffer = re.sub(
            r"<think>.*?</think>", "", self._buffer, flags=re.DOTALL
        )

        if self._buffer.strip():
            await self._synthesize_and_stream(self._buffer, is_final=True)
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
        self._inside_think = False
        logger.info("TTS: Synthesis cancelled")

        # Yield to allow any pending synthesis to check the cancellation flag
        await asyncio.sleep(0)

    def reset_cancellation(self) -> None:
        """Reset the cancellation flag and think-block tracking.

        Call this when starting a new utterance to allow synthesis.
        Also resets _inside_think to prevent stale think-block state
        from a previous utterance silently discarding TTS output at flush().
        """
        self._cancelled = False
        self._inside_think = False

    def reset_state(self) -> None:
        """Full reset of all TTS processing state.

        Call this on new connection or session start to clear all flags
        that could cause stale state to bleed across sessions.
        """
        self._cancelled = False
        self._inside_think = False
        self._buffer = ""
        self._total_audio_duration_ms = 0.0
        logger.debug("TTS: Full state reset")

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
