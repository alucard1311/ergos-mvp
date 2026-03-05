"""STT processor with VAD integration for speech-bounded transcription."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from ergos.audio.types import AudioChunk
from ergos.audio.vad import VADEvent, VADEventType
from ergos.stt.filter import TranscriptionFilter
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

    # Target sample rate for Whisper
    target_sample_rate: int = 16000

    # Internal state (not init params)
    _filter: TranscriptionFilter = field(default_factory=TranscriptionFilter, init=False)
    _audio_buffer: bytearray = field(default_factory=bytearray, init=False)
    _source_sample_rate: int = field(default=16000, init=False)  # Track source rate
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
    _no_result_callbacks: list[TranscriptionCallback] = field(
        default_factory=list, init=False
    )

    async def on_audio_chunk(self, chunk: AudioChunk) -> None:
        """Called by AudioPipeline for each audio chunk.

        Accumulates audio data when speech is active or accumulation is in progress.

        Args:
            chunk: Audio chunk from the pipeline with speech classification.
        """
        if chunk.is_speech or self._is_accumulating:
            self._audio_buffer.extend(chunk.data)
            # Track source sample rate from first chunk
            self._source_sample_rate = chunk.frame.sample_rate

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
        import numpy as np
        import wave

        audio_bytes = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        # Convert to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

        # DEBUG: Log sample count and compute implied duration at reported rate
        sample_count = len(audio_array)
        implied_duration_at_reported_rate = sample_count / self._source_sample_rate
        logger.info(
            "STT DEBUG: %d samples, reported rate=%dHz, implied duration=%.2fs",
            sample_count, self._source_sample_rate, implied_duration_at_reported_rate
        )

        # Convert to float for processing
        audio_float = audio_array.astype(np.float32)

        # Resample if needed (e.g., 48kHz WebRTC -> 16kHz Whisper)
        if self._source_sample_rate != self.target_sample_rate:
            from scipy.signal import resample_poly
            # Use polyphase resampling - stable and efficient
            logger.info(
                "STT: Resampling %d samples from %dHz to %dHz",
                len(audio_array), self._source_sample_rate, self.target_sample_rate
            )
            down_factor = self._source_sample_rate // self.target_sample_rate
            audio_float = resample_poly(audio_float, up=1, down=down_factor)

        # Apply gain normalization to entire buffer (not per-chunk)
        # Target peak around 50% of int16 max for good dynamic range
        # Some Android devices capture very quiet audio, so we need aggressive gain
        peak = max(abs(audio_float.min()), abs(audio_float.max()))
        if peak > 0 and peak < 20000:  # Amplify if below ~60% of full range
            target_peak = 20000
            gain = min(target_peak / peak, 50.0)  # Cap gain at 50x for very quiet input
            audio_float = audio_float * gain
            logger.debug("STT: Applied gain %.1fx (peak was %.0f, new peak %.0f)", gain, peak, peak * gain)

        audio_array = np.clip(audio_float, -32768, 32767).astype(np.int16)

        # Less than 100ms at target rate
        min_samples = int(self.target_sample_rate * 0.1)  # 100ms
        if len(audio_array) < min_samples:
            logger.debug("STT: Audio too short (%d samples), skipping", len(audio_array))
            return

        logger.debug("STT: Processing %d samples of audio", len(audio_array))

        # Convert back to bytes
        audio_bytes = audio_array.tobytes()

        # Save audio for debugging
        debug_path = "/tmp/ergos_debug_audio.wav"
        with wave.open(debug_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.target_sample_rate)
            wf.writeframes(audio_bytes)
        logger.debug("STT: Saved debug audio to %s", debug_path)

        # Run transcription in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self.transcriber.transcribe, audio_bytes, self.target_sample_rate
            )
        except Exception as e:
            logger.error("STT transcription error: %s", e)
            await self._fire_no_result_callbacks()
            return

        logger.debug("STT: Raw transcription result: %s", repr(result.text))
        if result.text.strip():
            # Apply intelligent filter (hallucinations, confidence, repetitions)
            filtered = self._filter.filter(result)
            if filtered is None:
                logger.debug("STT: Filtered out: %s", repr(result.text))
                await self._fire_no_result_callbacks()
                return
            if filtered.text != result.text:
                logger.info("STT: Cleaned: %r -> %r", result.text, filtered.text)
            result = filtered

            logger.info("STT: %s", result.text)
            self._transcription_count += 1
            logger.debug("STT: Calling %d transcription callbacks", len(self._transcription_callbacks))
            for callback in self._transcription_callbacks:
                try:
                    await callback(result)
                except Exception as e:
                    logger.error("Transcription callback error: %s", e)
        else:
            logger.warning("STT: Empty transcription result, skipping callbacks")
            await self._fire_no_result_callbacks()

    async def _start_partial_loop(self) -> None:
        """Periodically transcribe partial audio while speaking."""
        import numpy as np

        while self._is_accumulating and self.enable_partials:
            await asyncio.sleep(self.partial_interval_ms / 1000)

            if not self._is_accumulating:
                break

            current_buffer = bytes(self._audio_buffer)

            # At least 200ms of audio at source rate
            # (200ms * source_rate samples/sec * 2 bytes/sample)
            min_bytes = int(0.2 * self._source_sample_rate * 2)
            if len(current_buffer) < min_bytes:
                continue

            # Convert to numpy and resample if needed (same as final transcription)
            audio_array = np.frombuffer(current_buffer, dtype=np.int16)
            audio_float = audio_array.astype(np.float32)

            if self._source_sample_rate != self.target_sample_rate:
                from scipy.signal import resample_poly

                down_factor = self._source_sample_rate // self.target_sample_rate
                audio_float = resample_poly(audio_float, up=1, down=down_factor)

            audio_resampled = np.clip(audio_float, -32768, 32767).astype(np.int16)
            resampled_bytes = audio_resampled.tobytes()

            # Run partial transcription in thread pool
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, self.transcriber.transcribe, resampled_bytes, self.target_sample_rate
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

    async def _fire_no_result_callbacks(self) -> None:
        """Notify listeners that STT produced no actionable result."""
        for callback in self._no_result_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.error("No-result callback error: %s", e)

    def add_no_result_callback(self, callback) -> None:
        """Register a callback for when transcription produces no result.

        Fires when transcription is filtered out (low confidence,
        hallucination) or empty. Allows the pipeline to reset state.
        """
        self._no_result_callbacks.append(callback)

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
