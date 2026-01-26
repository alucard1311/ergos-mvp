# Project Research Summary

**Project:** Ergos
**Domain:** Local-first voice assistant / Real-time AI audio pipeline
**Researched:** 2026-01-26
**Confidence:** HIGH

## Executive Summary

Ergos is entering a well-established domain with clear best practices. The chosen stack (faster-whisper, llama-cpp-python, Kokoro ONNX, aiortc) represents the optimal 2024-2025 combination for local-first voice assistants. Research confirms this approach is sound, with the primary challenges being latency optimization and proper barge-in handling.

The critical success factor is **streaming everything**. Sequential processing (record → transcribe → generate → synthesize) creates 3-5 second latency. Concurrent streaming with proper pipeline architecture achieves sub-second voice-to-voice response. The state machine design (IDLE → LISTENING → PROCESSING → SPEAKING) with client-side VAD for instant barge-in detection is the industry-standard approach.

Key risks center on llama-cpp-python memory management at the <8GB RAM target and Whisper's tendency to hallucinate on silence. Both have documented mitigations. The architecture must be async-first from day one—blocking operations in the audio pipeline create cascading failures that are difficult to diagnose and fix later.

## Key Findings

### Recommended Stack

The stated stack is optimal. Key additions and version pins from research:

**Core technologies:**
- **faster-whisper 1.2.x**: 4x faster than openai-whisper, CTranslate2 backend — verified optimal for local STT
- **llama-cpp-python 0.3.x**: Best local LLM inference, requires careful memory management — use KV cache quantization
- **kokoro-onnx 0.4.x**: Fast, high-quality local TTS via ONNX — 82M parameter model
- **aiortc 1.14.x**: WebRTC for Python, handles NAT traversal — industry standard for real-time audio
- **silero-vad 6.x**: Best VAD accuracy (<1ms per 30ms chunk), 4x fewer errors than webrtcvad — critical addition

**What NOT to use:**
- openai-whisper (4x slower)
- webrtcvad (outdated GMM, poor accuracy)
- PyAudio (installation issues)
- pyttsx3 (low quality)

### Expected Features

**Must have (table stakes):**
- Speech-to-text with <1.5s latency — users expect instant response
- Text-to-speech with natural voice — low-quality TTS feels broken
- Basic commands (timer, alarm, time) — 57% of voice use is simple commands
- Visual/audio feedback for listening state — users need to know when active

**Should have (competitive):**
- Barge-in support — natural conversation requires interruption
- Streaming responses — start speaking before full response ready
- Configuration via CLI/YAML — power users expect customization
- Hardware auto-detection — reduces setup friction

**Defer (v2+):**
- Wake word detection — adds complexity, use explicit activation for v1
- Multi-language — English only reduces scope
- Smart home integration — separate concern, can add via plugins
- Mobile apps — desktop first

### Architecture Approach

The research validates the planned architecture with one critical addition: **client-side VAD**.

**Major components:**
1. **Transport Layer (aiortc)**: WebRTC signaling, Opus audio codec, data channel for control
2. **Audio Pipeline**: Client-side VAD, sample rate conversion (48kHz→16kHz), echo cancellation
3. **AI Pipeline**: STT→LLM→TTS with streaming at every stage
4. **State Machine**: IDLE/LISTENING/PROCESSING/SPEAKING with barge-in transitions
5. **Persona System**: YAML configuration, system prompt generation

**Critical pattern:** Frame-based pipeline (Pipecat style) where SystemFrames (interrupts) bypass queues for immediate processing.

### Critical Pitfalls

1. **Whisper 30-second chunking**: Use VAD-based segmentation, not fixed windows; set `condition_on_previous_text=False` to prevent hallucinations
2. **llama-cpp-python memory**: Limit context size explicitly; use KV cache quantization; queue all inference requests (not concurrent)
3. **Blocking operations**: ALL audio/model operations must run in executor; blocking event loop destroys real-time performance
4. **Latency tolerance**: >500ms feels unnatural, >800ms causes frustration — target P50 <500ms, P95 <800ms
5. **Barge-in failure**: Requires immediate TTS stop, audio buffer clearing, and proper echo cancellation — test with speakers, not headphones

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Project Foundation
**Rationale:** Configuration and CLI must exist before any component integration
**Delivers:** pyproject.toml, CLI skeleton, configuration system, hardware detection
**Addresses:** Table stakes (configurable system)
**Avoids:** Hardcoded parameters pitfall

### Phase 2: Audio Infrastructure
**Rationale:** Audio pipeline is foundation for everything; sample rate mismatches cause cascading failures
**Delivers:** Audio capture/playback, sample rate standardization (16kHz), VAD integration (silero-vad)
**Uses:** sounddevice, silero-vad, numpy/scipy
**Avoids:** Sample rate mismatch pitfall, blocking operations pitfall

### Phase 3: STT Pipeline
**Rationale:** STT is the entry point for all user interaction
**Delivers:** faster-whisper integration with streaming, VAD-triggered transcription, hallucination prevention
**Implements:** Streaming STT pattern
**Avoids:** 30-second chunking pitfall, hallucination pitfall

### Phase 4: State Machine
**Rationale:** Orchestration layer must exist before adding more pipeline components
**Delivers:** IDLE/LISTENING/PROCESSING/SPEAKING states, transition logic, async callbacks
**Implements:** FSM architecture pattern
**Avoids:** Blocking state transitions anti-pattern

### Phase 5: LLM Integration
**Rationale:** Core intelligence layer, but requires careful memory management
**Delivers:** llama-cpp-python integration, streaming token output, context management, memory controls
**Uses:** llama-cpp-python with KV quantization
**Avoids:** Memory consumption pitfall, concurrency pitfall

### Phase 6: TTS Pipeline
**Rationale:** Output must stream to achieve low latency
**Delivers:** Kokoro ONNX integration, streaming audio output, sentence-boundary chunking
**Implements:** Streaming TTS pattern
**Avoids:** Buffer underrun pitfall

### Phase 7: Barge-In System
**Rationale:** Critical for natural conversation; depends on all pipeline components
**Delivers:** Immediate interrupt detection, TTS cancellation, audio buffer clearing, echo cancellation
**Addresses:** Barge-in support (differentiator)
**Avoids:** Barge-in failure pitfall — test extensively with real speakers

### Phase 8: WebRTC Transport
**Rationale:** Real-time bidirectional audio transport
**Delivers:** Signaling server, WebRTC peer connections, Opus codec handling, data channel protocol
**Uses:** aiortc, FastAPI
**Implements:** WebRTC transport pattern

### Phase 9: Persona System
**Rationale:** Customization layer, lower risk than core pipeline
**Delivers:** YAML persona loading, personality traits, system prompt generation, voice settings
**Addresses:** Customizable personality (differentiator)

### Phase 10: Integration & Latency
**Rationale:** Full pipeline must work together; latency optimization requires all components
**Delivers:** End-to-end pipeline tests, latency benchmarks, component telemetry
**Addresses:** Sub-second latency (table stakes)
**Avoids:** Missing telemetry debt pattern

### Phase 11: Error Handling & Polish
**Rationale:** Production hardening after core functionality works
**Delivers:** Graceful degradation, error recovery, CLI completion, logging
**Avoids:** Edge case failures

### Phase 12: Documentation
**Rationale:** Final phase after implementation stabilizes
**Delivers:** README, setup guide, API documentation

### Phase Ordering Rationale

- **Foundation first (1-2):** Configuration and audio infrastructure are prerequisites for everything
- **Pipeline components in order (3, 5, 6):** STT→LLM→TTS follows data flow
- **State machine before barge-in (4, 7):** Orchestration must exist before interrupt handling
- **Transport after pipeline (8):** WebRTC wraps working pipeline
- **Polish last (9-12):** Persona, testing, and docs after core works

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 7 (Barge-In):** Echo cancellation is complex; may need to evaluate AEC libraries
- **Phase 8 (WebRTC):** aiortc specifics for audio streaming need API exploration

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Standard Python project setup
- **Phase 3 (STT):** faster-whisper API is well-documented
- **Phase 4 (State Machine):** Standard FSM pattern

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified via PyPI, official docs, GitHub |
| Features | HIGH | Based on OVOS, Home Assistant Voice, user research |
| Architecture | HIGH | Pipecat, LiveKit, Deepgram patterns well-documented |
| Pitfalls | HIGH | Multiple GitHub issues, post-mortems, community reports |

**Overall confidence:** HIGH

### Gaps to Address

- **Echo cancellation library selection:** Research specific AEC options during Phase 7 planning
- **Kokoro ONNX streaming:** Limited documentation; may need experimentation
- **Memory usage on target hardware:** Verify <8GB achievable with chosen model sizes

## Sources

### Primary (HIGH confidence)
- faster-whisper GitHub/PyPI — version, API, performance benchmarks
- llama-cpp-python GitHub — memory management, concurrency issues
- aiortc GitHub — WebRTC implementation
- kokoro-onnx GitHub — TTS integration
- silero-vad GitHub — VAD accuracy benchmarks
- Pipecat documentation — pipeline architecture patterns
- Deepgram, LiveKit docs — voice AI architecture patterns

### Secondary (MEDIUM confidence)
- Home Assistant Voice, OVOS — feature expectations for local voice assistants
- AssemblyAI, Modal blogs — latency optimization techniques
- Community GitHub issues — real-world pitfall documentation

### Tertiary (LOW confidence)
- Various blog posts on voice AI — general patterns, need verification

---
*Research completed: 2026-01-26*
*Ready for roadmap: yes*
