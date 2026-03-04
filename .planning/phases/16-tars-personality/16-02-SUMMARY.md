---
phase: 16-tars-personality
plan: "02"
subsystem: memory
tags: [json-persistence, dataclasses, pathlib, pruning, memory-budget, extraction]

# Dependency graph
requires:
  - phase: 16-tars-personality-01
    provides: TARSPromptBuilder that injects memory entries into system prompts

provides:
  - MemoryEntry dataclass with content, category, timestamp, access_count fields
  - MemoryStore with load/save/prune/get_budget for cross-session JSON persistence
  - parse_extraction_result() for CATEGORY: sentence LLM output parsing
  - format_history_for_extraction() with 4-message minimum threshold
  - EXTRACTION_PROMPT template for session-end memory extraction
  - Comprehensive unit test suite (13 tests) covering all CRUD and extraction paths

affects: [16-tars-personality, 16-03, 16-04, llm-processor, tars-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JSON memory persistence via pathlib + json stdlib following kitchen plugin pattern"
    - "Scored pruning: 0.7*normalized_timestamp + 0.3*normalized_access_count to balance recency vs frequency"
    - "Extraction skip guard: format_history_for_extraction returns None if fewer than 4 messages"
    - "TDD RED/GREEN cycle: tests written and committed before implementation"

key-files:
  created:
    - src/ergos/memory/__init__.py
    - src/ergos/memory/types.py
    - src/ergos/memory/store.py
    - tests/unit/test_tars_memory.py
  modified: []

key-decisions:
  - "MemoryStore scoring formula: 0.7*norm_timestamp + 0.3*norm_access_count — recency-weighted with frequency boost"
  - "prune_respects_access_count test uses same-age entries (timestamp=1000.0 for all) to isolate access_count effect — different-timestamp scenario cannot overcome 0.7 recency weight mathematically"
  - "MEMORY_PATH = ~/.ergos/memory.json (not ~/.ergos/plugins/memory.json) — top-level as core feature, not plugin"
  - "storage_path param accepts full file path (not directory) matching the test fixture pattern tmp_path / 'memory.json'"

patterns-established:
  - "Memory extraction skips sessions with fewer than 4 messages to avoid extracting noise from trivial exchanges"
  - "Valid extraction categories are strictly: preference, fact, moment — lines with unknown categories are silently dropped"
  - "get_budget() mutates access_count in-place on returned entries — caller must save() to persist the updated counts"

requirements-completed: [PERS-03]

# Metrics
duration: 7min
completed: 2026-03-04
---

# Phase 16 Plan 02: Cross-Session Memory Store Summary

**JSON-backed MemoryStore with scored pruning (0.7 recency + 0.3 frequency), CATEGORY: sentence extraction parser, and 13-test TDD suite for PERS-03 cross-session memory**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-04T05:04:32Z
- **Completed:** 2026-03-04T05:11:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Cross-session memory package (src/ergos/memory/) with MemoryEntry dataclass, MemoryStore class, extraction helpers
- Scored pruning drops lowest-value entries: 0.7*normalized_timestamp + 0.3*normalized_access_count keeps up to 100 entries
- Extraction infrastructure: EXTRACTION_PROMPT template, parse_extraction_result() for CATEGORY: sentence format, format_history_for_extraction() with 4-message minimum guard
- 13 unit tests all passing (GREEN), covering load/save roundtrip, prune, prune access_count weighting, budget limiting, budget access_count increment, extraction parsing, NOTHING response, mixed case, short history skip, history formatting

## Task Commits

1. **Task 1: Create test suite (RED phase)** - `9210c302` (test)
2. **Task 2: Implement memory store, types, extraction** - `a7f7692c` (feat)

## Files Created/Modified

- `src/ergos/memory/__init__.py` - Package init re-exporting MemoryEntry and MemoryStore
- `src/ergos/memory/types.py` - MemoryEntry dataclass with auto-timestamp and access_count=0 defaults
- `src/ergos/memory/store.py` - MemoryStore (load/save/get_budget/prune), EXTRACTION_PROMPT, parse_extraction_result, format_history_for_extraction, MEMORY_BUDGET=15, MEMORY_MAX_STORED=100
- `tests/unit/test_tars_memory.py` - 13 tests across TestMemoryEntry, TestMemoryStore, TestMemoryExtraction classes

## Decisions Made

- Scoring formula 0.7/0.3 (recency/frequency): matches plan spec, keeps memory fresh while rewarding frequently accessed entries
- Test for prune_respects_access_count uses same-age entries (all timestamp=1000.0) to isolate the access_count effect cleanly — originally written with different timestamps (0.0 vs 1.0) but 0.3*access_count cannot overcome 0.7*recency penalty mathematically
- MEMORY_PATH is ~/.ergos/memory.json at top level (not under plugins/) since cross-session memory is a core feature
- storage_path parameter accepts a full file path rather than a directory, matching how tests use tmp_path fixtures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test scenario for prune_respects_access_count**
- **Found during:** Task 2 (GREEN phase — running tests after implementation)
- **Issue:** Test created 100 entries at timestamp=1.0 and 1 entry at timestamp=0.0 with access_count=100. With the spec's 0.7/0.3 weighting, the older high-access entry scores 0.3 vs 0.7 for newer entries — mathematically cannot survive
- **Fix:** Changed test to use same timestamp (1000.0) for all 101 entries; isolated access_count effect so high_access entry (access_count=10) scores higher than zero-access entries
- **Files modified:** tests/unit/test_tars_memory.py
- **Verification:** All 13 tests pass
- **Committed in:** a7f7692c (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test scenario)
**Impact on plan:** Test logic corrected to match spec intent. No scope creep. Scoring formula unchanged.

## Issues Encountered

None beyond the test scenario fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MemoryStore ready for integration into Plan 01's TARSPromptBuilder (inject via get_budget())
- Extraction helpers ready for post-session extraction call in the pipeline
- All 13 tests passing — no regressions in test suite

---
*Phase: 16-tars-personality*
*Completed: 2026-03-04*
