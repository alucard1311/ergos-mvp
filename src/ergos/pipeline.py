"""Pipeline orchestration wiring all voice assistant components."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from aiohttp import web

from ergos.audio.types import AudioChunk, AudioFrame
from ergos.audio.vad import VADProcessor, VADEvent, VADEventType
from ergos.config import Config
from ergos.core.vram import VRAMMonitor
from ergos.metrics import LatencyTracker
from ergos.llm.generator import LLMGenerator
from ergos.llm.processor import LLMProcessor
from ergos.plugins import PluginManager
from ergos.persona.loader import DEFAULT_PERSONA, load_persona
from ergos.state import ConversationStateMachine, ConversationState
from ergos.stt.processor import STTProcessor
from ergos.stt.transcriber import WhisperTranscriber
from ergos.transport.audio_track import TTSAudioTrack
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler
from ergos.transport.signaling import create_signaling_app
from ergos.tts.processor import TTSProcessor
from ergos.tts.synthesizer import KokoroSynthesizer

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
    latency_tracker: LatencyTracker
    plugin_manager: PluginManager
    app: web.Application
    vram_monitor: VRAMMonitor

    async def preload_models(self) -> None:
        """Pre-load all AI models to eliminate first-request latency.

        Call this during server startup, before accepting connections.
        Models are loaded in parallel where possible.
        """
        import concurrent.futures

        # Log VRAM budget info before loading
        fits, total_est, available = self.vram_monitor.budget_check()
        if fits:
            logger.info(
                f"VRAM budget OK: ~{total_est:.0f}MB estimated, "
                f"{available:.0f}MB available (budget - headroom)"
            )
        else:
            logger.warning(
                f"VRAM budget exceeded: ~{total_est:.0f}MB estimated but only "
                f"{available:.0f}MB available — may cause OOM errors"
            )

        logger.info("Pre-loading AI models...")

        # Load models in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all model loading tasks
            futures = []

            # STT model (Whisper)
            futures.append(
                loop.run_in_executor(
                    executor,
                    self.stt_processor.transcriber._ensure_model
                )
            )

            # LLM model (llama.cpp)
            futures.append(
                loop.run_in_executor(
                    executor,
                    self.llm_processor.generator._ensure_model
                )
            )

            # TTS model (Kokoro)
            futures.append(
                loop.run_in_executor(
                    executor,
                    self.tts_processor.synthesizer._ensure_model
                )
            )

            # Wait for all to complete
            await asyncio.gather(*futures)

        logger.info("All AI models pre-loaded successfully")

        # Log actual VRAM usage after loading
        snap = self.vram_monitor.snapshot()
        if snap.total_mb > 0:
            logger.info(
                f"GPU VRAM: {snap.used_mb:.0f}MB / {snap.total_mb:.0f}MB "
                f"({snap.utilization_pct:.1f}% utilization)"
            )
        else:
            logger.info("GPU VRAM: not available (CPU mode or torch not installed)")


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

    # 0. Create VRAM monitor and register all v2 models with estimates
    vram_monitor = VRAMMonitor()
    vram_monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
    vram_monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
    if config.tts.engine != "csm":
        vram_monitor.register_model("kokoro-82m", 500.0, "tts")
    logger.debug(
        "Created VRAM monitor with model estimates: STT=1000MB, LLM=5200MB"
    )

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
        compute_type=config.stt.compute_type,
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
            n_gpu_layers=config.llm.n_gpu_layers,
            chat_format=config.llm.chat_format,
        )
        llm_processor = LLMProcessor(
            generator=generator,
            system_prompt=system_prompt,
            chat_format=config.llm.chat_format,
        )
        logger.debug("Created LLM processor")
    else:
        logger.warning("No LLM model path configured - LLM processing disabled")
        # Create a placeholder processor for the pipeline structure
        # In real use, the model path should be configured
        generator = LLMGenerator(
            model_path="",  # Will fail on first use if called
            n_ctx=config.llm.context_length,
            n_gpu_layers=config.llm.n_gpu_layers,
            chat_format=config.llm.chat_format,
        )
        llm_processor = LLMProcessor(
            generator=generator,
            system_prompt=system_prompt,
            chat_format=config.llm.chat_format,
        )

    # 5. Instantiate TTS components
    import os
    if config.tts.engine == "csm":
        from ergos.tts.csm_synthesizer import CSMSynthesizer
        tts_synthesizer = CSMSynthesizer(
            model_id=config.tts.model_id,
            device=config.tts.device,
            reference_audio=config.tts.reference_audio,
        )
        vram_monitor.register_model("csm-1b", 4500.0, "tts")
        logger.debug("Created CSM-1B TTS synthesizer")
    else:
        tts_model_dir = os.path.expanduser("~/.ergos/models/tts")
        tts_synthesizer = KokoroSynthesizer(
            model_path=os.path.join(tts_model_dir, "kokoro-v1.0.onnx"),
            voices_path=os.path.join(tts_model_dir, "voices-v1.0.bin"),
        )
        logger.debug("Created Kokoro TTS synthesizer")
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

    # 8. Create latency tracker
    latency_tracker = LatencyTracker()
    logger.debug("Created latency tracker")

    # 9. Create plugin manager and discover plugins
    plugin_manager = PluginManager()
    plugin_manager.discover_plugins()
    logger.debug(f"Discovered {len(plugin_manager.plugins)} plugins")

    # ========== Wire callbacks ==========

    # Register state change broadcast via data channels
    state_machine.add_callback(data_handler.get_state_callback())
    logger.debug("Wired: state machine -> data channel broadcast")

    # Register state machine transitions for VAD events FIRST
    # (must happen before STT processing to ensure correct state)
    _overlap_timer_task: list[Optional[asyncio.Task]] = [None]  # Track overlap timer for cancellation

    async def on_vad_for_state(event: VADEvent) -> None:
        """Trigger state machine transitions on VAD events.

        Handles full-duplex: when SPEECH_START fires during SPEAKING,
        transitions to SPEAKING_AND_LISTENING with a 500ms overlap window.
        When SPEECH_END fires during SPEAKING_AND_LISTENING, executes
        barge-in immediately and transitions to PROCESSING.
        """
        current_state = state_machine.state

        if event.type == VADEventType.SPEECH_START:
            if current_state in (ConversationState.IDLE, ConversationState.LISTENING):
                await state_machine.start_listening()

            elif current_state == ConversationState.SPEAKING:
                # Transition to full-duplex overlap state
                # AI audio continues for ~500ms overlap window
                success = await state_machine.transition_to(
                    ConversationState.SPEAKING_AND_LISTENING,
                    metadata={"trigger": "speech_start_during_speaking"}
                )
                if success:
                    # Schedule barge-in after 500ms overlap window
                    # If SPEECH_END fires before timer, timer is cancelled
                    async def _overlap_timeout():
                        await asyncio.sleep(0.5)
                        if state_machine.state == ConversationState.SPEAKING_AND_LISTENING:
                            logger.info("Overlap timeout: executing barge-in after 500ms")
                            await state_machine.barge_in()
                            await state_machine.start_processing()

                    _overlap_timer_task[0] = asyncio.create_task(_overlap_timeout())
                    logger.debug("SPEAKING_AND_LISTENING: 500ms overlap timer started")

            elif current_state == ConversationState.SPEAKING_AND_LISTENING:
                # Already in overlap state, ignore additional SPEECH_START
                logger.debug("Ignoring SPEECH_START: already in SPEAKING_AND_LISTENING")

            else:
                logger.debug(f"Ignoring SPEECH_START in state {current_state.value}")

        elif event.type == VADEventType.SPEECH_END:
            # Cancel overlap timer if pending (SPEECH_END fires before 500ms)
            if _overlap_timer_task[0] is not None and not _overlap_timer_task[0].done():
                _overlap_timer_task[0].cancel()
                _overlap_timer_task[0] = None
                logger.debug("SPEAKING_AND_LISTENING: overlap timer cancelled by SPEECH_END")

            if current_state == ConversationState.SPEAKING_AND_LISTENING:
                # User finished speaking during overlap — execute barge-in now
                await state_machine.barge_in()  # Cancels LLM+TTS, transitions to LISTENING
                await state_machine.start_processing()
                logger.info("Barge-in complete: SPEAKING_AND_LISTENING -> PROCESSING")

            elif current_state in (ConversationState.LISTENING,):
                await state_machine.start_processing()

    vad_processor.add_callback(on_vad_for_state)
    logger.debug("Wired: VAD -> state machine transitions (full-duplex with SPEAKING_AND_LISTENING)")

    # Register STT processor as VAD event listener (after state transition)
    vad_processor.add_callback(stt_processor.on_vad_event)
    logger.debug("Wired: VAD -> STT processor")

    # Register latency tracking for VAD speech_end events
    async def on_vad_for_latency(event: VADEvent) -> None:
        """Mark speech_end time for latency tracking."""
        if event.type == VADEventType.SPEECH_END:
            latency_tracker.mark_speech_end()

    vad_processor.add_callback(on_vad_for_latency)
    logger.debug("Wired: VAD -> latency tracker (speech_end)")

    # Register TTS processor as LLM token callback
    llm_processor.add_token_callback(tts_processor.receive_token)
    logger.debug("Wired: LLM -> TTS processor")

    # Register completion callback to flush TTS buffer after LLM finishes
    async def on_llm_complete(result) -> None:
        """Flush TTS buffer and wait for audio to finish before transitioning state."""
        logger.info(f"LLM completed: {len(result.text)} chars, {result.tokens_generated} tokens")
        await tts_processor.flush()

        # Wait for TTS synthesis to complete (in case flush triggered synthesis)
        max_wait = 30.0
        elapsed = 0.0
        while tts_processor.is_synthesizing and elapsed < max_wait:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        # Now wait for audio to actually play out
        # The audio is buffered in tracks - wait for buffer to drain
        # Use a combination of checking track buffers and a timeout based on audio duration
        audio_duration_s = tts_processor.total_audio_duration_ms / 1000.0
        logger.info(f"TTS generated {tts_processor.total_audio_duration_ms:.0f}ms of audio, waiting for playback")

        # Wait for track buffers to drain
        max_wait_seconds = max(audio_duration_s + 5.0, 30.0)  # At least audio duration + buffer
        check_interval = 0.2
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            has_audio = False
            for pc in list(connection_manager._connections):
                track = connection_manager.get_track(pc)
                if track is not None and track.has_audio:
                    has_audio = True
                    buffer_ms = track.buffer_duration_ms
                    logger.debug(f"Track buffer: {buffer_ms:.0f}ms remaining")
                    break

            if not has_audio:
                logger.info("Audio buffers drained, transitioning to IDLE")
                break

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        if elapsed >= max_wait_seconds:
            logger.warning(f"Timeout ({max_wait_seconds:.1f}s) waiting for audio to drain")

        # Reset audio tracking for next utterance
        tts_processor.reset_audio_tracking()

        # Transition back to IDLE after speaking completes
        await state_machine.stop()

    llm_processor.add_completion_callback(on_llm_complete)
    logger.debug("Wired: LLM completion -> TTS flush + state IDLE")

    # Create audio output callback that pushes to all TTSAudioTracks
    _first_audio_sent = [False]  # Track if we've sent first audio chunk

    async def on_tts_audio(samples: np.ndarray, sample_rate: int) -> None:
        """Push TTS audio samples to all connected WebRTC tracks.

        Also marks first audio for latency tracking on the first chunk
        after speech_end, and transitions state to SPEAKING.

        IMPORTANT: Only pushes audio if state allows (PROCESSING or SPEAKING).
        If user interrupts (barge-in), state changes to LISTENING and audio
        is discarded to avoid segfaults from concurrent audio streams.
        """
        current_state = state_machine.state

        # Only push audio if we're in a state that expects TTS output
        # PROCESSING: waiting for first audio (will transition to SPEAKING)
        # SPEAKING: actively playing TTS audio
        # SPEAKING_AND_LISTENING: overlap window — TTS audio continues while user speaks
        if current_state not in (ConversationState.PROCESSING, ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
            logger.debug(
                f"TTS audio discarded: state is {current_state.value}, not PROCESSING/SPEAKING/SPEAKING_AND_LISTENING"
            )
            return

        logger.debug(
            f"TTS audio callback: {len(samples)} samples at {sample_rate}Hz, "
            f"dtype={samples.dtype}, range=[{samples.min():.4f}, {samples.max():.4f}]"
        )

        # Mark first audio for latency tracking
        if latency_tracker.is_waiting_for_audio:
            latency_tracker.mark_first_audio()
            latency_tracker.log_current()
            latency_tracker.reset()

        # Transition to SPEAKING on first audio chunk
        if not _first_audio_sent[0]:
            _first_audio_sent[0] = True
            success = await state_machine.start_speaking()
            if not success:
                logger.warning("Failed to transition to SPEAKING, discarding audio")
                return

        # Double-check state after transition attempt (could have changed)
        if state_machine.state not in (ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
            logger.debug(
                f"State changed during transition, discarding audio "
                f"(state={state_machine.state.value})"
            )
            return

        connections = list(connection_manager._connections)
        logger.debug(f"Pushing audio to {len(connections)} connections")
        for pc in connections:
            track = connection_manager.get_track(pc)
            if track is not None:
                track.push_audio(samples, sample_rate)
            else:
                logger.warning(f"No track found for connection {pc}")

    # Reset flags when entering PROCESSING state (for each new response)
    async def on_vad_reset_flags(event: VADEvent) -> None:
        current_state = state_machine.state

        # Reset on speech_start if we're able to listen
        if event.type == VADEventType.SPEECH_START:
            if current_state in (ConversationState.IDLE, ConversationState.LISTENING, ConversationState.SPEAKING_AND_LISTENING):
                # Reset TTS cancellation so new response can be synthesized
                # SPEAKING_AND_LISTENING: reset needed for post-barge-in response (Pitfall 2 + Pattern 6)
                tts_processor.reset_cancellation()

        # Always reset _first_audio_sent when speech ends (entering PROCESSING)
        # This ensures the next TTS response triggers SPEAKING transition
        if event.type == VADEventType.SPEECH_END:
            _first_audio_sent[0] = False
            logger.debug("Reset _first_audio_sent flag for new response")

    vad_processor.add_callback(on_vad_reset_flags)

    tts_processor.add_audio_callback(on_tts_audio)
    logger.debug("Wired: TTS -> WebRTC audio tracks (with latency tracking)")

    # ========== Barge-in cancellation ==========
    async def on_barge_in() -> None:
        """Cancel LLM generation, TTS synthesis, and clear audio buffers on barge-in.

        Called by state_machine.barge_in() before transitioning to LISTENING.
        Execution order matters: cancel generation flag first, then synthesis,
        then clear audio buffers to prevent re-queuing.
        """
        logger.info("Barge-in: executing cancel sequence")

        # 1. Cancel LLM generation (flag-based, stops at next token check)
        generator.cancel()

        # 2. Cancel TTS synthesis (flag-based + clears text buffer)
        await tts_processor.cancel()

        # 3. Reset _first_audio_sent so next response triggers SPEAKING transition
        _first_audio_sent[0] = False

        # 4. Clear audio track buffers (thread-safe, immediate)
        for pc in list(connection_manager._connections):
            track = connection_manager.get_track(pc)
            if track is not None:
                track.clear()

        logger.info("Barge-in: cancel sequence complete")

    state_machine.add_barge_in_callback(on_barge_in)
    logger.debug("Barge-in callback wired: LLM cancel + TTS cancel + track clear")

    # ========== Plugin Integration ==========

    # Create speak callback for plugins
    # This allows plugins to speak text via TTS
    async def plugin_speak_callback(text: str) -> None:
        """Speak text via TTS for plugins.

        Feeds text to TTS processor and handles state transitions.
        """
        logger.info(f"Plugin speaking: {text[:50]}...")

        # Transition to PROCESSING state first (required for TTS audio to be accepted)
        current_state = state_machine.state
        if current_state == ConversationState.IDLE:
            await state_machine.start_listening()
            await state_machine.start_processing()
        elif current_state == ConversationState.LISTENING:
            await state_machine.start_processing()

        # Reset TTS state for new utterance
        tts_processor.reset_cancellation()
        tts_processor.clear_buffer()
        _first_audio_sent[0] = False

        # Feed text to TTS (it will synthesize on sentence boundaries)
        for char in text:
            await tts_processor.receive_token(char)

        # Flush remaining text
        await tts_processor.flush()

        # Wait for synthesis to complete
        max_wait = 30.0
        elapsed = 0.0
        while tts_processor.is_synthesizing and elapsed < max_wait:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        # Wait for audio to play out
        audio_duration_s = tts_processor.total_audio_duration_ms / 1000.0
        max_wait_seconds = max(audio_duration_s + 2.0, 10.0)
        check_interval = 0.2
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            has_audio = False
            for pc in list(connection_manager._connections):
                track = connection_manager.get_track(pc)
                if track is not None and track.has_audio:
                    has_audio = True
                    break

            if not has_audio:
                break

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        # Reset for next utterance
        tts_processor.reset_audio_tracking()

        # Return to IDLE state
        await state_machine.stop()

    # Attach plugins to Ergos components
    plugin_manager.attach_all(
        llm=llm_processor.generator,
        tts=tts_processor,
        state_machine=state_machine,
        speak_callback=plugin_speak_callback,
    )
    logger.debug("Attached plugins to Ergos components")

    # Create transcription callback that routes through plugins first
    async def on_transcription_with_plugins(result) -> None:
        """Route transcription to plugins or LLM.

        Checks if any plugin should handle the input. If so, routes
        to the plugin. Otherwise, passes through to LLM processor.
        """
        text = result.text
        logger.info(f"Transcription: {text}")

        # Check if a plugin should handle this
        plugin = plugin_manager.route_input(text)

        if plugin is not None:
            logger.info(f"Routing to plugin: {plugin.name}")
            try:
                handled = await plugin.handle_input(text)
                if handled:
                    logger.debug(f"Plugin {plugin.name} handled input")
                    return
                else:
                    logger.debug(f"Plugin {plugin.name} passed through")
            except Exception as e:
                logger.error(f"Plugin error: {e}")
                # Deactivate plugin on error
                await plugin_manager.deactivate_current()

        # No plugin handled it, pass to LLM
        await llm_processor.process_transcription(result)

    # Replace the direct LLM callback with plugin-aware routing
    # First remove the direct callback, then add the routing callback
    stt_processor.remove_transcription_callback(llm_processor.process_transcription)
    stt_processor.add_transcription_callback(on_transcription_with_plugins)
    logger.debug("Wired: STT -> Plugin router -> LLM processor")

    # Create text input handler for direct text commands (e.g., mode switching)
    async def on_text_input(text: str) -> None:
        """Handle direct text input from data channel.

        Routes text to plugins, similar to transcription handling.
        Used for mode switching commands sent from the Flutter client.
        """
        logger.info(f"Text input: {text}")

        # Check if a plugin should handle this
        plugin = plugin_manager.route_input(text)

        if plugin is not None:
            logger.info(f"Routing text input to plugin: {plugin.name}")
            try:
                handled = await plugin.handle_input(text)
                if handled:
                    logger.debug(f"Plugin {plugin.name} handled text input")
                    return
                else:
                    logger.debug(f"Plugin {plugin.name} passed through text input")
            except Exception as e:
                logger.error(f"Plugin error on text input: {e}")
                await plugin_manager.deactivate_current()

        # No plugin handled it - for text input, we just log and ignore
        # (unlike transcription, we don't pass unhandled text to LLM)
        logger.debug("Text input not handled by any plugin")

    # Wire text input callback to data handler
    data_handler.set_text_input_callback(on_text_input)
    logger.debug("Wired: Data channel text input -> Plugin router")

    # Create on_incoming_audio callback to bridge WebRTC audio to STT
    # This keeps a sequence counter for AudioChunk creation
    _audio_sequence = [0]  # Use list to allow modification in closure

    async def on_incoming_audio(samples: np.ndarray, sample_rate: int) -> None:
        """Route incoming WebRTC audio to STT pipeline.

        Processes audio in IDLE, LISTENING, or SPEAKING_AND_LISTENING states.
        SPEAKING_AND_LISTENING: user is speaking while AI is speaking — route to STT
        for barge-in transcription. Ignores audio during PROCESSING and SPEAKING.
        """
        # Only listen when in IDLE, LISTENING, or SPEAKING_AND_LISTENING state
        current_state = state_machine.state
        if current_state not in (ConversationState.IDLE, ConversationState.LISTENING, ConversationState.SPEAKING_AND_LISTENING):
            # Silently ignore audio during processing/speaking
            return

        logger.debug(f"Incoming audio: {len(samples)} samples, rate={sample_rate}, dtype={samples.dtype}, range=[{samples.min():.4f}, {samples.max():.4f}]")

        # Pass raw audio to STT at original sample rate
        # STT processor will resample once after accumulating all audio
        # This avoids resampling artifacts from processing small chunks independently

        # Convert samples to bytes (int16 format expected by STT)
        int_samples = np.clip(samples, -32768, 32767).astype(np.int16)

        logger.debug(f"Int16 range: [{int_samples.min()}, {int_samples.max()}]")

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
        latency_tracker=latency_tracker,
        plugin_manager=plugin_manager,
        app=app,
        vram_monitor=vram_monitor,
    )
