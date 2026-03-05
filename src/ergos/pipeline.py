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
from ergos.llm.cloud_generator import CloudLLMGenerator
from ergos.llm.fallback_generator import FallbackLLMGenerator
from ergos.plugins import PluginManager
from ergos.persona.loader import DEFAULT_PERSONA, load_persona
from ergos.persona.builder import ErgosPromptBuilder, get_time_context, try_sarcasm_command
from ergos.memory import MemoryStore, MemoryEntry
from ergos.memory.store import EXTRACTION_PROMPT, parse_extraction_result, format_history_for_extraction
from ergos.state import ConversationStateMachine, ConversationState
from ergos.stt.processor import STTProcessor
from ergos.stt.transcriber import WhisperTranscriber
from ergos.transport.audio_track import TTSAudioTrack
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler
from ergos.transport.signaling import create_signaling_app
from ergos.tts.processor import TTSProcessor
from ergos.tts.synthesizer import TTSSynthesizer

logger = logging.getLogger(__name__)

# Default tool registry YAML content — shipped built-in and written to ~/.ergos/tools/
# on first server start when tools are enabled. Mirrors tools/default.yaml.
_DEFAULT_TOOLS_YAML = """\
# Default tool registry for Ergos agentic execution
#
# Add new tools by creating additional .yaml files in the same directory.
# Tools are hot-reloadable via ToolRegistry.reload() without server restart.
#
# Shell command security: shell_run enforces allowed_prefixes.
# Commands not starting with a listed prefix are rejected with an error message.
# Remove allowed_prefixes entirely to allow any command (use with caution).

tools:
  - name: file_read
    description: "Read the contents of a file at the given path"
    impl: builtin.file_read
    parameters:
      type: object
      properties:
        path:
          type: string
          description: "Absolute or home-relative file path (e.g., ~/notes.txt)"
      required: [path]

  - name: shell_run
    description: "Run a shell command and return stdout+stderr. Timeout is 10 seconds."
    impl: builtin.shell_run
    allowed_prefixes:
      - "ls"
      - "cat"
      - "head"
      - "tail"
      - "wc"
      - "find"
      - "grep"
      - "echo"
      - "pwd"
      - "whoami"
      - "date"
      - "df"
      - "du"
      - "uname"
      - "python3"
      - "uv run"
    parameters:
      type: object
      properties:
        command:
          type: string
          description: "Shell command to execute (must start with an allowed prefix)"
        timeout_seconds:
          type: integer
          description: "Max seconds to wait (default 10, max 30)"
      required: [command]

  - name: file_list
    description: "List files in a directory matching an optional glob pattern"
    impl: builtin.file_list
    parameters:
      type: object
      properties:
        directory:
          type: string
          description: "Directory to list (supports ~ expansion)"
        pattern:
          type: string
          description: "Optional glob pattern, e.g. '*.py'. Default is '*' (all files)."
      required: [directory]
"""


def _ensure_default_tools(tools_dir: str) -> None:
    """Create default tool registry YAML if tools directory has no YAML files.

    Called at pipeline startup when tools are enabled. Creates ~/.ergos/tools/
    and writes default.yaml if the directory is missing or has no YAML files.
    This allows the server to work out of the box without manual file setup.

    Args:
        tools_dir: Path to tools directory (supports ~ expansion).
    """
    import os
    expanded = os.path.expanduser(tools_dir)
    os.makedirs(expanded, exist_ok=True)

    # Check if any YAML files exist
    import glob as _glob
    existing_yamls = _glob.glob(os.path.join(expanded, "*.yaml")) + _glob.glob(
        os.path.join(expanded, "*.yml")
    )
    if not existing_yamls:
        default_path = os.path.join(expanded, "default.yaml")
        with open(default_path, "w") as f:
            f.write(_DEFAULT_TOOLS_YAML)
        logger.info(f"Created default tool registry at {default_path}")
    else:
        logger.debug(f"Tool registry directory already has YAML files: {existing_yamls}")


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

        # Load models sequentially in thread pool to avoid llama.cpp
        # thread-safety issues (both LLM and Orpheus TTS use llama.cpp)
        loop = asyncio.get_event_loop()

        # STT model (Whisper) — independent, can load first
        await loop.run_in_executor(
            None, self.stt_processor.transcriber._ensure_model
        )

        # LLM model (llama.cpp) — must finish before Orpheus starts
        # FallbackLLMGenerator wraps cloud+local; CloudLLMGenerator has no local model
        gen = self.llm_processor.generator
        if hasattr(gen, '_local'):
            gen = gen._local
        if hasattr(gen, '_ensure_model'):
            await loop.run_in_executor(None, gen._ensure_model)

        # TTS model (Orpheus/Kokoro) — also uses llama.cpp, load after LLM
        await loop.run_in_executor(
            None, self.tts_processor.synthesizer._ensure_model
        )

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
    if config.tts.engine not in ("csm", "orpheus"):
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

    # If Ergos persona (default or from file), use ErgosPromptBuilder
    prompt_builder = None
    memory_store = MemoryStore()
    current_sarcasm_level = [config.persona.sarcasm_level]  # Mutable for voice command updates

    if persona.is_ergos_persona:
        prompt_builder = ErgosPromptBuilder()
        # Load memories for prompt injection
        all_memories = memory_store.load()
        budget_memories = memory_store.get_budget(all_memories)
        memory_strings = [m.content for m in budget_memories]
        time_context = get_time_context()

        system_prompt = prompt_builder.build(
            name=persona.name,
            sarcasm_level=current_sarcasm_level[0],
            memories=memory_strings,
            time_context=time_context,
        )
        logger.info(
            f"Ergos persona active: sarcasm={current_sarcasm_level[0]}%, "
            f"{len(budget_memories)} memories loaded"
        )
    # else: system_prompt already set from persona.system_prompt or inline config (existing behavior unchanged)

    # Create LLM generator(s) based on config:
    # - Both model_path + cloud_endpoint_url → FallbackGenerator (cloud-first, local fallback)
    # - Only model_path → Local LLMGenerator (current behavior)
    # - Only cloud_endpoint_url → CloudLLMGenerator (cloud only)
    llm_processor: Optional[LLMProcessor] = None
    local_generator = None
    cloud_generator = None

    if config.llm.model_path:
        local_generator = LLMGenerator(
            model_path=config.llm.model_path,
            n_ctx=config.llm.context_length,
            n_gpu_layers=config.llm.n_gpu_layers,
            chat_format=config.llm.chat_format,
        )

    if config.llm.cloud_endpoint_url:
        cloud_generator = CloudLLMGenerator(
            endpoint_url=config.llm.cloud_endpoint_url,
            api_key=config.llm.cloud_api_key or "",
            model_name=config.llm.cloud_model_name,
            timeout=config.llm.cloud_timeout,
            chat_format=config.llm.chat_format,
            n_ctx=config.llm.context_length,
            max_tokens=config.llm.max_tokens,
        )

    if cloud_generator and local_generator:
        generator = FallbackLLMGenerator(cloud_generator, local_generator)
        logger.info("LLM: Cloud-first with local fallback")
    elif cloud_generator:
        generator = cloud_generator
        logger.info("LLM: Cloud only (no local fallback)")
    elif local_generator:
        generator = local_generator
        logger.info("LLM: Local only")
    else:
        logger.warning("No LLM model path or cloud endpoint configured - LLM processing disabled")
        generator = LLMGenerator(
            model_path="",  # Will fail on first use if called
            n_ctx=config.llm.context_length,
            n_gpu_layers=config.llm.n_gpu_layers,
            chat_format=config.llm.chat_format,
        )

    llm_processor = LLMProcessor(
        generator=generator,
        system_prompt=system_prompt,
        max_tokens=config.llm.max_tokens,
        chat_format=config.llm.chat_format,
    )
    logger.debug("Created LLM processor")

    # 4b. Instantiate tool execution infrastructure (if enabled)
    tool_processor = None
    tool_registry = None
    if config.tools.enabled and config.llm.model_path:
        from ergos.tools import ToolRegistry, ToolExecutor
        from ergos.llm.tool_processor import ToolCallProcessor

        # Ensure default tools exist on first run
        _ensure_default_tools(config.tools.tools_dir)

        tool_registry = ToolRegistry(tools_dir=config.tools.tools_dir)
        tool_registry.load()

        if tool_registry.has_tools:
            tool_executor = ToolExecutor(impl_map=tool_registry.get_impl_map(), registry=tool_registry)
            tool_processor = ToolCallProcessor(
                generator=generator,
                registry=tool_registry,
                executor=tool_executor,
                system_prompt=system_prompt,
                max_steps=config.tools.max_steps,
            )
            logger.info(f"Tool processor enabled: {len(tool_registry.get_tools())} tools loaded")
        else:
            logger.info("Tools enabled but no tools found in registry")
    else:
        if not config.tools.enabled:
            logger.info("Tool processor disabled (tools.enabled=false in config)")
        elif not config.llm.model_path:
            logger.info("Tool processor disabled (no LLM model path configured)")

    # 5. Instantiate TTS components
    import os
    from ergos.tts.types import SynthesisConfig as _SynthesisConfig

    if config.tts.engine == "csm":
        from ergos.tts.csm_synthesizer import CSMSynthesizer
        tts_synthesizer = CSMSynthesizer(
            model_id=config.tts.model_id,
            device=config.tts.device,
            reference_audio=config.tts.reference_audio,
        )
        vram_monitor.register_model("csm-1b", 4500.0, "tts")
        logger.debug("Created CSM-1B TTS synthesizer")
    elif config.tts.engine == "orpheus":
        from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer
        tts_synthesizer = OrpheusSynthesizer(
            n_gpu_layers=config.tts.orpheus_n_gpu_layers,
            lang="en",
            verbose=False,
        )
        vram_monitor.register_model("orpheus-3b-q4", 2000.0, "tts")
        logger.debug("Created Orpheus TTS synthesizer")
    else:
        # Default: Kokoro
        tts_model_dir = os.path.expanduser("~/.ergos/models/tts")
        tts_synthesizer = TTSSynthesizer(
            model_path=os.path.join(tts_model_dir, "kokoro-v1.0.onnx"),
            voices_path=os.path.join(tts_model_dir, "voices-v1.0.bin"),
        )
        logger.debug("Created Kokoro TTS synthesizer")

    # Build SynthesisConfig for TTSProcessor, carrying engine-specific fields
    tts_config = _SynthesisConfig(
        voice=config.tts.voice,
        speed=config.tts.speed,
    )
    if config.tts.engine == "orpheus":
        tts_config.orpheus_voice = config.tts.orpheus_voice

    tts_processor = TTSProcessor(synthesizer=tts_synthesizer, config=tts_config, engine=config.tts.engine)
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

    # Wire model change callback (FallbackLLMGenerator -> client notification)
    # Uses call_soon_threadsafe because fallback can trigger from sync thread context
    if isinstance(generator, FallbackLLMGenerator):
        _loop = asyncio.get_event_loop()
        def _on_model_change(model: str) -> None:
            _loop.call_soon_threadsafe(
                asyncio.ensure_future,
                data_handler.broadcast_model_status(model),
            )
        generator.set_on_model_change(_on_model_change)
        logger.debug("Wired: fallback generator model change -> data channel broadcast")

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

    # ========== Idle timeout state change wiring (registered early, used later) ==========
    # ========== Idle timeout infrastructure ==========
    # Timeout to IDLE after 30s of silence post-response (locked decision from CONTEXT.md)
    _idle_timeout_task: list[Optional[asyncio.Task]] = [None]
    # Safety timeout: if stuck in PROCESSING for 60s (e.g. plugin exception), force IDLE
    _processing_timeout_task: list[Optional[asyncio.Task]] = [None]

    async def _start_idle_timeout() -> None:
        """Start 30s idle timeout. Cancelled when user starts speaking."""
        # Cancel any existing timeout first
        if _idle_timeout_task[0] is not None and not _idle_timeout_task[0].done():
            _idle_timeout_task[0].cancel()

        async def _idle_timeout():
            await asyncio.sleep(30.0)
            current = state_machine.state
            if current == ConversationState.LISTENING:
                logger.info("Idle timeout: 30s without speech, transitioning to IDLE")
                await state_machine.stop()
            elif current == ConversationState.IDLE:
                logger.debug("Idle timeout: already IDLE, no action needed")

        _idle_timeout_task[0] = asyncio.create_task(_idle_timeout())
        logger.debug("Idle timeout: 30s timer started")

    async def _cancel_idle_timeout() -> None:
        """Cancel idle timeout when user starts speaking."""
        if _idle_timeout_task[0] is not None and not _idle_timeout_task[0].done():
            _idle_timeout_task[0].cancel()
            _idle_timeout_task[0] = None
            logger.debug("Idle timeout: cancelled by speech")

    async def _start_processing_timeout() -> None:
        """Start safety timeout when entering PROCESSING.

        If plugin_speak_callback or LLM handling throws an exception before
        calling state_machine.stop(), state stays PROCESSING with no recovery.
        This timeout forces IDLE as a last-resort safety net.
        The primary fix is try/finally in plugin_speak_callback; this is defence-in-depth.

        Timeout is extended to 300s when tool_processor is active to allow multi-step
        agentic execution (each tool call + narration can take several seconds).
        """
        if _processing_timeout_task[0] is not None and not _processing_timeout_task[0].done():
            _processing_timeout_task[0].cancel()

        _PROCESSING_TIMEOUT_S = (
            300.0 if (tool_processor is not None and tool_processor.has_tools) else 60.0
        )

        async def _processing_timeout():
            await asyncio.sleep(_PROCESSING_TIMEOUT_S)
            current = state_machine.state
            if current == ConversationState.PROCESSING:
                logger.warning(
                    f"Processing timeout: stuck in PROCESSING for {_PROCESSING_TIMEOUT_S:.0f}s "
                    "— forcing IDLE (plugin_speak_callback or LLM handler likely threw an unhandled exception)"
                )
                await state_machine.transition_to(ConversationState.IDLE)

        _processing_timeout_task[0] = asyncio.create_task(_processing_timeout())
        logger.debug(f"Processing timeout: {_PROCESSING_TIMEOUT_S:.0f}s safety timer started")

    async def _cancel_processing_timeout() -> None:
        """Cancel processing timeout when state leaves PROCESSING."""
        if _processing_timeout_task[0] is not None and not _processing_timeout_task[0].done():
            _processing_timeout_task[0].cancel()
            _processing_timeout_task[0] = None
            logger.debug("Processing timeout: cancelled")

    # Wire idle timeout to state changes: start 30s timer on IDLE entry, cancel on activity
    async def _on_state_change_for_idle_timeout(event) -> None:
        """Manage idle and processing timeouts on state changes."""
        if event.new_state == ConversationState.IDLE:
            await _cancel_processing_timeout()
            await _start_idle_timeout()
        elif event.new_state == ConversationState.PROCESSING:
            await _cancel_idle_timeout()
            await _start_processing_timeout()
        elif event.new_state == ConversationState.LISTENING:
            await _cancel_idle_timeout()
            await _cancel_processing_timeout()
        elif event.new_state in (ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
            # SPEAKING/SPEAKING_AND_LISTENING: cancel processing timeout (we're no longer stuck)
            await _cancel_processing_timeout()

    state_machine.add_callback(_on_state_change_for_idle_timeout)
    logger.debug("Wired: state machine -> idle timeout manager (30s on IDLE entry, 60s on PROCESSING entry)")

    # Register state machine transitions for VAD events FIRST
    # (must happen before STT processing to ensure correct state)
    _overlap_timer_task: list[Optional[asyncio.Task]] = [None]  # Track overlap timer for cancellation
    # Echo suppression: track when SPEAKING_AND_LISTENING was entered so we can
    # distinguish brief echo activations from real user barge-in.
    _overlap_entry_time: list[Optional[float]] = [None]

    # Minimum sustained speech duration (in seconds) to count as real barge-in.
    # Echo from TTS typically lasts < 500ms in VAD; real speech sustains longer.
    # This threshold must be shorter than the overlap window so short real speech
    # (e.g. "stop") still triggers barge-in on SPEECH_END.
    _MIN_BARGE_IN_DURATION_S = 0.8

    # Overlap window duration. Increased from 0.5s to 1.5s so that:
    #   - Brief echo (< 0.8s sustained) → SPEECH_END before timer → restored to SPEAKING
    #   - Long user speech (> 1.5s sustained without pause) → timer fires → barge-in
    _OVERLAP_WINDOW_S = 1.5

    async def on_vad_for_state(event: VADEvent) -> None:
        """Trigger state machine transitions on VAD events.

        Handles full-duplex: when SPEECH_START fires during SPEAKING,
        transitions to SPEAKING_AND_LISTENING with a 1.5s overlap window.
        When SPEECH_END fires during SPEAKING_AND_LISTENING:
          - If speech was brief (< 0.8s) → likely TTS echo, restore to SPEAKING
          - If speech was sustained (>= 0.8s) → real barge-in, execute immediately
        """
        current_state = state_machine.state

        if event.type == VADEventType.SPEECH_START:
            # Cancel any pending idle timeout — user is speaking
            await _cancel_idle_timeout()

            if current_state in (ConversationState.IDLE, ConversationState.LISTENING):
                await state_machine.start_listening()

            elif current_state == ConversationState.SPEAKING:
                # Ignore VAD during SPEAKING — no AEC means TTS echo from
                # laptop speakers is indistinguishable from real speech.
                # Barge-in is disabled until acoustic echo cancellation is added.
                logger.debug("Ignoring SPEECH_START during SPEAKING (no AEC, echo likely)")

            elif current_state == ConversationState.SPEAKING_AND_LISTENING:
                # Already in overlap state, ignore additional SPEECH_START
                logger.debug("Ignoring SPEECH_START: already in SPEAKING_AND_LISTENING")

            else:
                logger.debug(f"Ignoring SPEECH_START in state {current_state.value}")

        elif event.type == VADEventType.SPEECH_END:
            # Cancel overlap timer if pending (SPEECH_END fires before timeout)
            if _overlap_timer_task[0] is not None and not _overlap_timer_task[0].done():
                _overlap_timer_task[0].cancel()
                _overlap_timer_task[0] = None
                logger.debug("SPEAKING_AND_LISTENING: overlap timer cancelled by SPEECH_END")

            if current_state == ConversationState.SPEAKING_AND_LISTENING:
                import time as _time
                # Measure how long we were in the overlap state (proxy for speech duration)
                entry_time = _overlap_entry_time[0]
                speech_duration_s = (
                    _time.monotonic() - entry_time if entry_time is not None else 999.0
                )
                _overlap_entry_time[0] = None

                if speech_duration_s < _MIN_BARGE_IN_DURATION_S:
                    # Brief activation: almost certainly TTS echo.
                    # Restore SPEAKING state so TTS can continue uninterrupted.
                    logger.info(
                        f"Echo suppressed: speech lasted {speech_duration_s:.2f}s "
                        f"(< {_MIN_BARGE_IN_DURATION_S}s threshold), restoring SPEAKING"
                    )
                    await state_machine.transition_to(
                        ConversationState.SPEAKING,
                        metadata={"trigger": "echo_suppression_restore"}
                    )
                else:
                    # Sustained speech: real user barge-in — execute immediately
                    logger.info(
                        f"Barge-in: speech lasted {speech_duration_s:.2f}s "
                        f"(>= {_MIN_BARGE_IN_DURATION_S}s), executing"
                    )
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
        """Flush TTS buffer and wait for audio to finish before transitioning state.

        Handles barge-in: if the generation was cancelled (barge-in), skip the
        audio drain to avoid interfering with the next request's state.
        """
        logger.info(f"LLM completed: {len(result.text)} chars, {result.tokens_generated} tokens")

        # Update Whisper prompt context with recent LLM output for better STT accuracy
        stt_processor.transcriber.set_prompt_context(result.text)

        # Skip stale completions from cancelled generations (barge-in)
        # The _cancelled flag is True when barge-in interrupted this generation,
        # and hasn't been reset yet by a new generate_stream() call.
        if generator._cancelled:
            logger.info("LLM complete (cancelled generation), skipping audio drain")
            tts_processor.reset_audio_tracking()
            return

        # If barge-in occurred, skip the wait-for-audio sequence
        # The state machine is already in LISTENING or PROCESSING from barge-in
        current = state_machine.state
        if current not in (ConversationState.PROCESSING, ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
            logger.info(f"LLM complete but state is {current.value} (barge-in occurred), skipping audio drain")
            tts_processor.reset_audio_tracking()
            return

        await tts_processor.flush()

        # Wait for TTS synthesis to complete (in case flush triggered synthesis)
        max_wait = 30.0
        elapsed = 0.0
        while tts_processor.is_synthesizing and elapsed < max_wait:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        # Wait for audio buffer to drain.
        # With backpressure in on_tts_audio, audio is pushed at playback rate,
        # so after synthesis completes, only the remaining buffer needs to drain.
        # Use buffer polling (reliable now that backpressure prevents overflow).
        logger.info(f"TTS generated {tts_processor.total_audio_duration_ms:.0f}ms of audio, waiting for playback")

        max_drain_wait = 15.0  # Buffer can hold max 10s, so 15s is generous
        drain_elapsed = 0.0
        while drain_elapsed < max_drain_wait:
            has_audio = False
            for pc in list(connection_manager._connections):
                track = connection_manager.get_track(pc)
                if track is not None and track.has_audio:
                    has_audio = True
                    break
            if not has_audio:
                break
            await asyncio.sleep(0.05)
            drain_elapsed += 0.05
        logger.info("Audio playback wait complete, transitioning to IDLE")

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
                # Backpressure: wait for buffer to drain below 80% capacity
                # before pushing more audio. Without this, long responses
                # overflow the 10s buffer and audio gets dropped/truncated.
                max_wait = 30.0
                waited = 0.0
                while track.buffer_duration_ms > 8000:  # 8s threshold (max is 10s)
                    await asyncio.sleep(0.05)
                    waited += 0.05
                    if waited >= max_wait:
                        logger.warning("Backpressure timeout, pushing anyway")
                        break
                    # Abort if cancelled (barge-in)
                    if state_machine.state not in (ConversationState.PROCESSING, ConversationState.SPEAKING, ConversationState.SPEAKING_AND_LISTENING):
                        logger.debug("Backpressure aborted: state changed")
                        return
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

        # Reset _first_audio_sent when speech ends — but only if we're entering PROCESSING.
        # If echo suppression fired (SPEECH_END during brief SPEAKING_AND_LISTENING),
        # on_vad_for_state already restored state to SPEAKING. In that case we must NOT
        # reset _first_audio_sent, because TTS is still running and the next audio chunk
        # must be accepted without re-triggering the PROCESSING → SPEAKING transition.
        if event.type == VADEventType.SPEECH_END:
            if current_state != ConversationState.SPEAKING:
                _first_audio_sent[0] = False
                logger.debug("Reset _first_audio_sent flag for new response")
            else:
                logger.debug(
                    "Skipping _first_audio_sent reset: echo suppression restored SPEAKING, "
                    "TTS still active"
                )

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

        Wrapped in try/finally to ALWAYS return to IDLE state — even if
        synthesis throws an exception (OOM, model error, etc.).  Without
        this, any exception leaves the state machine stuck in PROCESSING
        forever because the idle-timeout only recovers LISTENING→IDLE.
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

        try:
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

        except Exception as e:
            logger.error(f"plugin_speak_callback: synthesis error: {e}", exc_info=True)
            # Cancel any in-progress synthesis so it doesn't leak resources
            await tts_processor.cancel()
        finally:
            # Always reset TTS state and return state machine to IDLE.
            # This is critical: without it, any exception leaves state=PROCESSING
            # with no automatic recovery (idle timeout only handles LISTENING→IDLE).
            tts_processor.reset_audio_tracking()
            await state_machine.stop()

    # Attach plugins to Ergos components
    plugin_manager.attach_all(
        llm=llm_processor.generator,
        tts=tts_processor,
        state_machine=state_machine,
        speak_callback=plugin_speak_callback,
    )
    logger.debug("Attached plugins to Ergos components")

    # Wire meeting notes plugin with transcriber, vault path, and recording broadcast
    meeting_plugin = plugin_manager.get_plugin("meeting_notes")
    if meeting_plugin is not None:
        meeting_plugin.set_transcriber(stt_processor.transcriber)
        meeting_plugin.set_broadcast_recording(data_handler.broadcast_recording_status)
        if hasattr(config, "meeting_notes"):
            meeting_plugin.set_vault_path(config.meeting_notes.vault_path)

    # Build capabilities list and inject into system prompt
    known_capabilities: list[str] = []
    if prompt_builder is not None:
        # Tools from registry
        if tool_registry is not None and tool_processor is not None and tool_processor.has_tools:
            for tool in tool_registry.get_tools():
                name = tool.get("function", {}).get("name", "")
                desc = tool.get("function", {}).get("description", "")
                if name and desc:
                    known_capabilities.append(f"Tool: {name} — {desc}")

        # Plugins
        for plugin in plugin_manager.plugins.values():
            phrases = ", ".join(f'"{p}"' for p in plugin.activation_phrases[:3])
            known_capabilities.append(
                f'Voice command: say {phrases} to activate {plugin.name}'
            )

        # Built-in voice commands
        known_capabilities.append(
            'Voice command: "set sarcasm to N%" adjusts your humor level'
        )

        if known_capabilities:
            all_mems = memory_store.load()
            budget_mems = memory_store.get_budget(all_mems)
            mem_strs = [m.content for m in budget_mems]
            system_prompt = prompt_builder.build(
                name=persona.name,
                sarcasm_level=current_sarcasm_level[0],
                memories=mem_strs,
                time_context=get_time_context(),
                capabilities=known_capabilities,
            )
            llm_processor.update_system_prompt(system_prompt)
            logger.info(f"Injected {len(known_capabilities)} capabilities into system prompt")

    # Create transcription callback that routes through plugins first
    async def on_transcription_with_plugins(result) -> None:
        """Route transcription to plugins or LLM.

        Checks if any plugin should handle the input. If so, routes
        to the plugin. Otherwise, passes through to LLM processor.
        Sarcasm voice commands are intercepted BEFORE plugins and LLM.
        """
        text = result.text
        logger.info(f"Transcription: {text}")
        await data_handler.broadcast_transcription(text)

        # === Wake word gate (before everything else) ===
        wake_word = config.persona.wake_word
        if wake_word:
            text_lower = text.lower()
            # Sarcasm commands bypass wake word (system commands always work)
            is_sarcasm_cmd = try_sarcasm_command(text) is not None
            if not is_sarcasm_cmd and wake_word.lower() not in text_lower:
                logger.debug(f"Wake word '{wake_word}' not found, ignoring: {text[:50]}")
                await state_machine.stop()  # Return to IDLE — without this, state stays PROCESSING
                return
            # Strip wake word from text so LLM doesn't see it
            if not is_sarcasm_cmd:
                import re as _re
                text = _re.sub(r'(?i)\b' + _re.escape(wake_word) + r'\b[,.]?\s*', '', text).strip()
                if not text:
                    await state_machine.stop()  # Just the wake word, nothing to process
                    return

        # === Ergos sarcasm command intercept (before plugins and LLM) ===
        if prompt_builder is not None:
            new_level = try_sarcasm_command(text)
            if new_level is not None:
                current_sarcasm_level[0] = new_level
                # Rebuild system prompt with new sarcasm level
                all_mems = memory_store.load()
                budget_mems = memory_store.get_budget(all_mems)
                mem_strs = [m.content for m in budget_mems]
                new_prompt = prompt_builder.build(
                    name=persona.name,
                    sarcasm_level=new_level,
                    memories=mem_strs,
                    time_context=get_time_context(),
                    capabilities=known_capabilities,
                )
                llm_processor.update_system_prompt(new_prompt)
                logger.info(f"Sarcasm level updated to {new_level}%")

                # Speak confirmation via TTS without going through LLM
                confirmations = {
                    range(0, 21): f"Sarcasm level set to {new_level}%. All business.",
                    range(21, 50): f"Sarcasm at {new_level}%. I'll try to keep a straight face.",
                    range(50, 80): f"Sarcasm now at {new_level}%. This should be interesting.",
                    range(80, 101): f"Sarcasm cranked to {new_level}%. You asked for it.",
                }
                confirmation = next(
                    msg for rng, msg in confirmations.items() if new_level in rng
                )
                await plugin_speak_callback(confirmation)
                return  # Don't forward to plugins or LLM

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

        # Agentic tool execution (if tools available)
        if tool_processor is not None and tool_processor.has_tools:
            tts_processor.reset_cancellation()
            _first_audio_sent[0] = False

            async def agentic_speak(text: str) -> None:
                """Speak narration phrase during agentic execution."""
                await plugin_speak_callback(text)

            response_text = await tool_processor.process(
                user_text=text,
                speak=agentic_speak,
                llm_processor=llm_processor,
            )

            # Stream the final response through TTS
            if response_text:
                # CRITICAL: Transition state to PROCESSING before streaming TTS.
                # After narration phases, plugin_speak_callback returns state to IDLE.
                # on_tts_audio needs PROCESSING state to transition to SPEAKING on
                # first audio chunk. Without this, client shows IDLE during playback.
                # This mirrors the non-agentic path where PROCESSING is set by
                # on_vad_for_state before LLM generates tokens.
                current_state = state_machine.state
                if current_state == ConversationState.IDLE:
                    await state_machine.start_listening()
                    await state_machine.start_processing()
                elif current_state == ConversationState.LISTENING:
                    await state_machine.start_processing()
                # If already PROCESSING (e.g., no narration was spoken), no transition needed

                tts_processor.reset_cancellation()
                _first_audio_sent[0] = False
                for char in response_text:
                    await tts_processor.receive_token(char)
                await tts_processor.flush()

                # Wait for synthesis + audio drain (same pattern as on_llm_complete)
                max_wait = 30.0
                elapsed = 0.0
                while tts_processor.is_synthesizing and elapsed < max_wait:
                    await asyncio.sleep(0.1)
                    elapsed += 0.1

                # Wait for audio buffer drain
                max_drain = 15.0
                drain_elapsed = 0.0
                while drain_elapsed < max_drain:
                    has_audio = False
                    for pc in list(connection_manager._connections):
                        track = connection_manager.get_track(pc)
                        if track is not None and track.has_audio:
                            has_audio = True
                            break
                    if not has_audio:
                        break
                    await asyncio.sleep(0.2)
                    drain_elapsed += 0.2

                tts_processor.reset_audio_tracking()
                await state_machine.stop()
            return

        # No plugin handled it, pass to LLM
        # Reset TTS cancellation flag before new generation — barge-in sets
        # _cancelled=True but there's no SPEECH_START between barge-in and
        # the new transcription to reset it.
        tts_processor.reset_cancellation()
        _first_audio_sent[0] = False
        await llm_processor.process_transcription(result)

    # Replace the direct LLM callback with plugin-aware routing
    # First remove the direct callback, then add the routing callback
    stt_processor.remove_transcription_callback(llm_processor.process_transcription)
    stt_processor.add_transcription_callback(on_transcription_with_plugins)
    logger.debug("Wired: STT -> Plugin router -> LLM processor")

    # When STT filters out a transcription (low confidence, hallucination, empty),
    # no transcription callback fires, leaving state stuck in PROCESSING.
    # Wire a no-result callback to return to IDLE.
    async def on_stt_no_result() -> None:
        current = state_machine.state
        if current == ConversationState.PROCESSING:
            logger.debug("STT produced no result, returning to IDLE")
            await state_machine.stop()

    stt_processor.add_no_result_callback(on_stt_no_result)
    logger.debug("Wired: STT no-result -> state IDLE")

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

    # Reset pipeline state on new connection (fixes stuck state after reconnect)
    async def on_new_connection() -> None:
        """Reset pipeline state when a new client connects.

        Performs a full reset of all pipeline flags to prevent stale state
        from a previous session bleeding into the new one. Critically,
        this includes _inside_think which causes 0ms TTS if stuck True.
        """
        logger.info("New connection: resetting pipeline state")
        await state_machine.reset()
        tts_processor.reset_state()  # Clears _cancelled, _inside_think, buffer, audio tracking
        _first_audio_sent[0] = False
        # Pre-warm cloud endpoint and notify client of progress
        if hasattr(generator, 'warm_up'):
            async def _warm_up_with_status():
                await data_handler.broadcast_warmup_status("started")
                try:
                    await generator.warm_up()
                    await data_handler.broadcast_warmup_status("ready")
                except Exception:
                    await data_handler.broadcast_warmup_status("failed")
            asyncio.create_task(_warm_up_with_status())

    # Create signaling app with all handlers
    app = create_signaling_app(
        manager=connection_manager,
        data_handler=data_handler,
        on_incoming_audio=on_incoming_audio,
    )
    app["on_connect"] = on_new_connection
    logger.debug("Created signaling app")

    # ========== Memory extraction on disconnect ==========
    # Runs after session ends — uses generator.generate() directly to avoid
    # polluting LLM conversation history (anti-pattern: never use llm_processor here)
    async def _extract_and_save_memories() -> None:
        """Extract memories from conversation history and save to disk."""
        if llm_processor is None or not persona.is_ergos_persona:
            return

        history_text = format_history_for_extraction(llm_processor.history)
        if history_text is None:
            logger.info("Memory extraction skipped: too few messages in history")
            return

        logger.info("Extracting session memories...")
        loop = asyncio.get_event_loop()
        try:
            prompt = EXTRACTION_PROMPT.format(history=history_text)
            # Wrap generator.generate() in executor — it is synchronous and must not
            # block the event loop. Never use llm_processor here (pollutes history).
            from ergos.llm.types import GenerationConfig as _GenConfig
            result = await loop.run_in_executor(
                None,
                lambda: generator.generate(prompt, config=_GenConfig(max_tokens=300)),
            )
            new_entries = parse_extraction_result(result.text)
            if new_entries:
                existing = memory_store.load()
                existing.extend(new_entries)
                existing = memory_store.prune(existing)
                memory_store.save(existing)
                logger.info(f"Saved {len(new_entries)} new memories ({len(existing)} total)")
            else:
                logger.info("No memorable moments extracted from this session")
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            # Never lose existing memories on extraction failure (Pitfall 2)

    # Register memory extraction to run on peer disconnect
    connection_manager.set_disconnect_callback(_extract_and_save_memories)
    logger.debug("Wired: peer disconnect -> memory extraction")

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
