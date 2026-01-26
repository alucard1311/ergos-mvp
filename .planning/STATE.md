# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-26)

**Core value:** Complete privacy through local-only processing
**Current focus:** Phase 7 — Pipeline Integration (Next)

## Current Position

Phase: 6 of 12 (TTS Pipeline) — Complete
Plan: 2/2 complete
Status: Ready for Phase 7
Last activity: 2026-01-26 — Completed 06-02-PLAN.md

Progress: ██████████ 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 12
- Average duration: 2.7 min
- Total execution time: 33 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1-foundation | 2 | 11 min | 5.5 min |
| 2-audio-infrastructure | 2 | 5 min | 2.5 min |
| 3-stt-pipeline | 2 | 4 min | 2 min |
| 4-state-machine | 2 | 4 min | 2 min |
| 5-llm-integration | 2 | 4 min | 2 min |
| 6-tts-pipeline | 2 | 5 min | 2.5 min |

**Recent Trend:**
- Last 5 plans: 05-01 (2 min), 05-02 (2 min), 06-01 (3 min), 06-02 (2 min)
- Trend: Stable at ~2-3 min per plan

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

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-01-26T22:12:00Z
Stopped at: Completed 06-02-PLAN.md — TTS processor with sentence chunking
Resume file: None
