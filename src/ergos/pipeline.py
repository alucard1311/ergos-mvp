"""Pipeline orchestration wiring all voice assistant components."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from aiohttp import web

from ergos.audio.types import AudioChunk, AudioFrame
from ergos.audio.vad import VADProcessor
from ergos.config import Config
from ergos.llm.generator import LLMGenerator
from ergos.llm.processor import LLMProcessor
from ergos.persona.loader import DEFAULT_PERSONA, load_persona
from ergos.state import ConversationStateMachine
from ergos.stt.processor import STTProcessor
from ergos.stt.transcriber import WhisperTranscriber
from ergos.transport.audio_track import TTSAudioTrack
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler
from ergos.transport.signaling import create_signaling_app
from ergos.tts.processor import TTSProcessor
from ergos.tts.synthesizer import TTSSynthesizer

logger = logging.getLogger(__name__)


@dataclass
class Pipeline:
    """Container for all pipeline components.

    Holds references to all voice assistant components and their
    interconnections. Created by create_pipeline() which handles
    all the wiring.
    """

    config: Config
    state_machine: ConversationStateMachine
    vad_processor: VADProcessor
    stt_processor: STTProcessor
    llm_processor: LLMProcessor
    tts_processor: TTSProcessor
    connection_manager: ConnectionManager
    data_handler: DataChannelHandler
    app: web.Application


async def create_pipeline(config: Config) -> Pipeline:
    """Create and wire all pipeline components.

    This is the main factory function that instantiates all voice
    assistant components and wires them together via callbacks.

    The callback flow is:
        1. Incoming audio -> STT processor (via on_incoming_audio)
        2. VAD events -> STT processor (via vad_processor callbacks)
        3. STT transcription -> LLM processor (via transcription callback)
        4. LLM tokens -> TTS processor (via token callback)
        5. TTS audio -> WebRTC tracks (via audio callback)
        6. State changes -> Data channels (via state machine listener)

    Args:
        config: The application configuration.

    Returns:
        A fully wired Pipeline ready to process voice interactions.
    """
    logger.info("Creating voice pipeline...")

    # 1. Instantiate state machine
    state_machine = ConversationStateMachine()
    logger.debug("Created state machine")

    # 2. Instantiate VAD processor
    vad_processor = VADProcessor()
    logger.debug("Created VAD processor")

    # 3. Instantiate STT components
    transcriber = WhisperTranscriber(
        model_size=config.stt.model,
        device=config.stt.device,
    )
    stt_processor = STTProcessor(transcriber=transcriber)
    logger.debug("Created STT processor")

    # 4. Instantiate LLM components
    # Load persona from file if specified, otherwise use default
    if config.persona.persona_file:
        persona = load_persona(config.persona.persona_file)
    else:
        persona = DEFAULT_PERSONA
        # Override with inline config if provided
        if config.persona.system_prompt != "You are a helpful voice assistant.":
            from ergos.persona.types import Persona
            persona = Persona(
                name=config.persona.name,
                description="a helpful voice assistant",
                personality_traits=["helpful", "concise"],
                voice="af_sarah",
                speaking_style="conversational",
            )
            # Use inline system prompt directly
            system_prompt = config.persona.system_prompt
        else:
            system_prompt = persona.system_prompt

    # Use persona's system prompt unless overridden
    if config.persona.persona_file:
        system_prompt = persona.system_prompt

    # Create LLM generator if model path is configured
    llm_processor: Optional[LLMProcessor] = None
    if config.llm.model_path:
        generator = LLMGenerator(
            model_path=config.llm.model_path,
            n_ctx=config.llm.context_length,
        )
        llm_processor = LLMProcessor(
            generator=generator,
            system_prompt=system_prompt,
        )
        logger.debug("Created LLM processor")
    else:
        logger.warning("No LLM model path configured - LLM processing disabled")
        # Create a placeholder processor for the pipeline structure
        # In real use, the model path should be configured
        generator = LLMGenerator(
            model_path="",  # Will fail on first use if called
            n_ctx=config.llm.context_length,
        )
        llm_processor = LLMProcessor(
            generator=generator,
            system_prompt=system_prompt,
        )

    # 5. Instantiate TTS components
    # Note: TTS requires model files - these paths should be in config in future
    tts_synthesizer = TTSSynthesizer(
        model_path="kokoro-v1.0.onnx",
        voices_path="voices-v1.0.bin",
    )
    tts_processor = TTSProcessor(synthesizer=tts_synthesizer)
    logger.debug("Created TTS processor")

    # 6. Create connection manager
    connection_manager = ConnectionManager()
    logger.debug("Created connection manager")

    # 7. Create data channel handler
    data_handler = DataChannelHandler(
        vad_processor=vad_processor,
        state_machine=state_machine,
    )
    logger.debug("Created data channel handler")

    # ========== Wire callbacks ==========

    # Register state change broadcast via data channels
    state_machine.add_callback(data_handler.get_state_callback())
    logger.debug("Wired: state machine -> data channel broadcast")

    # Register STT processor as VAD event listener
    vad_processor.add_callback(stt_processor.on_vad_event)
    logger.debug("Wired: VAD -> STT processor")

    # Register LLM processor as STT transcription callback
    stt_processor.add_transcription_callback(llm_processor.process_transcription)
    logger.debug("Wired: STT -> LLM processor")

    # Register TTS processor as LLM token callback
    llm_processor.add_token_callback(tts_processor.receive_token)
    logger.debug("Wired: LLM -> TTS processor")

    # Create audio output callback that pushes to all TTSAudioTracks
    async def on_tts_audio(samples: np.ndarray, sample_rate: int) -> None:
        """Push TTS audio samples to all connected WebRTC tracks."""
        for pc in list(connection_manager._connections):
            track = connection_manager.get_track(pc)
            if track is not None:
                track.push_audio(samples)

    tts_processor.add_audio_callback(on_tts_audio)
    logger.debug("Wired: TTS -> WebRTC audio tracks")

    # Register TTS buffer clear as barge-in callback
    async def on_barge_in() -> None:
        """Clear TTS buffer on barge-in."""
        tts_processor.clear_buffer()
        # Also clear audio queues in all tracks
        for pc in list(connection_manager._connections):
            track = connection_manager.get_track(pc)
            if track is not None:
                track.clear()

    state_machine.add_barge_in_callback(on_barge_in)
    logger.debug("Wired: barge-in -> TTS buffer clear")

    # Create on_incoming_audio callback to bridge WebRTC audio to STT
    # This keeps a sequence counter for AudioChunk creation
    _audio_sequence = [0]  # Use list to allow modification in closure

    async def on_incoming_audio(samples: np.ndarray, sample_rate: int) -> None:
        """Route incoming WebRTC audio to STT pipeline."""
        # Convert samples to bytes (int16 format expected by STT)
        if samples.dtype == np.float32:
            # Convert from float32 [-1, 1] to int16
            int_samples = (samples * 32767).astype(np.int16)
        else:
            int_samples = samples.astype(np.int16)

        audio_bytes = int_samples.tobytes()

        # Create AudioFrame and AudioChunk
        frame = AudioFrame(
            data=audio_bytes,
            sample_rate=sample_rate,
        )
        chunk = AudioChunk(
            frame=frame,
            sequence=_audio_sequence[0],
            is_speech=None,  # VAD runs on client, classification comes via data channel
        )
        _audio_sequence[0] += 1

        # Feed to STT processor
        await stt_processor.on_audio_chunk(chunk)

    # Create signaling app with all handlers
    app = create_signaling_app(
        manager=connection_manager,
        data_handler=data_handler,
        on_incoming_audio=on_incoming_audio,
    )
    logger.debug("Created signaling app")

    logger.info("Pipeline created and wired successfully")

    return Pipeline(
        config=config,
        state_machine=state_machine,
        vad_processor=vad_processor,
        stt_processor=stt_processor,
        llm_processor=llm_processor,
        tts_processor=tts_processor,
        connection_manager=connection_manager,
        data_handler=data_handler,
        app=app,
    )
