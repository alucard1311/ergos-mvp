# Ergos

## What This Is

Ergos is a local-first AI agent that talks like a human, thinks like an engineer, and has the personality of a sarcastic co-pilot. It runs entirely on your hardware — no cloud, no subscriptions, no data leaving your machine. Beyond voice conversation, it can see your screen, execute commands, and manage tasks, all with TARS-like dry wit and zero awkward silences.

## Core Value

**Complete privacy through local-only processing.** Everything runs on your hardware — STT, LLM, TTS, vision, tool execution — with zero network calls for core functionality.

## Current Milestone: v2.0 TARS

**Goal:** Evolve Ergos from a voice chatbot into an agentic personal AI assistant with human-like conversation feel, vision, tool execution, and TARS personality.

**Target features:**
- Full-duplex conversation with fluid interruptions
- Natural expressive voice with emotion and sarcastic delivery
- Agentic tool execution (files, shell, browser, screen control)
- Vision/screen understanding
- TARS personality with configurable sarcasm level
- Sub-300ms perceived response time

## Requirements

### Validated

- [x] CLI interface with start, setup, persona, and status commands (v1)
- [x] Configuration system with hardware auto-detection (v1)
- [x] State machine managing conversation flow (v1)
- [x] Barge-in support — interrupt AI mid-sentence (v1)
- [x] WebRTC signaling server for audio transport (v1)
- [x] Data channel protocol for VAD events (v1)
- [x] STT integration — faster-whisper (v1)
- [x] LLM integration — llama-cpp-python (v1)
- [x] TTS integration — Kokoro via ONNX (v1)
- [x] Persona system with YAML configuration (v1)
- [x] Sub-second voice-to-voice latency (v1)
- [x] Streaming TTS — start speaking before full response (v1)

### Active

See `.planning/REQUIREMENTS.md` for v2.0 scoped requirements.

### Out of Scope

- Multi-user support — single user focus
- Smart home integrations — separate project concern
- Multi-language — English only for v2
- Wake word detection — deferred to v3
- Cloud-only mode — contradicts core value (optional fallback with consent OK)

## Context

**Technical Environment:**
- Python 3.11+ codebase
- FastAPI/aiohttp for HTTP server
- aiortc for WebRTC peer connections
- Target hardware: RTX 5080 16GB VRAM, 64GB RAM

**v1 Architecture (built):**
- Client performs VAD, sends audio via WebRTC
- Server receives audio, runs STT → LLM → TTS pipeline
- State machine coordinates conversation flow
- Data channel carries control messages
- Flutter mobile client with 3D orb UI

**v2 Model Stack (researched March 2026):**
- STT: faster-whisper small.en INT8 (~1GB VRAM)
- LLM: Qwen3-8B Q4_K_M (~5.2GB) or Qwen3.5-9B Q4 (~5GB, native multimodal)
- TTS: Kokoro-82M ONNX (~0.5GB) — upgrade path to Orpheus for emotion
- Vision: Moondream 2B INT8 (~1.5GB) or native via Qwen3.5-9B
- Total: ~11.2GB of 16GB VRAM (4.8GB headroom)

**Reference Documents:**
- `.planning/PRD.md` — Product requirements (v1)
- `.planning/TRD.md` — Technical specifications (v1)
- `memory/v2-research.md` — v2 research findings

## Constraints

- **Hardware**: RTX 5080 16GB VRAM, 64GB RAM — all models must fit concurrently
- **Performance**: < 300ms perceived response time — human conversation feel
- **VRAM**: ~11-12GB total model footprint — leave headroom for KV cache and context
- **Privacy**: No network calls for core functionality — non-negotiable core value
- **Personality**: TARS-like sarcasm with configurable level — not optional, core to identity
- **License**: MIT — open source commitment

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| WebRTC for audio transport | Low latency, handles NAT, industry standard | ✓ Good (v1) |
| Client-side VAD | Reduces server load, enables instant barge-in | ✓ Good (v1) |
| Streaming TTS | Start speaking before full response ready | ✓ Good (v1) |
| YAML personas | Human-readable, easy to customize | ✓ Good (v1) |
| Pydantic for validation | Type safety, good FastAPI integration | ✓ Good (v1) |
| Cascaded pipeline over E2E | Text intermediary enables tool-calling, debugging, flexibility | — Pending (v2) |
| Qwen3 family for LLM | Best tool-calling F1 (0.933-0.971), fits 16GB VRAM | — Pending (v2) |
| Evolve existing pipeline | Ergos architecture is sound, mirrors Pipecat patterns | — Pending (v2) |
| Moondream 2B for vision | 1.5GB VRAM, strong UI localization, Pipecat-compatible | — Pending (v2) |
| TARS personality system | Configurable sarcasm level, dry humor as core identity | — Pending (v2) |

---
*Last updated: 2026-03-03 after v2.0 milestone start*
