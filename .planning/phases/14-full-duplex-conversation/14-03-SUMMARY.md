---
phase: 14-full-duplex-conversation
plan: 03
subsystem: pipeline
tags: [full-duplex, barge-in, pipeline, state-machine, idle-timeout, speaking-and-listening]

# Dependency graph
requires:
  - phase: 14-full-duplex-conversation
    provides: SPEAKING_AND_LISTENING enum, updated VALID_TRANSITIONS, barge_in() with callbacks, LLM cancel reset fix (plan 01)
provides:
  - Barge-in callback active in pipeline.py: cancels LLM generation + TTS synthesis + audio track buffers
  - on_vad_for_state handles SPEAKING -> SPEAKING_AND_LISTENING with 500ms overlap timer
  - SPEECH_END during SPEAKING_AND_LISTENING triggers barge_in() -> PROCESSING
  - on_incoming_audio routes audio to STT during SPEAKING_AND_LISTENING state
  - on_tts_audio allows TTS audio during SPEAKING_AND_LISTENING (overlap window)
  - on_vad_reset_flags resets TTS cancellation on SPEAKING_AND_LISTENING SPEECH_START
  - 30s idle timeout: starts on IDLE entry, cancelled on LISTENING/PROCESSING entry
  - on_llm_complete skips audio drain loop when barge-in already changed state
affects:
  - 14-full-duplex-conversation (plan 04 if any: pipeline integration tests)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "List-wrapper pattern for asyncio.Task in closures: _overlap_timer_task = [None] allows mutation from nested async def without nonlocal"
    - "Barge-in cancel sequence order: LLM cancel flag -> TTS cancel -> _first_audio_sent reset -> audio track buffer clear"
    - "State-gated TTS audio: check state at callback entry AND after start_speaking() transition attempt"
    - "Idle timeout via state change callback: _on_state_change_for_idle_timeout starts/cancels timer based on new_state"
    - "Barge-in guard in on_llm_complete: check state before audio drain to avoid spurious IDLE transitions after barge-in"

key-files:
  created: []
  modified:
    - src/ergos/pipeline.py

key-decisions:
  - "on_barge_in cancels LLM before TTS before audio tracks — order prevents TTS from re-queuing tokens after cancel"
  - "Overlap timer uses list wrapper [None] pattern instead of nonlocal — avoids nested closure scoping issues in Python"
  - "Idle timeout starts on IDLE entry (not after audio drains) — simpler and correct: 30s after system goes IDLE"
  - "on_llm_complete barge-in guard checks PROCESSING/SPEAKING/SPEAKING_AND_LISTENING — matches states where audio drain is valid"

patterns-established:
  - "Full-duplex pipeline pattern: SPEECH_START during SPEAKING -> SPEAKING_AND_LISTENING -> 500ms timer -> barge_in() -> PROCESSING"
  - "Overlap cancellation pattern: SPEECH_END before timer fires cancels timer and calls barge_in() immediately"
  - "State-gated audio routing: all audio callbacks (incoming + outgoing) check current state at entry"

requirements-completed: [VOICE-01, VOICE-02, VOICE-03]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 14 Plan 03: Full-Duplex Pipeline Wiring Summary

**Full-duplex barge-in wired in pipeline.py: LLM+TTS cancel on user interruption, 500ms overlap timer, SPEAKING_AND_LISTENING audio routing, and 30s idle timeout**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-04T02:02:40Z
- **Completed:** 2026-03-04T02:06:07Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Barge-in callback activated (was commented out): cancels LLM generation, TTS synthesis, and audio track buffers in correct order
- on_vad_for_state rewritten for full-duplex: SPEECH_START during SPEAKING transitions to SPEAKING_AND_LISTENING with 500ms overlap timer
- SPEECH_END during SPEAKING_AND_LISTENING cancels overlap timer and immediately calls barge_in() -> start_processing()
- on_incoming_audio now routes audio to STT during SPEAKING_AND_LISTENING (was IDLE/LISTENING only)
- on_tts_audio now allows TTS audio during SPEAKING_AND_LISTENING overlap window (AI audio continues during barge-in window)
- on_vad_reset_flags updated: resets TTS cancellation on SPEECH_START in SPEAKING_AND_LISTENING (prevents Pitfall 2)
- 30s idle timeout implemented via state change callback: starts on IDLE entry, cancelled on LISTENING/PROCESSING entry
- on_llm_complete now handles post-barge-in state: skips audio drain loop if state already changed due to barge-in
- All 124 unit tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire barge-in callback and overlap timer** - `c61cc1dd` (feat)
2. **Task 2: Add idle timeout and update on_llm_complete for post-barge-in** - `1d8a1555` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/ergos/pipeline.py` - Full-duplex pipeline wiring: barge-in callback, overlap timer, SPEAKING_AND_LISTENING audio routing, idle timeout, barge-in-aware on_llm_complete

## Decisions Made

- on_barge_in cancels LLM first, then TTS, then audio tracks — this order ensures TTS doesn't receive new tokens after the cancel flag is set
- Overlap timer uses list wrapper `[None]` pattern for asyncio.Task instead of `nonlocal` — avoids Python closure scoping issues with nested async defs
- Idle timeout starts on IDLE state entry (not on audio drain complete) — cleaner model: 30s after system enters idle is the right semantic
- on_llm_complete barge-in guard checks PROCESSING/SPEAKING/SPEAKING_AND_LISTENING — these are the only states where audio drain makes sense

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — pipeline changes were straightforward. Verified with `add_barge_in_callback` no longer commented out, all state guards updated.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Full-duplex conversation pipeline is complete: VOICE-01, VOICE-02, and VOICE-03 requirements are all satisfied
- Barge-in flow: IDLE -> LISTENING -> PROCESSING -> SPEAKING -> SPEAKING_AND_LISTENING -> (barge_in) -> LISTENING -> PROCESSING -> SPEAKING
- 30s idle timeout ensures system doesn't stay in LISTENING forever after a completed exchange
- LLM cancel reset fix (plan 01) + barge-in wiring (this plan) complete the barge-in story end-to-end

---
*Phase: 14-full-duplex-conversation*
*Completed: 2026-03-04*

## Self-Check: PASSED

- src/ergos/pipeline.py: FOUND
- .planning/phases/14-full-duplex-conversation/14-03-SUMMARY.md: FOUND
- Commit c61cc1dd: FOUND
- Commit 1d8a1555: FOUND
