# Requirements: Ergos

**Defined:** 2026-01-26
**Core Value:** Complete privacy through local-only processing

## v1 Requirements (Complete)

All v1 requirements shipped in phases 1-12. See v1 traceability below.

### Audio Infrastructure (Server)
- [x] **AUDIO-01**: Server receives audio stream from client
- [x] **AUDIO-02**: Server sends audio stream to client
- [x] **AUDIO-03**: Server processes VAD events from client

### Speech-to-Text (Server)
- [x] **STT-01**: Server transcribes speech to text using faster-whisper
- [x] **STT-02**: Server streams partial transcriptions as speech is recognized
- [x] **STT-03**: Server uses VAD boundaries for transcription segments

### LLM (Server)
- [x] **LLM-01**: Server generates responses using Phi-3 Mini (3.8B) via llama-cpp-python
- [x] **LLM-02**: Server streams tokens to TTS as they are generated
- [x] **LLM-03**: Server manages context/memory within <8GB RAM target

### Text-to-Speech (Server)
- [x] **TTS-01**: Server synthesizes speech using Kokoro ONNX
- [x] **TTS-02**: Server streams audio output as synthesis progresses
- [x] **TTS-03**: Server chunks responses at sentence boundaries

### State Machine (Server)
- [x] **STATE-01**: Server implements IDLE → LISTENING → PROCESSING → SPEAKING state machine
- [x] **STATE-02**: Server broadcasts state changes to client
- [x] **STATE-03**: Server handles barge-in (stops TTS, clears buffers)

### Transport (Server)
- [x] **TRANSPORT-01**: Server runs WebRTC signaling endpoint
- [x] **TRANSPORT-02**: Server uses data channel for VAD/state messages
- [x] **TRANSPORT-03**: Server uses Opus codec for audio

### CLI / Configuration (Server)
- [x] **CLI-01**: User can start server via CLI
- [x] **CLI-02**: User can stop server via CLI
- [x] **CLI-03**: User can check server status via CLI
- [x] **CONFIG-01**: Server loads configuration from YAML
- [x] **CONFIG-02**: Server auto-detects hardware (GPU)
- [x] **PERSONA-01**: Server loads persona from YAML
- [x] **PERSONA-02**: Server generates behavior based on persona

### Flutter Client - Audio
- [x] **CLIENT-AUDIO-01**: App captures audio from phone microphone
- [x] **CLIENT-AUDIO-02**: App plays audio through phone speaker
- [x] **CLIENT-AUDIO-03**: App performs client-side VAD
- [x] **CLIENT-AUDIO-04**: App establishes WebRTC connection to server

### Flutter Client - UI
- [x] **CLIENT-UI-01**: App displays animated 3D ball that pulses when speaking
- [x] **CLIENT-UI-02**: App ball visual changes to reflect state
- [x] **CLIENT-UI-03**: App supports barge-in gesture/control to interrupt AI

### Flutter Client - Platform
- [x] **CLIENT-PLATFORM-01**: App runs on Android
- [x] **CLIENT-PLATFORM-02**: App runs on iOS

## v2.0 Requirements

Requirements for TARS milestone. Each maps to roadmap phases (13+).

### Voice Experience

- [x] **VOICE-01**: User experiences zero awkward silence — sub-300ms from speech end to first AI audio
- [x] **VOICE-02**: User can talk while AI is speaking (full-duplex, SPEAKING_AND_LISTENING state)
- [x] **VOICE-03**: User can interrupt mid-sentence and AI stops within 200ms
- [x] **VOICE-04**: AI voice has natural prosody with emotion, pauses, and timed delivery for sarcasm

### Personality

- [x] **PERS-01**: AI has TARS-like dry wit with configurable sarcasm level (0-100%)
- [x] **PERS-02**: AI makes context-aware jokes referencing current activity and past conversations
- [x] **PERS-03**: AI remembers conversation history, user preferences, and running jokes across sessions

### Model Upgrade

- [x] **MODEL-01**: LLM upgraded from Phi-3 Mini to Qwen3-8B (or Qwen3.5-9B) with native tool-calling
- [x] **MODEL-02**: STT upgraded from Whisper tiny.en to small.en INT8 for better accuracy
- [x] **MODEL-03**: All models load concurrently and fit within 16GB VRAM budget

### Agentic Execution

- [x] **AGENT-01**: AI can call tools (file operations, shell commands, web search) via LLM function calling
- [x] **AGENT-02**: AI narrates what it's doing during tool execution ("Let me check that...")
- [x] **AGENT-03**: AI can chain multiple tools to complete multi-step workflows
- [x] **AGENT-04**: Tool registry allows adding new tools without code changes

### Vision

- [ ] **VIS-01**: User can ask "what's on my screen" and AI describes/analyzes the current screen
- [ ] **VIS-02**: AI can read and summarize documents, PDFs, and images
- [ ] **VIS-03**: AI can interact with UI elements — click buttons, fill forms, navigate apps

### Architecture

- [x] **ARCH-01**: VRAM orchestration manages concurrent model loading within 16GB budget
- [ ] **ARCH-02**: Optional cloud LLM fallback with explicit user consent per-query

### Claude Orchestrator

- [ ] **ORCH-01**: TARS classifies user requests as LOCAL (handle with Qwen3) or DELEGATE (send to Claude)
- [ ] **ORCH-02**: Complex tasks delegated to Claude Agent SDK with streaming output relayed through TTS
- [ ] **ORCH-03**: Long-running Claude tasks run in background with progress announcements and barge-in cancellation
- [ ] **ORCH-04**: Claude sessions persist across voice interactions for multi-turn delegation ("continue that analysis")

### Context-Aware Conversation

- [ ] **CTX-01**: TARS tracks conversational threads during brainstorming sessions (idea accumulation, referencing by number)
- [ ] **CTX-02**: Context window managed intelligently — older exchanges compressed/summarized while preserving key points

## v3 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Wake Word
- **WAKE-01**: User can activate assistant with a wake word without touching a button

### Multi-language
- **LANG-01**: User can converse in languages other than English

### Smart Home
- **HOME-01**: User can control smart home devices via voice commands

### Client
- **CLIENT-PLATFORM-03**: Web (Flutter web) support
- **CLIENT-UI-04**: Settings screen

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user support | Single user focus, personal assistant |
| Cloud-only mode | Contradicts core value of local-only privacy |
| Custom voice cloning | Complexity, defer to v3+ |
| Real-time translation | English only for v2 |
| Mobile-first redesign | Desktop/laptop primary for v2 (vision, screen control) |

## Development Notes

- **Mobile development:** Use mobile-mcp server for Flutter client development assistance
- **v2 research:** See `memory/v2-research.md` for model choices, architecture, framework analysis

## Traceability

### v1 (Phases 1-12) — Complete

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLI-01 | Phase 1 | Complete |
| CLI-02 | Phase 1 | Complete |
| CLI-03 | Phase 1 | Complete |
| CONFIG-01 | Phase 1 | Complete |
| CONFIG-02 | Phase 1 | Complete |
| AUDIO-01 | Phase 2 | Complete |
| AUDIO-02 | Phase 2 | Complete |
| AUDIO-03 | Phase 2 | Complete |
| STT-01 | Phase 3 | Complete |
| STT-02 | Phase 3 | Complete |
| STT-03 | Phase 3 | Complete |
| STATE-01 | Phase 4 | Complete |
| STATE-02 | Phase 4 | Complete |
| STATE-03 | Phase 4 | Complete |
| LLM-01 | Phase 5 | Complete |
| LLM-02 | Phase 5 | Complete |
| LLM-03 | Phase 5 | Complete |
| TTS-01 | Phase 6 | Complete |
| TTS-02 | Phase 6 | Complete |
| TTS-03 | Phase 6 | Complete |
| PERSONA-01 | Phase 7 | Complete |
| PERSONA-02 | Phase 7 | Complete |
| TRANSPORT-01 | Phase 8 | Complete |
| TRANSPORT-02 | Phase 8 | Complete |
| TRANSPORT-03 | Phase 8 | Complete |
| CLIENT-AUDIO-01 | Phase 9 | Complete |
| CLIENT-AUDIO-02 | Phase 9 | Complete |
| CLIENT-AUDIO-03 | Phase 9 | Complete |
| CLIENT-AUDIO-04 | Phase 9 | Complete |
| CLIENT-UI-01 | Phase 10 | Complete |
| CLIENT-UI-02 | Phase 10 | Complete |
| CLIENT-UI-03 | Phase 10 | Complete |
| CLIENT-PLATFORM-01 | Phase 11 | Complete |
| CLIENT-PLATFORM-02 | Phase 11 | Complete |

### v2.0 (Phases 13-19) — Pending

| Requirement | Phase | Status |
|-------------|-------|--------|
| MODEL-01 | Phase 13 | Complete |
| MODEL-02 | Phase 13 | Complete |
| MODEL-03 | Phase 13 | Complete |
| ARCH-01 | Phase 13 | Complete |
| VOICE-01 | Phase 14 | Complete |
| VOICE-02 | Phase 14 | Complete |
| VOICE-03 | Phase 14 | Complete |
| VOICE-04 | Phase 15 | Complete |
| PERS-01 | Phase 16 | Complete |
| PERS-02 | Phase 16 | Complete |
| PERS-03 | Phase 16 | Complete |
| AGENT-01 | Phase 17 | Complete |
| AGENT-02 | Phase 17 | Complete |
| AGENT-03 | Phase 17 | Complete |
| AGENT-04 | Phase 17 | Complete |
| VIS-01 | Phase 18 | Pending |
| VIS-02 | Phase 18 | Pending |
| VIS-03 | Phase 18 | Pending |
| ARCH-02 | Phase 19 | Pending |
| ORCH-01 | Phase 20 | Pending |
| ORCH-02 | Phase 20 | Pending |
| ORCH-03 | Phase 20 | Pending |
| ORCH-04 | Phase 20 | Pending |
| CTX-01 | Phase 21 | Pending |
| CTX-02 | Phase 21 | Pending |

**Coverage:**
- v1 requirements: 34 total — 34 mapped ✓
- v2.0 requirements: 25 total — 25 mapped ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-26*
*Last updated: 2026-03-03 — v2.0 phase mappings added (phases 13-19)*
