---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: TARS
status: executing
stopped_at: Completed 16-03-PLAN.md (TARS personality pipeline wiring)
last_updated: "2026-03-04T05:12:24.137Z"
last_activity: 2026-03-04 - Completed quick task 1: Research smooth human-like TTS voice transitions
progress:
  total_phases: 19
  completed_phases: 16
  total_plans: 36
  completed_plans: 36
  percent: 97
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Complete privacy through local-only processing
**Current focus:** Milestone v2.0 TARS — Phase 16: TARS Personality (next)

## Current Position

Phase: 16 of 19 (TARS Personality) — In Progress
Plan: 1 of 3 in current phase — COMPLETE (16-01 TARS personality infrastructure)
Status: Phase 16 in progress; 16-01 complete, 16-02 and 16-03 remaining
Last activity: 2026-03-04 — Phase 16 Plan 01 complete (TARS personality infrastructure)

Progress: [██████████] 97% (35/36 plans complete)

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
- [Phase 16-tars-personality]: MemoryStore scoring formula: 0.7*norm_timestamp + 0.3*norm_access_count — recency-weighted with frequency boost for pruning
- [Phase 16-tars-personality]: prune_respects_access_count test uses same-age entries to isolate access_count effect — different timestamps cannot overcome 0.7 recency weight
- [Phase 16-tars-personality]: MEMORY_PATH = ~/.ergos/memory.json at top level (not under plugins/) — cross-session memory is a core feature
- [Phase 16-tars-personality]: Section-based sarcasm blending uses two fixed template tiers (NEUTRAL/MAX_SARCASM) — cleaner output than interpolation
- [Phase 16-tars-personality]: DEFAULT_PERSONA and PersonaConfig.name both changed from 'Ergos' to 'TARS' — TARS is the v2 identity
- [Phase 16-tars-personality]: try_sarcasm_command() regex uses lookbehind (?<!\w) to capture negative sarcasm values like -10%
- [Phase 16-tars-personality]: Memory extraction uses generator.generate() directly (not llm_processor) to avoid polluting conversation history
- [Phase 16-tars-personality]: ConnectionManager.set_disconnect_callback() added as clean hook for peer disconnect lifecycle events
- [Phase 16-tars-personality]: Sarcasm command intercept is first gate in on_transcription_with_plugins() — returns early so command never reaches plugins or LLM

### Pending Todos

1. Add local speaker output mode bypassing WebRTC (`--local-audio` flag, sounddevice)

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Research smooth human-like TTS voice transitions | 2026-03-04 | 8e783ad | [1-research-smooth-human-like-tts-voice-tra](./quick/1-research-smooth-human-like-tts-voice-tra/) |

## Session Continuity

Last session: 2026-03-04T05:12:24.136Z
Stopped at: Completed 16-03-PLAN.md (TARS personality pipeline wiring)
Resume file: None
