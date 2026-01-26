---
phase: 04-state-machine
plan: 02
subsystem: state-machine
tags: [asyncio, barge-in, broadcast, callbacks]

# Dependency graph
requires:
  - phase: 04-state-machine/01
    provides: ConversationStateMachine, StateChangeEvent, async callbacks
provides:
  - barge_in() method for user interruption handling
  - BargeInCallback type for buffer-clearing hooks
  - StateChangeEvent.to_dict() for client broadcast
  - is_interruptible property for barge-in capability check
  - stats property for state machine monitoring
affects: [audio-pipeline, tts, transport, webrtc]

# Tech tracking
tech-stack:
  added: []
  patterns: [barge-in-callbacks, event-serialization, interruptible-states]

key-files:
  created: []
  modified:
    - src/ergos/state/machine.py
    - src/ergos/state/events.py
    - src/ergos/state/__init__.py

key-decisions:
  - "Barge-in callbacks invoked before state transition to allow buffer clearing"
  - "StateChangeEvent serializes to dict for WebRTC data channel broadcast"
  - "is_interruptible property checks SPEAKING or PROCESSING states"

patterns-established:
  - "Barge-in callbacks are no-arg async functions (buffer.clear() pattern)"
  - "Event.to_dict() for broadcast-ready serialization"
  - "stats property for component monitoring"

# Metrics
duration: 2min
completed: 2026-01-26
---

# Phase 4 Plan 2: Barge-in and Broadcast Summary

**Barge-in support with callback hooks and broadcast-ready state event serialization**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-26T20:15:00Z
- **Completed:** 2026-01-26T20:17:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Added barge_in() method that transitions SPEAKING/PROCESSING to LISTENING
- Created BargeInCallback type for registering buffer-clearing hooks
- Added to_dict() to StateChangeEvent for client broadcast serialization
- Added is_interruptible and stats properties for monitoring

## Task Commits

Each task was committed atomically:

1. **Task 1: Add barge-in support** - `18fe223` (feat)
2. **Task 2: Add broadcast metadata and stats** - `34b998e` (feat)
3. **Task 3: Update state package exports** - `ed2f3c9` (feat)

## Files Created/Modified

- `src/ergos/state/machine.py` - Added barge_in(), BargeInCallback, is_interruptible, stats
- `src/ergos/state/events.py` - Added to_dict() for broadcast serialization
- `src/ergos/state/__init__.py` - Exported BargeInCallback type

## Decisions Made

- Barge-in callbacks invoked before transition to allow buffer clearing first
- StateChangeEvent.to_dict() includes type, previous, state, timestamp, metadata
- is_interruptible returns True only for SPEAKING and PROCESSING states

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- State machine complete with full barge-in support
- Ready for Phase 5: LLM integration
- Audio pipeline can register barge-in callbacks to clear TTS buffers
- Transport layer can broadcast state changes to clients via data channel

---
*Phase: 04-state-machine*
*Completed: 2026-01-26*
