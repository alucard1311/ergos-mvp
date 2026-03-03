# Roadmap: Ergos

## Milestones

- ✅ **v1.0 Baseline** - Phases 1-12 (shipped 2026-01-26)
- 🚧 **v2.0 TARS** - Phases 13-19 (in progress)

## Phases

<details>
<summary>✅ v1.0 Baseline (Phases 1-12) - SHIPPED 2026-01-26</summary>

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

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
**Plans**: 2/2 complete

### Phase 2: Audio Infrastructure
**Goal**: Server can receive and send audio streams with VAD processing
**Depends on**: Phase 1
**Requirements**: AUDIO-01, AUDIO-02, AUDIO-03
**Success Criteria** (what must be TRUE):
  1. Server can receive audio bytes from a connection
  2. Server can send audio bytes to a connection
  3. VAD events are processed and logged
**Plans**: 2/2 complete

### Phase 3: STT Pipeline
**Goal**: Convert speech to text with streaming partial transcriptions
**Depends on**: Phase 2
**Requirements**: STT-01, STT-02, STT-03
**Success Criteria** (what must be TRUE):
  1. Speech audio produces text transcription
  2. Partial transcriptions appear while speaking
  3. Transcription uses VAD boundaries (not fixed chunks)
**Plans**: 2/2 complete

### Phase 4: State Machine
**Goal**: Conversation flow orchestration with barge-in support
**Depends on**: Phase 2
**Requirements**: STATE-01, STATE-02, STATE-03
**Success Criteria** (what must be TRUE):
  1. System transitions through IDLE → LISTENING → PROCESSING → SPEAKING
  2. State changes are broadcast to connected clients
  3. Barge-in during SPEAKING returns to LISTENING
**Plans**: 2/2 complete

### Phase 5: LLM Integration
**Goal**: Generate streaming responses using Phi-3 Mini (3.8B)
**Depends on**: Phase 3, Phase 4
**Requirements**: LLM-01, LLM-02, LLM-03
**Success Criteria** (what must be TRUE):
  1. Text input produces conversational response
  2. Response tokens stream to output
  3. Memory stays within 8GB target
**Plans**: 2/2 complete

### Phase 6: TTS Pipeline
**Goal**: Synthesize streaming speech output using Kokoro ONNX
**Depends on**: Phase 5
**Requirements**: TTS-01, TTS-02, TTS-03
**Success Criteria** (what must be TRUE):
  1. Text produces synthesized audio
  2. Audio streams as synthesis progresses
  3. Long responses pause at sentence boundaries
**Plans**: 2/2 complete

### Phase 7: Persona System
**Goal**: YAML-configured personality affecting response behavior
**Depends on**: Phase 5
**Requirements**: PERSONA-01, PERSONA-02
**Success Criteria** (what must be TRUE):
  1. Persona loads from YAML file
  2. Persona affects response style/behavior
**Plans**: 1/1 complete

### Phase 8: WebRTC Transport
**Goal**: Real-time bidirectional audio transport with data channel
**Depends on**: Phase 2, Phase 4, Phase 6
**Requirements**: TRANSPORT-01, TRANSPORT-02, TRANSPORT-03
**Success Criteria** (what must be TRUE):
  1. Client can establish WebRTC connection to server
  2. Audio flows bidirectionally over connection
  3. Data channel carries VAD/state messages
**Plans**: 4/4 complete

### Phase 9: Flutter Client Core
**Goal**: Mobile app with audio capture, playback, VAD, and WebRTC
**Depends on**: Phase 8
**Requirements**: CLIENT-AUDIO-01, CLIENT-AUDIO-02, CLIENT-AUDIO-03, CLIENT-AUDIO-04
**Success Criteria** (what must be TRUE):
  1. App captures audio from phone microphone
  2. App plays audio through phone speaker
  3. App detects speech locally (VAD)
  4. App connects to server via WebRTC
**Plans**: 3/3 complete

### Phase 10: Flutter Client UI
**Goal**: Animated 3D ball UI with state visualization and barge-in
**Depends on**: Phase 9
**Requirements**: CLIENT-UI-01, CLIENT-UI-02, CLIENT-UI-03
**Success Criteria** (what must be TRUE):
  1. App displays animated 3D ball
  2. Ball pulses when user/AI is speaking
  3. Ball visual reflects current state (IDLE/LISTENING/PROCESSING/SPEAKING)
  4. Barge-in gesture interrupts AI
**Plans**: 2/2 complete

### Phase 11: Flutter Client Platform
**Goal**: Working Android and iOS builds
**Depends on**: Phase 10
**Requirements**: CLIENT-PLATFORM-01, CLIENT-PLATFORM-02
**Success Criteria** (what must be TRUE):
  1. App builds and runs on Android device
  2. App builds and runs on iOS device
**Plans**: 1/1 complete

### Phase 12: Integration & Latency
**Goal**: End-to-end pipeline working with sub-second latency
**Depends on**: Phase 11
**Requirements**: (validates all prior requirements)
**Success Criteria** (what must be TRUE):
  1. Full voice-to-voice loop works end-to-end
  2. P50 latency < 500ms (measured)
  3. P95 latency < 800ms (measured)
**Plans**: 3/3 complete

</details>

---

### 🚧 v2.0 TARS (In Progress)

**Milestone Goal:** Evolve Ergos from a voice chatbot into an agentic personal AI assistant with human-like conversation feel, vision, tool execution, and TARS personality. All processing local, all models fitting within 16GB VRAM.

#### Phase 13: Model Upgrade & VRAM Orchestration
**Goal**: All v2 models loaded concurrently within 16GB VRAM budget, with upgraded LLM and STT ready for production use
**Depends on**: Phase 12
**Requirements**: MODEL-01, MODEL-02, MODEL-03, ARCH-01
**Success Criteria** (what must be TRUE):
  1. Qwen3-8B (or Qwen3.5-9B) responds to queries with native tool-calling format
  2. STT accuracy improves measurably with small.en INT8 vs previous tiny.en
  3. All models (STT ~1GB, LLM ~5.2GB, TTS ~0.5GB) load simultaneously without OOM errors
  4. VRAM monitor reports total usage under 12GB with all models active
  5. Existing voice conversation flow works end-to-end with new model stack
**Plans**: 2 plans
Plans:
- [ ] 13-01-PLAN.md — VRAM orchestration infrastructure + STT upgrade to small.en INT8
- [ ] 13-02-PLAN.md — LLM upgrade to Qwen3-8B chatml + VRAM integration + concurrent loading verification

#### Phase 14: Full-Duplex Conversation
**Goal**: Users can talk and interrupt naturally — zero awkward silences, sub-300ms response, barge-in within 200ms
**Depends on**: Phase 13
**Requirements**: VOICE-01, VOICE-02, VOICE-03
**Success Criteria** (what must be TRUE):
  1. First AI audio begins within 300ms of user finishing speech (measured P50)
  2. User can speak while AI is speaking and AI continues to listen (SPEAKING_AND_LISTENING state active)
  3. When user speaks during AI output, AI audio stops within 200ms and system transitions to processing the interruption
  4. State machine logs SPEAKING_AND_LISTENING transitions correctly
**Plans**: TBD

#### Phase 15: Expressive Voice
**Goal**: AI voice delivers emotion, natural pauses, and timed sarcastic delivery via upgraded TTS
**Depends on**: Phase 14
**Requirements**: VOICE-04
**Success Criteria** (what must be TRUE):
  1. AI voice varies pitch and cadence across statement types (questions, jokes, commands)
  2. Sarcastic responses include audible timing pauses characteristic of dry delivery
  3. Emotional tone in responses is perceptibly different from flat TTS output (user-verifiable by ear)
**Plans**: TBD

#### Phase 16: TARS Personality
**Goal**: AI has consistent TARS-like dry wit, context-aware humor, and persistent memory across sessions
**Depends on**: Phase 13
**Requirements**: PERS-01, PERS-02, PERS-03
**Success Criteria** (what must be TRUE):
  1. Sarcasm level slider (0-100%) changes response tone — 0% is neutral, 100% is maximum dry wit
  2. AI makes jokes that reference what the user is currently doing (screen context or recent conversation topic)
  3. AI recalls a user preference or running joke from a previous session without being re-told
  4. TARS persona loads from configuration and overrides default system prompt behavior
**Plans**: TBD

#### Phase 17: Agentic Execution
**Goal**: AI executes multi-step workflows using tools, narrates its actions, and accepts new tools without code changes
**Depends on**: Phase 13, Phase 16
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04
**Success Criteria** (what must be TRUE):
  1. AI calls a file operation or shell command tool in response to a natural language request and returns the result
  2. During tool execution AI speaks a narration phrase before and after the call ("Let me check that..." / "Done.")
  3. AI completes a multi-step request (e.g., find a file, read its contents, summarize) using chained tool calls
  4. A new tool added to the tool registry YAML is available for calling without restarting the server or modifying Python code
**Plans**: TBD

#### Phase 18: Vision
**Goal**: AI can see the screen, read documents, and interact with UI elements on the user's desktop
**Depends on**: Phase 13, Phase 17
**Requirements**: VIS-01, VIS-02, VIS-03
**Success Criteria** (what must be TRUE):
  1. User asks "what's on my screen?" and AI gives an accurate verbal description of the current display
  2. User holds up or shares a PDF/image and AI correctly summarizes its content
  3. AI successfully clicks a visible button or fills a form field when instructed by the user
  4. Vision model (Moondream 2B INT8 ~1.5GB) loads within existing VRAM budget alongside other models
**Plans**: TBD

#### Phase 19: Cloud Fallback
**Goal**: Users can optionally route a single query to a cloud LLM with explicit per-query consent
**Depends on**: Phase 17
**Requirements**: ARCH-02
**Success Criteria** (what must be TRUE):
  1. User can say "use cloud for this" and AI asks for explicit confirmation before sending any data externally
  2. Without user confirmation, no query data leaves the local machine
  3. Cloud response integrates into conversation flow identically to local response
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 13 → 14 → 15 → 16 → 17 → 18 → 19

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 2/2 | Complete | 2026-01-26 |
| 2. Audio Infrastructure | v1.0 | 2/2 | Complete | 2026-01-26 |
| 3. STT Pipeline | v1.0 | 2/2 | Complete | 2026-01-26 |
| 4. State Machine | v1.0 | 2/2 | Complete | 2026-01-26 |
| 5. LLM Integration | v1.0 | 2/2 | Complete | 2026-01-26 |
| 6. TTS Pipeline | v1.0 | 2/2 | Complete | 2026-01-26 |
| 7. Persona System | v1.0 | 1/1 | Complete | 2026-01-26 |
| 8. WebRTC Transport | v1.0 | 4/4 | Complete | 2026-01-26 |
| 9. Flutter Client Core | v1.0 | 3/3 | Complete | 2026-01-26 |
| 10. Flutter Client UI | v1.0 | 2/2 | Complete | 2026-01-26 |
| 11. Flutter Client Platform | v1.0 | 1/1 | Complete | 2026-01-26 |
| 12. Integration & Latency | v1.0 | 3/3 | Complete | 2026-01-26 |
| 13. Model Upgrade & VRAM Orchestration | 2/2 | Complete   | 2026-03-03 | - |
| 14. Full-Duplex Conversation | v2.0 | 0/? | Not started | - |
| 15. Expressive Voice | v2.0 | 0/? | Not started | - |
| 16. TARS Personality | v2.0 | 0/? | Not started | - |
| 17. Agentic Execution | v2.0 | 0/? | Not started | - |
| 18. Vision | v2.0 | 0/? | Not started | - |
| 19. Cloud Fallback | v2.0 | 0/? | Not started | - |

---
*Roadmap created: 2026-01-26*
*v2.0 phases added: 2026-03-03*
