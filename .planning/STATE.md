# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-26)

**Core value:** Complete privacy through local-only processing
**Current focus:** Phase 12 — Integration Latency

## Current Position

Phase: 12 of 12 (Integration Latency)
Plan: 2 of 2 in current phase
Status: Plan 12-02 complete
Last activity: 2026-01-26 — Latency instrumentation added

Progress: ██████████████████████████ 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 25
- Average duration: 2.4 min
- Total execution time: 62 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1-foundation | 2 | 11 min | 5.5 min |
| 2-audio-infrastructure | 2 | 5 min | 2.5 min |
| 3-stt-pipeline | 2 | 4 min | 2 min |
| 4-state-machine | 2 | 4 min | 2 min |
| 5-llm-integration | 2 | 4 min | 2 min |
| 6-tts-pipeline | 2 | 5 min | 2.5 min |
| 7-persona-system | 1 | 1 min | 1 min |
| 8-webrtc-transport | 4 | 6 min | 1.5 min |
| 9-flutter-client-core | 3 | 8 min | 2.7 min |
| 10-flutter-client-ui | 2 | 6 min | 3 min |
| 11-flutter-client-platform | 1 | 2 min | 2 min |
| 12-integration-latency | 2 | 6 min | 3 min |

**Recent Trend:**
- Last 5 plans: 10-01 (3 min), 10-02 (3 min), 11-01 (2 min), 12-01 (3 min), 12-02 (3 min)
- Trend: Integration phase completes final wiring and latency instrumentation

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- LLM choice: Phi-3 Mini (3.8B) via llama-cpp-python (user specified)
- Client architecture: Flutter mobile app (Android/iOS) connecting to Python server
- UI: Animated 3D ball with state-based visuals (user specified)
- Development tooling: mobile-mcp server for Flutter development assistance
- Package layout: src/ layout for Python package (01-01)
- Config validation: Pydantic v2 with YAML loading (01-01)
- PID file at ~/.ergos/server.pid for server tracking (01-02)
- asyncio.Event for shutdown coordination (01-02)
- Signal handlers for SIGINT and SIGTERM (01-02)
- Audio format: 16kHz, mono, 16-bit, 30ms chunks (02-01)
- asyncio.Queue for thread-safe audio buffering (02-01)
- VAD runs on client, server receives events via data channel (02-02)
- Async callbacks for non-blocking VAD/audio notification (02-02)
- PipelineState enum matching state machine phases (02-02)
- Lazy model loading for deferred Whisper initialization (03-01)
- Word timestamps enabled for fine-grained transcription segments (03-01)
- Audio normalized to float32 [-1, 1] for faster-whisper (03-01)
- Speech-bounded transcription via VAD events (03-02)
- Thread pool executor for transcription to not block event loop (03-02)
- 100ms minimum audio threshold for transcription (03-02)
- ConversationState separate from PipelineState (state machine is source of truth) (04-01)
- asyncio.Lock for thread-safe state transitions (04-01)
- Barge-in callbacks invoked before transition to allow buffer clearing (04-02)
- StateChangeEvent.to_dict() for WebRTC data channel broadcast (04-02)
- llama-cpp-python with Llama() for Phi-3 Mini GGUF models (05-01)
- Lazy model loading for LLMGenerator (05-01)
- n_ctx=2048 context window, n_gpu_layers=-1 for GPU offload (05-01)
- Phi-3 chat format: <|system|>, <|user|>, <|assistant|> with <|end|> (05-02)
- Conversation history bounded to 10 messages for memory management (05-02)
- Token callbacks for streaming to TTS (05-02)
- kokoro-onnx for TTS with natively async create_stream() (06-01)
- Lazy model loading for TTSSynthesizer (06-01)
- Sample rate fixed at 24000 Hz (Kokoro output) (06-01)
- AudioCallback type for streaming audio chunks (06-01)
- Sentence boundaries detected by .!? followed by space or end of buffer (06-02)
- receive_token() designed as LLMProcessor token callback (06-02)
- Buffer cleared synchronously for immediate barge-in response (06-02)
- flush() called after LLM generation to synthesize remaining text (06-02)
- Persona uses dataclass with system_prompt property for dynamic prompt generation (07-01)
- load_persona() returns DEFAULT_PERSONA on file not found or parse error (07-01)
- PersonaConfig.persona_file supports both file-based and inline persona definition (07-01)
- 24kHz sample rate for TTSAudioTrack to match Kokoro output (08-01)
- 20ms frame duration (AUDIO_PTIME=0.020) for aiortc standard pacing (08-01)
- Non-blocking recv() returns silence when no audio available (08-01)
- ConnectionManager tracks connections in set for auto-cleanup (08-02)
- Async cleanup on connectionstatechange for failed/closed states (08-02)
- aiohttp /offer endpoint returns SDP answer synchronously (08-02)
- Data channel message routing by type field: vad_event, barge_in (08-03)
- get_state_callback() for state machine registration pattern (08-03)
- Track added BEFORE createAnswer() per RESEARCH.md pitfall #6 (08-04)
- Track registry on ConnectionManager for retrieving TTSAudioTrack (08-04)
- on_incoming_audio callback for routing client audio to STT pipeline (08-04)
- flutter_webrtc ^0.12.5 for WebRTC (SDK compatibility) (09-01)
- vad ^0.0.6 for Silero VAD v5 (Dart SDK version requirement) (09-01)
- minSdkVersion 23 for Android (flutter_webrtc requirement) (09-01)
- Data channel created BEFORE createOffer (RESEARCH.md pitfall #1) (09-02)
- Permission handling for microphone with permanentlyDenied → openAppSettings() (09-02)
- frameSamples: 512 for Silero VAD v5 (32ms frames at 16kHz) (09-03)
- VAD events flow: speech → VADService → WebRTCService.sendDataChannelMessage() (09-03)
- Pseudo-3D sphere via RadialGradient with Alignment(-0.3, -0.4) light source (10-01)
- AnimatedContainer for smooth color transitions (300ms) without custom ColorTween (10-01)
- HitTestBehavior.opaque for tap detection on transparent orb areas (10-01)
- Dark theme with 0xFF1A1A2E background for better orb visibility (10-02)
- Barge-in timestamp as millisecondsSinceEpoch / 1000 for float format (10-02)
- "Tap to interrupt" hint only shown during SPEAKING state (10-02)
- LatencyMetrics keeps rolling window of 100 samples for percentile calculation (12-02)
- Latency measured from VAD SPEECH_END to first TTS audio chunk (12-02)
- Latency logged as: current, P50, P95, mean with sample count (12-02)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-01-26
Stopped at: Phase 12 complete — All phases complete
Resume file: None
