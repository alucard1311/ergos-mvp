---
phase: 04-state-machine
plan: 01
subsystem: state-machine
tags: [asyncio, fsm, state-management, callbacks]

# Dependency graph
requires:
  - phase: 02-audio-infrastructure/02
    provides: PipelineState enum pattern, async callback pattern
provides:
  - ConversationState enum (IDLE, LISTENING, PROCESSING, SPEAKING)
  - StateChangeEvent dataclass for transition notifications
  - ConversationStateMachine with enforced valid transitions
  - Async state change callbacks
affects: [audio-pipeline, stt, llm, tts, transport]

# Tech tracking
tech-stack:
  added: []
  patterns: [async-state-machine, transition-lock, callback-pattern]

key-files:
  created:
    - src/ergos/state/events.py
    - src/ergos/state/machine.py
    - src/ergos/state/__init__.py
  modified: []

key-decisions:
  - "ConversationState separate from PipelineState (state machine is source of truth)"
  - "asyncio.Lock for thread-safe transitions"
  - "Callbacks notified after state change, errors logged but don't fail transition"

patterns-established:
  - "Valid transitions enforced via lookup table"
  - "Convenience methods (start_listening, start_processing, etc.) wrap transition_to"
  - "Reset method for error recovery bypasses validation"

# Metrics
duration: 2min
completed: 2026-01-26
---

# Phase 4 Plan 1: State Machine Foundation Summary

**Conversation state machine with enforced IDLE/LISTENING/PROCESSING/SPEAKING transitions and async callbacks**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-26T20:10:51Z
- **Completed:** 2026-01-26T20:12:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created ConversationState enum matching pipeline states (single source of truth)
- Built StateChangeEvent dataclass with previous/new state and optional metadata
- Implemented ConversationStateMachine with transition validation via lookup table
- Added asyncio.Lock for thread-safe state transitions
- Convenience methods for common transitions (start_listening, start_processing, etc.)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create state change events** - `ec05646` (feat)
2. **Task 2: Create ConversationStateMachine** - `784f90f` (feat)

## Files Created/Modified

- `src/ergos/state/events.py` - ConversationState enum, StateChangeEvent dataclass, StateChangeCallback type
- `src/ergos/state/machine.py` - ConversationStateMachine class with enforced transitions
- `src/ergos/state/__init__.py` - Package exports

## Decisions Made

- ConversationState intentionally separate from PipelineState - state machine is the single source of truth, pipeline will read from it
- Used asyncio.Lock for transition safety in concurrent async environment
- Callback errors are logged but don't prevent transitions from completing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- State machine foundation complete
- Ready for Plan 02: state broadcast and barge-in integration
- Audio pipeline can be updated to read state from ConversationStateMachine
- STT/LLM/TTS processors can register for state change callbacks

---
*Phase: 04-state-machine*
*Completed: 2026-01-26*
