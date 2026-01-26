# Roadmap: Ergos

## Overview

Ergos is a local-first voice assistant with a Python server (STT, LLM, TTS pipeline) and Flutter mobile client. The roadmap progresses from foundation through server components, then client development, ending with integration and latency optimization. All AI processing runs locally for complete privacy.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Foundation** - Project scaffolding, CLI, configuration system
- [ ] **Phase 2: Audio Infrastructure** - Server audio receive/send, VAD processing
- [ ] **Phase 3: STT Pipeline** - Speech-to-text with streaming transcription
- [ ] **Phase 4: State Machine** - Conversation flow orchestration with barge-in
- [ ] **Phase 5: LLM Integration** - Phi-3 Mini with streaming tokens
- [ ] **Phase 6: TTS Pipeline** - Kokoro ONNX with streaming audio
- [ ] **Phase 7: Persona System** - YAML-configured personality
- [ ] **Phase 8: WebRTC Transport** - Real-time bidirectional audio
- [ ] **Phase 9: Flutter Client Core** - Audio capture, playback, VAD, WebRTC
- [ ] **Phase 10: Flutter Client UI** - Animated 3D ball with state visualization
- [ ] **Phase 11: Flutter Client Platform** - Android and iOS builds
- [ ] **Phase 12: Integration & Latency** - End-to-end testing, performance optimization

## Phase Details

### Phase 1: Foundation
**Goal**: Project scaffolding with working CLI and configuration system
**Depends on**: Nothing (first phase)
**Requirements**: CLI-01, CLI-02, CLI-03, CONFIG-01, CONFIG-02
**Success Criteria** (what must be TRUE):
  1. `ergos start` command launches the server
  2. `ergos stop` command stops the server
  3. `ergos status` shows server state
  4. Configuration loads from YAML file
  5. Hardware (GPU) is auto-detected and logged
**Research**: Unlikely (standard Python project setup)
**Plans**: TBD

### Phase 2: Audio Infrastructure
**Goal**: Server can receive and send audio streams with VAD processing
**Depends on**: Phase 1
**Requirements**: AUDIO-01, AUDIO-02, AUDIO-03
**Success Criteria** (what must be TRUE):
  1. Server can receive audio bytes from a connection
  2. Server can send audio bytes to a connection
  3. VAD events are processed and logged
**Research**: Unlikely (sounddevice, silero-vad established)
**Plans**: TBD

### Phase 3: STT Pipeline
**Goal**: Convert speech to text with streaming partial transcriptions
**Depends on**: Phase 2
**Requirements**: STT-01, STT-02, STT-03
**Success Criteria** (what must be TRUE):
  1. Speech audio produces text transcription
  2. Partial transcriptions appear while speaking
  3. Transcription uses VAD boundaries (not fixed chunks)
**Research**: Unlikely (faster-whisper API well-documented)
**Plans**: TBD

### Phase 4: State Machine
**Goal**: Conversation flow orchestration with barge-in support
**Depends on**: Phase 2
**Requirements**: STATE-01, STATE-02, STATE-03
**Success Criteria** (what must be TRUE):
  1. System transitions through IDLE → LISTENING → PROCESSING → SPEAKING
  2. State changes are broadcast to connected clients
  3. Barge-in during SPEAKING returns to LISTENING
**Research**: Unlikely (standard FSM pattern)
**Plans**: TBD

### Phase 5: LLM Integration
**Goal**: Generate streaming responses using Phi-3 Mini (3.8B)
**Depends on**: Phase 3, Phase 4
**Requirements**: LLM-01, LLM-02, LLM-03
**Success Criteria** (what must be TRUE):
  1. Text input produces conversational response
  2. Response tokens stream to output
  3. Memory stays within 8GB target
**Research**: Unlikely (llama-cpp-python documented)
**Plans**: TBD

### Phase 6: TTS Pipeline
**Goal**: Synthesize streaming speech output using Kokoro ONNX
**Depends on**: Phase 5
**Requirements**: TTS-01, TTS-02, TTS-03
**Success Criteria** (what must be TRUE):
  1. Text produces synthesized audio
  2. Audio streams as synthesis progresses
  3. Long responses pause at sentence boundaries
**Research**: Likely (Kokoro ONNX streaming needs investigation)
**Research topics**: Kokoro ONNX API, streaming audio output patterns, sentence boundary detection
**Plans**: TBD

### Phase 7: Persona System
**Goal**: YAML-configured personality affecting response behavior
**Depends on**: Phase 5
**Requirements**: PERSONA-01, PERSONA-02
**Success Criteria** (what must be TRUE):
  1. Persona loads from YAML file
  2. Persona affects response style/behavior
**Research**: Unlikely (YAML parsing, system prompts)
**Plans**: TBD

### Phase 8: WebRTC Transport
**Goal**: Real-time bidirectional audio transport with data channel
**Depends on**: Phase 2, Phase 4, Phase 6
**Requirements**: TRANSPORT-01, TRANSPORT-02, TRANSPORT-03
**Success Criteria** (what must be TRUE):
  1. Client can establish WebRTC connection to server
  2. Audio flows bidirectionally over connection
  3. Data channel carries VAD/state messages
**Research**: Likely (aiortc specifics for audio streaming)
**Research topics**: aiortc audio track handling, Opus codec integration, data channel protocol design
**Plans**: TBD

### Phase 9: Flutter Client Core
**Goal**: Mobile app with audio capture, playback, VAD, and WebRTC
**Depends on**: Phase 8
**Requirements**: CLIENT-AUDIO-01, CLIENT-AUDIO-02, CLIENT-AUDIO-03, CLIENT-AUDIO-04
**Success Criteria** (what must be TRUE):
  1. App captures audio from phone microphone
  2. App plays audio through phone speaker
  3. App detects speech locally (VAD)
  4. App connects to server via WebRTC
**Research**: Likely (Flutter audio and WebRTC packages)
**Research topics**: Flutter audio plugins (record, just_audio), flutter_webrtc, client-side VAD options (silero-vad ONNX)
**Plans**: TBD

### Phase 10: Flutter Client UI
**Goal**: Animated 3D ball UI with state visualization and barge-in
**Depends on**: Phase 9
**Requirements**: CLIENT-UI-01, CLIENT-UI-02, CLIENT-UI-03
**Success Criteria** (what must be TRUE):
  1. App displays animated 3D ball
  2. Ball pulses when user/AI is speaking
  3. Ball visual reflects current state (IDLE/LISTENING/PROCESSING/SPEAKING)
  4. Barge-in gesture interrupts AI
**Research**: Likely (3D animations in Flutter)
**Research topics**: Flutter 3D rendering options (flutter_gl, custom painter), animation libraries, gesture handling
**Plans**: TBD

### Phase 11: Flutter Client Platform
**Goal**: Working Android and iOS builds
**Depends on**: Phase 10
**Requirements**: CLIENT-PLATFORM-01, CLIENT-PLATFORM-02
**Success Criteria** (what must be TRUE):
  1. App builds and runs on Android device
  2. App builds and runs on iOS device
**Research**: Unlikely (standard Flutter platform builds)
**Plans**: TBD

### Phase 12: Integration & Latency
**Goal**: End-to-end pipeline working with sub-second latency
**Depends on**: Phase 11
**Requirements**: (validates all prior requirements)
**Success Criteria** (what must be TRUE):
  1. Full voice-to-voice loop works end-to-end
  2. P50 latency < 500ms (measured)
  3. P95 latency < 800ms (measured)
**Research**: Unlikely (performance tuning, no new tech)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete | 2026-01-26 |
| 2. Audio Infrastructure | 0/TBD | Not started | - |
| 3. STT Pipeline | 0/TBD | Not started | - |
| 4. State Machine | 0/TBD | Not started | - |
| 5. LLM Integration | 0/TBD | Not started | - |
| 6. TTS Pipeline | 0/TBD | Not started | - |
| 7. Persona System | 0/TBD | Not started | - |
| 8. WebRTC Transport | 0/TBD | Not started | - |
| 9. Flutter Client Core | 0/TBD | Not started | - |
| 10. Flutter Client UI | 0/TBD | Not started | - |
| 11. Flutter Client Platform | 0/TBD | Not started | - |
| 12. Integration & Latency | 0/TBD | Not started | - |

---
*Roadmap created: 2026-01-26*
