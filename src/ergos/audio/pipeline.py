import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Awaitable

from ergos.audio.types import AudioFrame, AudioChunk
from ergos.audio.buffer import AudioInputStream, AudioOutputStream
from ergos.audio.vad import VADProcessor, VADEvent, VADEventType

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """State of the audio pipeline."""
    IDLE = "idle"  # Not processing
    LISTENING = "listening"  # Receiving audio, waiting for speech
    PROCESSING = "processing"  # Processing speech (STT → LLM)
    SPEAKING = "speaking"  # Playing TTS output


# Type alias for audio processing callbacks
AudioCallback = Callable[[AudioChunk], Awaitable[None]]


@dataclass
class AudioPipeline:
    """
    Coordinates audio input/output with VAD-driven state management.

    This is the central audio coordinator that:
    - Receives audio from input stream (from WebRTC)
    - Processes VAD events from client
    - Routes audio to STT when speech detected
    - Sends TTS output to output stream
    """

    input_stream: AudioInputStream = field(default_factory=AudioInputStream)
    output_stream: AudioOutputStream = field(default_factory=AudioOutputStream)
    vad_processor: VADProcessor = field(default_factory=VADProcessor)

    _state: PipelineState = field(default=PipelineState.IDLE, init=False)
    _audio_callbacks: list[AudioCallback] = field(default_factory=list, init=False)
    _running: bool = field(default=False, init=False)
    _process_task: Optional[asyncio.Task] = field(default=None, init=False)

    def __post_init__(self):
        # Register for VAD events
        self.vad_processor.add_callback(self._on_vad_event)

    async def start(self) -> None:
        """Start the audio pipeline."""
        if self._running:
            logger.warning("Pipeline already running")
            return

        self._running = True
        self._state = PipelineState.LISTENING
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info("Audio pipeline started")

    async def stop(self) -> None:
        """Stop the audio pipeline."""
        if not self._running:
            return

        self._running = False
        self._state = PipelineState.IDLE

        # Close streams
        self.input_stream.close()
        self.output_stream.close()

        # Wait for process task
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None

        logger.info("Audio pipeline stopped")

    async def _process_loop(self) -> None:
        """Main processing loop for incoming audio."""
        logger.debug("Pipeline process loop started")

        try:
            async for chunk in self.input_stream:
                if not self._running:
                    break

                # Mark chunk with VAD state
                chunk.is_speech = self.vad_processor.is_speech_active

                # Notify audio callbacks (e.g., STT processor)
                for callback in self._audio_callbacks:
                    try:
                        await callback(chunk)
                    except Exception as e:
                        logger.error(f"Audio callback error: {e}")

        except asyncio.CancelledError:
            logger.debug("Pipeline process loop cancelled")
        except Exception as e:
            logger.error(f"Pipeline process loop error: {e}")

        logger.debug("Pipeline process loop ended")

    async def _on_vad_event(self, event: VADEvent) -> None:
        """Handle VAD events for state management."""
        if event.type == VADEventType.SPEECH_START:
            if self._state == PipelineState.LISTENING:
                logger.debug("VAD triggered: transitioning to processing")
                # State machine will handle full transition in Phase 4

        elif event.type == VADEventType.SPEECH_END:
            if self._state == PipelineState.LISTENING:
                logger.debug("VAD ended: speech segment complete")
                # State machine will trigger STT processing

    def add_audio_callback(self, callback: AudioCallback) -> None:
        """Register a callback for processed audio chunks."""
        self._audio_callbacks.append(callback)

    def remove_audio_callback(self, callback: AudioCallback) -> None:
        """Remove an audio callback."""
        if callback in self._audio_callbacks:
            self._audio_callbacks.remove(callback)

    async def receive_audio(self, data: bytes) -> bool:
        """
        Receive audio data from external source (e.g., WebRTC).

        Returns True if successfully buffered.
        """
        return await self.input_stream.write(data)

    async def send_audio(self, frame: AudioFrame) -> bool:
        """
        Queue audio for output (e.g., TTS).

        Returns True if successfully buffered.
        """
        return await self.output_stream.write(frame)

    async def get_output_chunk(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """Get next audio chunk to send to client."""
        return await self.output_stream.read(timeout=timeout)

    async def process_vad_event(self, event_type: str, data: dict) -> None:
        """Process a VAD event from the data channel."""
        await self.vad_processor.process_raw_event(event_type, data)

    @property
    def state(self) -> PipelineState:
        return self._state

    @state.setter
    def state(self, value: PipelineState) -> None:
        if value != self._state:
            logger.info(f"Pipeline state: {self._state.value} → {value.value}")
            self._state = value

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {
            "state": self._state.value,
            "running": self._running,
            "input_stats": self.input_stream.stats,
            "output_stats": self.output_stream.stats,
            "vad_stats": self.vad_processor.stats,
        }
