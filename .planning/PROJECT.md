# Ergos

## What This Is

Ergos is a local-first voice assistant that runs entirely on your hardware. No cloud services, no subscriptions, no data leaving your machine. It provides sub-second voice interactions with natural conversation flow including barge-in support, all while keeping complete privacy.

## Core Value

**Complete privacy through local-only processing.** Everything runs on your hardware - STT, LLM, TTS - with zero network calls for core functionality.

## Requirements

### Validated

(None yet - ship to validate)

### Active

- [ ] CLI interface with start, setup, persona, and status commands
- [ ] Configuration system with hardware auto-detection
- [ ] State machine managing IDLE → LISTENING → PROCESSING → SPEAKING flow
- [ ] Barge-in support (interrupt AI mid-sentence)
- [ ] WebRTC signaling server for audio transport
- [ ] Data channel protocol for VAD events
- [ ] STT integration (faster-whisper)
- [ ] LLM integration (llama-cpp-python)
- [ ] TTS integration (Kokoro via ONNX)
- [ ] Persona system with YAML configuration
- [ ] Sub-second voice-to-voice latency
- [ ] Streaming TTS (start speaking before full response)

### Out of Scope

- Wake word detection - adds complexity, v2 feature
- Multi-user support - single user focus for v1
- Smart home integrations - separate project concern
- Mobile apps - desktop first
- Multi-language - English only for v1
- Cloud/hybrid mode - contradicts core value

## Context

**Technical Environment:**
- Python 3.11+ codebase
- FastAPI for HTTP/WebSocket server
- aiortc for WebRTC peer connections
- Local AI models: Whisper (STT), llama.cpp (LLM), Kokoro (TTS)

**Architecture:**
- Client performs VAD, sends audio via WebRTC
- Server receives audio, runs STT → LLM → TTS pipeline
- State machine coordinates conversation flow
- Data channel carries control messages (VAD events, state changes)

**Existing Code:**
- Project structure exists with empty placeholder files
- No implementation yet - greenfield build

**Reference Documents:**
- `.planning/PRD.md` - Product requirements
- `.planning/TRD.md` - Technical specifications

## Constraints

- **Tech Stack**: Python 3.11+, FastAPI, aiortc, faster-whisper, llama-cpp-python, ONNX - chosen for local inference capabilities
- **Performance**: < 1 second voice-to-voice latency - required for natural conversation
- **Memory**: < 8GB RAM for full pipeline - accessibility on consumer hardware
- **Privacy**: No network calls for core functionality - non-negotiable core value
- **License**: MIT - open source commitment

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| WebRTC for audio transport | Low latency, handles NAT, industry standard | - Pending |
| Client-side VAD | Reduces server load, enables instant barge-in | - Pending |
| Streaming TTS | Start speaking before full response ready | - Pending |
| YAML personas | Human-readable, easy to customize | - Pending |
| Pydantic for validation | Type safety, good FastAPI integration | - Pending |

---
*Last updated: 2026-01-26 after initialization*
