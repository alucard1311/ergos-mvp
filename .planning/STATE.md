---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: TARS
status: planning
stopped_at: "Checkpoint: 15-02 Task 2 human-verify"
last_updated: "2026-03-04T03:05:41.657Z"
last_activity: 2026-03-03 — v2.0 roadmap created, phases 13-19 defined
progress:
  total_phases: 19
  completed_phases: 15
  total_plans: 33
  completed_plans: 33
  percent: 96
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Complete privacy through local-only processing
**Current focus:** Milestone v2.0 TARS — Phase 13: Model Upgrade & VRAM Orchestration

## Current Position

Phase: 13 of 19 (Model Upgrade & VRAM Orchestration)
Plan: 0 of ? in current phase
Status: Ready to plan
Last activity: 2026-03-03 — v2.0 roadmap created, phases 13-19 defined

Progress: [██████████] 96%

## v1 Performance Metrics (archived)

**Velocity:**
- Total plans completed: 26
- Average duration: 2.6 min
- Total execution time: 67 min

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
v2-relevant decisions:

- Phase 13: Qwen3-8B Q4_K_M (~5.2GB) as LLM upgrade — best tool-calling F1 in 16GB VRAM budget
- Phase 13: STT upgrade to faster-whisper small.en INT8 (~1GB) for accuracy improvement
- Phase 13: ARCH-01 (VRAM orchestration) co-located with model upgrades — prerequisite for all v2 models
- Phase 15: Kokoro-82M ONNX stays as base TTS; Orpheus is upgrade path for emotion/expressiveness
- Phase 18: Moondream 2B INT8 (~1.5GB) for vision — strong UI localization, Pipecat-compatible
- All models must fit concurrently: ~11.2GB of 16GB VRAM (~4.8GB headroom for KV cache)
- Cascaded pipeline retained (text intermediary enables tool-calling and debugging)
- [Phase 13-model-upgrade-vram-orchestration]: VRAMMonitor uses torch.cuda.mem_get_info() with None fallback for zero-dep CPU compatibility
- [Phase 13-model-upgrade-vram-orchestration]: STT upgraded to faster-whisper small.en INT8 (~1GB VRAM) in config.yaml for v2 accuracy
- [Phase 13-model-upgrade-vram-orchestration]: chatml is default chat_format for LLMGenerator and LLMProcessor — Qwen3 works out of the box
- [Phase 13-model-upgrade-vram-orchestration]: Phi-3 format preserved as backward-compatible fallback via chat_format='phi3'
- [Phase 13-model-upgrade-vram-orchestration]: VRAM registration hardcoded at pipeline creation: STT=1000MB, LLM=5200MB, TTS=500MB — known estimates, no dynamic file scanning
- [Phase 14-full-duplex-conversation]: Flutter state strings are UPPERCASE (ServerState.fromJson calls .toUpperCase()) — all state checks use UPPERCASE including SPEAKING_AND_LISTENING
- [Phase 14-full-duplex-conversation]: VAD redemptionFrames reduced from 45 to 16 (~512ms) for fast turn-taking per CONTEXT.md locked decision
- [Phase 14-full-duplex-conversation]: SPEAKING_AND_LISTENING -> PROCESSING not allowed — must go through LISTENING to avoid bypassing STT
- [Phase 14-full-duplex-conversation]: LLM generate_stream() resets _cancelled=False at start — prevents silent empty generation after barge-in (Pitfall 3)
- [Phase 14-full-duplex-conversation]: on_barge_in cancel order: LLM -> TTS -> audio tracks prevents TTS from re-queuing after cancel
- [Phase 14-full-duplex-conversation]: Idle timeout starts on IDLE state entry via state change callback — 30s after system goes IDLE
- [Phase 14-full-duplex-conversation]: on_llm_complete barge-in guard checks PROCESSING/SPEAKING/SPEAKING_AND_LISTENING before audio drain
- [Phase 15-expressive-voice]: OrpheusSynthesizer uses orpheus-cpp lazy loading; registered as [orpheus] optional dep; VRAM 2000MB at Q4_K_M
- [Phase 15-expressive-voice]: EmotionMarkupProcessor: regex r'\*(\w+)\*' with .lower() for case-insensitive hint matching, unknown hints stripped entirely
- [Phase 15-expressive-voice]: Ellipsis (...) converted to ', ' (comma+space) for Orpheus sarcasm pause timing
- [Phase 15-expressive-voice]: engine field added to TTSProcessor (default 'kokoro') — controls emotion markup activation, zero regression for existing deployments

### Pending Todos

1. Add local speaker output mode bypassing WebRTC (`--local-audio` flag, sounddevice)

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-04T03:05:29.868Z
Stopped at: Checkpoint: 15-02 Task 2 human-verify
Resume file: None
