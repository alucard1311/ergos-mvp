# Requirements: Ergos

**Defined:** 2026-01-26
**Core Value:** Complete privacy through local-only processing

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Audio Infrastructure (Server)

- [ ] **AUDIO-01**: Server receives audio stream from client
- [ ] **AUDIO-02**: Server sends audio stream to client
- [ ] **AUDIO-03**: Server processes VAD events from client

### Speech-to-Text (Server)

- [ ] **STT-01**: Server transcribes speech to text using faster-whisper
- [ ] **STT-02**: Server streams partial transcriptions as speech is recognized
- [ ] **STT-03**: Server uses VAD boundaries for transcription segments

### LLM (Server)

- [ ] **LLM-01**: Server generates responses using Phi-3 Mini (3.8B) via llama-cpp-python
- [ ] **LLM-02**: Server streams tokens to TTS as they are generated
- [ ] **LLM-03**: Server manages context/memory within <8GB RAM target

### Text-to-Speech (Server)

- [ ] **TTS-01**: Server synthesizes speech using Kokoro ONNX
- [ ] **TTS-02**: Server streams audio output as synthesis progresses
- [ ] **TTS-03**: Server chunks responses at sentence boundaries

### State Machine (Server)

- [ ] **STATE-01**: Server implements IDLE → LISTENING → PROCESSING → SPEAKING state machine
- [ ] **STATE-02**: Server broadcasts state changes to client
- [ ] **STATE-03**: Server handles barge-in (stops TTS, clears buffers)

### Transport (Server)

- [ ] **TRANSPORT-01**: Server runs WebRTC signaling endpoint
- [ ] **TRANSPORT-02**: Server uses data channel for VAD/state messages
- [ ] **TRANSPORT-03**: Server uses Opus codec for audio

### CLI / Configuration (Server)

- [ ] **CLI-01**: User can start server via CLI
- [ ] **CLI-02**: User can stop server via CLI
- [ ] **CLI-03**: User can check server status via CLI
- [ ] **CONFIG-01**: Server loads configuration from YAML
- [ ] **CONFIG-02**: Server auto-detects hardware (GPU)
- [ ] **PERSONA-01**: Server loads persona from YAML
- [ ] **PERSONA-02**: Server generates behavior based on persona

### Flutter Client - Audio

- [ ] **CLIENT-AUDIO-01**: App captures audio from phone microphone
- [ ] **CLIENT-AUDIO-02**: App plays audio through phone speaker
- [ ] **CLIENT-AUDIO-03**: App performs client-side VAD
- [ ] **CLIENT-AUDIO-04**: App establishes WebRTC connection to server

### Flutter Client - UI

- [ ] **CLIENT-UI-01**: App displays animated 3D ball that pulses when speaking
- [ ] **CLIENT-UI-02**: App ball visual changes to reflect state (IDLE/LISTENING/PROCESSING/SPEAKING)
- [ ] **CLIENT-UI-03**: App supports barge-in gesture/control to interrupt AI

### Flutter Client - Platform

- [ ] **CLIENT-PLATFORM-01**: App runs on Android
- [ ] **CLIENT-PLATFORM-02**: App runs on iOS

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Audio

- **AUDIO-04**: Echo cancellation

### Features

- **WAKE-01**: Wake word activation
- **MULTI-LANG-01**: Multi-language support
- **HOME-01**: Smart home integration
- **CLIENT-PLATFORM-03**: Web (Flutter web) support
- **CLIENT-UI-04**: Settings screen

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Wake word detection | Adds complexity, v2 feature |
| Multi-user support | Single user focus for v1 |
| Smart home integrations | Separate project concern |
| Multi-language | English only for v1 |
| Cloud/hybrid mode | Contradicts core value |

## Development Notes

- **Mobile development:** Use mobile-mcp server (https://github.com/mobile-next/mobile-mcp) for Flutter client development assistance

## Traceability

Which phases cover which requirements. Updated by create-roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLI-01 | Phase 1 | Pending |
| CLI-02 | Phase 1 | Pending |
| CLI-03 | Phase 1 | Pending |
| CONFIG-01 | Phase 1 | Pending |
| CONFIG-02 | Phase 1 | Pending |
| AUDIO-01 | Phase 2 | Pending |
| AUDIO-02 | Phase 2 | Pending |
| AUDIO-03 | Phase 2 | Pending |
| STT-01 | Phase 3 | Pending |
| STT-02 | Phase 3 | Pending |
| STT-03 | Phase 3 | Pending |
| STATE-01 | Phase 4 | Pending |
| STATE-02 | Phase 4 | Pending |
| STATE-03 | Phase 4 | Pending |
| LLM-01 | Phase 5 | Pending |
| LLM-02 | Phase 5 | Pending |
| LLM-03 | Phase 5 | Pending |
| TTS-01 | Phase 6 | Pending |
| TTS-02 | Phase 6 | Pending |
| TTS-03 | Phase 6 | Pending |
| PERSONA-01 | Phase 7 | Pending |
| PERSONA-02 | Phase 7 | Pending |
| TRANSPORT-01 | Phase 8 | Pending |
| TRANSPORT-02 | Phase 8 | Pending |
| TRANSPORT-03 | Phase 8 | Pending |
| CLIENT-AUDIO-01 | Phase 9 | Pending |
| CLIENT-AUDIO-02 | Phase 9 | Pending |
| CLIENT-AUDIO-03 | Phase 9 | Pending |
| CLIENT-AUDIO-04 | Phase 9 | Pending |
| CLIENT-UI-01 | Phase 10 | Pending |
| CLIENT-UI-02 | Phase 10 | Pending |
| CLIENT-UI-03 | Phase 10 | Pending |
| CLIENT-PLATFORM-01 | Phase 11 | Pending |
| CLIENT-PLATFORM-02 | Phase 11 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-26*
*Last updated: 2026-01-26 after roadmap creation*
