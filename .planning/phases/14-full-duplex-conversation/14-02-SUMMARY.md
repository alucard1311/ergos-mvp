---
phase: 14-full-duplex-conversation
plan: 02
subsystem: ui
tags: [flutter, webrtc, vad, barge-in, full-duplex, animation]

# Dependency graph
requires:
  - phase: 14-full-duplex-conversation
    provides: SPEAKING_AND_LISTENING server state broadcast (plan 01)
provides:
  - Flutter orb SPEAKING_AND_LISTENING visual state (cyan, 400ms fast pulse)
  - Barge-in gesture guard updated for full-duplex state
  - Faster VAD speech_end threshold (~512ms vs ~1.4s)
affects:
  - 14-full-duplex-conversation (plan 03+: server-side implementation depends on client handling)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "State string casing: ServerState.fromJson() calls .toUpperCase() — all Flutter state checks use UPPERCASE"
    - "Barge-in guard pattern: OR condition covers both SPEAKING and SPEAKING_AND_LISTENING"
    - "VAD tuning: redemptionFrames=16 (~512ms) targets sub-500ms speech_end for turn-taking"

key-files:
  created: []
  modified:
    - client/lib/widgets/ergos_orb.dart
    - client/lib/main.dart
    - client/lib/services/vad_service.dart

key-decisions:
  - "State strings in Flutter are UPPERCASE because ServerState.fromJson() calls .toUpperCase() on the server's lowercase enum values"
  - "SPEAKING_AND_LISTENING uses 400ms pulse period (vs 1200ms default) for visual distinction from SPEAKING"
  - "VAD redemptionFrames reduced from 45 to 16 (512ms) per CONTEXT.md locked decision for fast turn-taking"

patterns-established:
  - "OR-guard pattern: all barge-in checks cover both SPEAKING and SPEAKING_AND_LISTENING states"

requirements-completed: [VOICE-02, VOICE-03]

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 14 Plan 02: Flutter Full-Duplex Client Update Summary

**Flutter orb gains SPEAKING_AND_LISTENING state (cyan + 400ms fast pulse) with barge-in support, and VAD speech_end reduced to ~512ms for faster turn-taking**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T01:53:06Z
- **Completed:** 2026-03-04T01:54:35Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- ErgosOrb handles SPEAKING_AND_LISTENING with cyan color and 400ms fast pulse in both normal and kitchen mode
- Tap gesture on orb during SPEAKING_AND_LISTENING sends barge_in data channel message
- "Tap to interrupt" hint text appears during both SPEAKING and SPEAKING_AND_LISTENING states
- VAD redemptionFrames reduced from 45 (~1.4s) to 16 (~512ms) for sub-500ms speech_end detection

## Task Commits

Each task was committed atomically:

1. **Task 1: Add SPEAKING_AND_LISTENING visual state to ErgosOrb** - `2ff65167` (feat)
2. **Task 2: Update barge-in guard and VAD sensitivity** - `b2679a14` (feat)

## Files Created/Modified

- `client/lib/widgets/ergos_orb.dart` - Added SPEAKING_AND_LISTENING cases in _updateForState, _colorForState (both modes), build onTap guard, and doc comment
- `client/lib/main.dart` - Updated _sendBargeIn() guard and "Tap to interrupt" hint text condition
- `client/lib/services/vad_service.dart` - Reduced redemptionFrames from 45 to 16

## Decisions Made

- State strings in Flutter are UPPERCASE: `ServerState.fromJson()` calls `.toUpperCase()` on the server's lowercase Python enum values ("speaking_and_listening" -> "SPEAKING_AND_LISTENING"). This was discovered during Task 1 by reading the model code, ensuring all switch cases use uppercase.
- 400ms pulse period for SPEAKING_AND_LISTENING chosen to be visually distinct from SPEAKING (uses controller default 1200ms) while being fast enough to indicate active dual state.
- VAD reduction to 16 frames is a locked decision from CONTEXT.md (VOICE-01 sub-300ms target) — no negotiation needed.

## Deviations from Plan

None - plan executed exactly as written. The casing investigation (checking ServerState.fromJson) was anticipated in the plan's IMPORTANT note and resolved by reading the code.

## Issues Encountered

None - Flutter analyze shows only pre-existing info-level lints (avoid_print, deprecated withOpacity in orb_painter.dart) in files not touched by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Flutter client is ready to receive and display SPEAKING_AND_LISTENING state from server
- Barge-in works correctly for both SPEAKING and SPEAKING_AND_LISTENING states
- VAD is tuned for fast turn-taking
- Awaiting: Phase 14 plan 03+ to implement server-side full-duplex state management

---
*Phase: 14-full-duplex-conversation*
*Completed: 2026-03-04*

## Self-Check: PASSED

- client/lib/widgets/ergos_orb.dart: FOUND
- client/lib/main.dart: FOUND
- client/lib/services/vad_service.dart: FOUND
- .planning/phases/14-full-duplex-conversation/14-02-SUMMARY.md: FOUND
- Commit 2ff65167: FOUND
- Commit b2679a14: FOUND
