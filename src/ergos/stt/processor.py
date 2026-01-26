"""STT processor with VAD integration for speech-bounded transcription."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from ergos.audio.types import AudioChunk
from ergos.audio.vad import VADEvent, VADEventType
from ergos.stt.transcriber import WhisperTranscriber
from ergos.stt.types import TranscriptionCallback, TranscriptionResult

logger = logging.getLogger(__name__)


@dataclass
class STTProcessor:
    """Processor that integrates STT with VAD for speech-bounded transcription.

    Accumulates audio during speech and transcribes on speech boundaries.
    Registers with AudioPipeline as an audio callback and VAD event handler.
    """

    transcriber: WhisperTranscriber

    # Configuration
    enable_partials: bool = True
    partial_interval_ms: float = 500  # Emit partials every 500ms

    # Internal state (not init params)
    _audio_buffer: bytearray = field(default_factory=bytearray, init=False)
    _is_accumulating: bool = field(default=False, init=False)
    _transcription_callbacks: list[TranscriptionCallback] = field(
        default_factory=list, init=False
    )
    _partial_callbacks: list[TranscriptionCallback] = field(
        default_factory=list, init=False
    )
    _transcription_count: int = field(default=0, init=False)
    _last_partial_time: float = field(default=0.0, init=False)
    _partial_task: Optional[asyncio.Task] = field(default=None, init=False)

    async def on_audio_chunk(self, chunk: AudioChunk) -> None:
        """Called by AudioPipeline for each audio chunk.

        Accumulates audio data when speech is active or accumulation is in progress.

        Args:
            chunk: Audio chunk from the pipeline with speech classification.
        """
        if chunk.is_speech or self._is_accumulating:
            self._audio_buffer.extend(chunk.data)

    async def on_vad_event(self, event: VADEvent) -> None:
        """Called when VAD events occur.

        Manages audio accumulation based on speech boundaries.

        Args:
            event: VAD event indicating speech state changes.
        """
        if event.type == VADEventType.SPEECH_START:
            self._is_accumulating = True
            self._audio_buffer.clear()
            logger.debug("STT: Started accumulating audio")

            # Start partial transcription loop if enabled
            if self.enable_partials and self._partial_callbacks:
                self._partial_task = asyncio.create_task(self._start_partial_loop())

        elif event.type == VADEventType.SPEECH_END:
            self._is_accumulating = False

            # Cancel partial loop if running
            if self._partial_task is not None:
                self._partial_task.cancel()
                try:
                    await self._partial_task
                except asyncio.CancelledError:
                    pass
                self._partial_task = None

            # Process final accumulated audio
            if len(self._audio_buffer) > 0:
                await self._process_accumulated_audio()

    async def _process_accumulated_audio(self) -> None:
        """Transcribe accumulated audio buffer."""
        audio_bytes = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        # Less than 100ms at 16kHz (1600 bytes = 100ms * 16 samples/ms * 2 bytes/sample)
        if len(audio_bytes) < 1600:
            logger.debug("STT: Audio too short (%d bytes), skipping", len(audio_bytes))
            return

        logger.info("STT: Processing %d bytes of audio", len(audio_bytes))

        # Run transcription in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self.transcriber.transcribe, audio_bytes
            )
        except Exception as e:
            logger.error("STT transcription error: %s", e)
            return

        if result.text.strip():
            logger.info("STT: Transcribed: %s", result.text)
            self._transcription_count += 1
            for callback in self._transcription_callbacks:
                try:
                    await callback(result)
                except Exception as e:
                    logger.error("Transcription callback error: %s", e)

    async def _start_partial_loop(self) -> None:
        """Periodically transcribe partial audio while speaking."""
        while self._is_accumulating and self.enable_partials:
            await asyncio.sleep(self.partial_interval_ms / 1000)

            if not self._is_accumulating:
                break

            current_buffer = bytes(self._audio_buffer)

            # At least 200ms of audio (3200 bytes = 200ms * 16 samples/ms * 2 bytes/sample)
            if len(current_buffer) < 3200:
                continue

            # Run partial transcription in thread pool
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, self.transcriber.transcribe, current_buffer
                )
                if result.text.strip():
                    logger.debug("STT partial: %s", result.text)
                    for callback in self._partial_callbacks:
                        try:
                            await callback(result)
                        except Exception as e:
                            logger.error("Partial callback error: %s", e)
            except Exception as e:
                logger.error("Partial transcription error: %s", e)

    def add_transcription_callback(self, callback: TranscriptionCallback) -> None:
        """Register a callback for final transcription results.

        Args:
            callback: Async function called with TranscriptionResult on speech end.
        """
        self._transcription_callbacks.append(callback)

    def remove_transcription_callback(self, callback: TranscriptionCallback) -> None:
        """Remove a registered transcription callback.

        Args:
            callback: Previously registered callback to remove.
        """
        if callback in self._transcription_callbacks:
            self._transcription_callbacks.remove(callback)

    def add_partial_callback(self, callback: TranscriptionCallback) -> None:
        """Register a callback for streaming partial transcriptions.

        Partials are emitted periodically while speech is ongoing (Phase 2 use).

        Args:
            callback: Async function called with partial TranscriptionResult.
        """
        self._partial_callbacks.append(callback)

    def remove_partial_callback(self, callback: TranscriptionCallback) -> None:
        """Remove a registered partial callback.

        Args:
            callback: Previously registered callback to remove.
        """
        if callback in self._partial_callbacks:
            self._partial_callbacks.remove(callback)

    @property
    def stats(self) -> dict:
        """Get processor statistics.

        Returns:
            Dict with buffer_size, is_accumulating, and transcription_count.
        """
        return {
            "buffer_size": len(self._audio_buffer),
            "is_accumulating": self._is_accumulating,
            "transcription_count": self._transcription_count,
        }
