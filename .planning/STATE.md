# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-26)

**Core value:** Complete privacy through local-only processing
**Current focus:** Phase 4 — State Machine (Complete)

## Current Position

Phase: 4 of 12 (State Machine) — Complete
Plan: 2/2 complete
Status: Ready for Phase 5
Last activity: 2026-01-26 — Completed 04-02-PLAN.md

Progress: ██████████ 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: 3.0 min
- Total execution time: 24 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1-foundation | 2 | 11 min | 5.5 min |
| 2-audio-infrastructure | 2 | 5 min | 2.5 min |
| 3-stt-pipeline | 2 | 4 min | 2 min |
| 4-state-machine | 2 | 4 min | 2 min |

**Recent Trend:**
- Last 5 plans: 03-01 (2 min), 03-02 (2 min), 04-01 (2 min), 04-02 (2 min)
- Trend: Stable at ~2 min per plan

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

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-01-26T20:17:00Z
Stopped at: Completed 04-02-PLAN.md — Barge-in and broadcast support added
Resume file: None
