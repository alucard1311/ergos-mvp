---
phase: 14-full-duplex-conversation
plan: 01
subsystem: state-machine
tags: [full-duplex, barge-in, state-machine, llm, latency, tdd, pytest]

# Dependency graph
requires:
  - phase: 13-model-upgrade-vram-orchestration
    provides: LLMGenerator with chatml chat_format and cancellation support
provides:
  - SPEAKING_AND_LISTENING enum value in ConversationState (value "speaking_and_listening")
  - Updated VALID_TRANSITIONS table with 5 entries including all new state transitions
  - barge_in() handles SPEAKING_AND_LISTENING in addition to SPEAKING
  - is_interruptible includes SPEAKING_AND_LISTENING
  - LLMGenerator.generate_stream() resets _cancelled=False and sets _generating=True at start
  - Cancellation check in token yield loop with try/finally _generating=False cleanup
  - Full-duplex unit test suite (33 tests, 472 lines) covering VOICE-01/02/03
affects:
  - 14-full-duplex-conversation (plan 03: pipeline wiring depends on this state infrastructure)

# Tech tracking
tech-stack:
  added:
    - pytest-asyncio 1.3.0 (for async test support)
    - lark (installed in venv for ROS launch_testing plugin compatibility)
  patterns:
    - "TDD pattern: RED commit with failing state machine tests, then GREEN commit after implementation"
    - "Dependency mock pattern: sys.modules.setdefault() at top of test file to mock aiohttp, aiortc, llama_cpp before ergos __init__.py imports pipeline"
    - "State transition helper: _set_state_to_speaking() async helper reduces boilerplate in test setup"
    - "try/finally in async generator: ensures _generating=False even on cancellation or exception"

key-files:
  created:
    - tests/unit/test_full_duplex.py
    - .planning/phases/14-full-duplex-conversation/14-01-SUMMARY.md
  modified:
    - src/ergos/state/events.py
    - src/ergos/state/machine.py
    - src/ergos/llm/generator.py

key-decisions:
  - "SPEAKING_AND_LISTENING -> PROCESSING is explicitly NOT a valid transition — must go through LISTENING first to avoid skipping STT"
  - "_cancelled reset happens at the very top of generate_stream() before config or model checks — ensures no path skips the reset"
  - "_generating=False cleanup uses try/finally to guarantee cleanup on cancellation, exception, or normal completion"
  - "Tests use sys.modules.setdefault() (not sys.modules[mod] = ) so existing mocks from prior test files are not overwritten"
  - "Venv at .venv is the correct test runner (has llama_cpp, aiohttp) — system python lacks these"

patterns-established:
  - "Full-duplex state guard pattern: all barge-in and interruptibility checks use 'in (SPEAKING, SPEAKING_AND_LISTENING)' tuple"
  - "LLM generation lifecycle: _cancelled=False, _generating=True at start; _generating=False in finally block"
  - "Test file mock-first pattern: mock all optional heavy deps before any ergos import to allow submodule imports through the pipeline chain"

requirements-completed: [VOICE-01, VOICE-02, VOICE-03]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 14 Plan 01: Full-Duplex State Machine and LLM Cancel Fix Summary

**SPEAKING_AND_LISTENING state added to ConversationState with full transition table, barge_in() updated for both speaking states, LLM cancel flag reset fix, and 33-test full-duplex TDD suite**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-04T02:14:32Z
- **Completed:** 2026-03-04T02:18:19Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments

- ConversationState.SPEAKING_AND_LISTENING enum value ("speaking_and_listening") added with 3 valid exit transitions: LISTENING, SPEAKING, IDLE
- SPEAKING -> SPEAKING_AND_LISTENING added to VALID_TRANSITIONS (voice detected during AI speech)
- barge_in() now handles both SPEAKING and SPEAKING_AND_LISTENING states via tuple guard
- is_interruptible extended to include SPEAKING_AND_LISTENING state
- LLMGenerator.generate_stream() resets _cancelled=False and sets _generating=True at start (fixes Pitfall 3 from RESEARCH.md)
- Token loop checks _cancelled during streaming; try/finally ensures _generating=False cleanup
- 33 unit tests covering all VOICE-01 (latency P50), VOICE-02 (state transitions), and VOICE-03 (barge-in, cancel reset) requirements — all pass GREEN

## Task Commits

Each task was committed atomically:

1. **Task 1: Create full-duplex test suite (RED)** - `82786555` (test)
2. **Task 2: Add SPEAKING_AND_LISTENING state + fix LLM cancel reset (GREEN)** - `ecd6b731` (feat)

## Files Created/Modified

- `tests/unit/test_full_duplex.py` - 33 tests across 6 test classes: enum, transitions, state machine, is_interruptible, barge_in, LLM cancel reset, latency tracker
- `src/ergos/state/events.py` - Added SPEAKING_AND_LISTENING = "speaking_and_listening" to ConversationState enum
- `src/ergos/state/machine.py` - Updated VALID_TRANSITIONS (5 entries), barge_in() tuple guard, is_interruptible tuple, docstring
- `src/ergos/llm/generator.py` - generate_stream() reset _cancelled=False, set _generating=True, cancellation check in loop, try/finally cleanup

## Decisions Made

- SPEAKING_AND_LISTENING -> PROCESSING is not a valid transition (must go through LISTENING first to avoid bypassing STT processing)
- _cancelled reset is placed at the very top of generate_stream() before any other logic to ensure no code path can skip the reset
- try/finally ensures _generating=False on all exit paths (normal completion, cancellation, exception)
- Test mock setup uses sys.modules.setdefault() so prior mocks from other test files survive

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed pytest-asyncio for async test support**
- **Found during:** Task 1 (test file creation)
- **Issue:** pytest-asyncio not installed in venv; all async tests would fail to collect
- **Fix:** Installed pytest-asyncio 1.3.0 via pip into the project venv
- **Files modified:** venv only (no project files)
- **Verification:** import pytest_asyncio succeeds; all async tests run
- **Committed in:** 82786555 (Task 1 RED commit)

**2. [Rule 3 - Blocking] Installed lark in venv for ROS plugin compatibility**
- **Found during:** Task 1 (first test run attempt with venv)
- **Issue:** ROS jazzy launch_testing pytest plugin fails to load without lark, preventing any test collection
- **Fix:** Installed lark in the project venv
- **Files modified:** venv only (no project files)
- **Verification:** venv pytest runs correctly with ROS environment active
- **Committed in:** 82786555 (Task 1 RED commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking dependency installs)
**Impact on plan:** Both installs were prerequisites for running tests. No scope creep.

## Issues Encountered

- System Python lacks aiohttp, aiortc, llama_cpp — cannot use `python3 -m pytest` directly. Must use `/home/vinay/ergos/.venv/bin/python -m pytest` which has all required dependencies.
- ROS jazzy launch_testing plugin (installed at /opt/ros/jazzy/) requires lark module which was missing from venv. Fixed by installing lark.
- Test file uses `sys.modules.setdefault()` for mocking heavy deps instead of direct assignment — this prevents overwriting mocks that may already be set up by the venv's pytest plugin chain.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- State machine infrastructure is complete for plan 03 (pipeline wiring)
- SPEAKING_AND_LISTENING state is in place and tested for server-side full-duplex handling
- LLM cancel bug is fixed — barge-in followed by new generation will produce tokens correctly
- LatencyTracker P50 computation is validated against known sample data
- Plan 02 (Flutter client) was already completed — it handles the same SPEAKING_AND_LISTENING state on the client side
- Plan 03 can now wire the pipeline to use the new state and enable barge-in

---
*Phase: 14-full-duplex-conversation*
*Completed: 2026-03-04*

## Self-Check: PASSED

- src/ergos/state/events.py: FOUND
- src/ergos/state/machine.py: FOUND
- src/ergos/llm/generator.py: FOUND
- tests/unit/test_full_duplex.py: FOUND
- .planning/phases/14-full-duplex-conversation/14-01-SUMMARY.md: FOUND
- Commit 82786555: FOUND
- Commit ecd6b731: FOUND
