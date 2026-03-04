---
phase: 16-tars-personality
plan: 02
subsystem: memory
tags: [memory, persistence, json, dataclass, tdd, extraction]

# Dependency graph
requires:
  - phase: 15-expressive-voice
    provides: EmotionMarkupProcessor for TARS persona
provides:
  - MemoryStore with load/save/prune/budget over JSON-backed list[MemoryEntry]
  - MemoryEntry dataclass (content, category, timestamp, access_count)
  - parse_extraction_result() parsing LLM output into MemoryEntry objects
  - format_history_for_extraction() formatting conversation history for LLM extraction
  - EXTRACTION_PROMPT constant for LLM self-extraction
affects: [16-tars-personality, pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [JSON persistence via dataclasses.asdict(), scored pruning formula, fixed budget injection]

key-files:
  created:
    - src/ergos/memory/__init__.py
    - src/ergos/memory/types.py
    - src/ergos/memory/store.py
    - tests/unit/test_tars_memory.py
  modified: []

key-decisions:
  - "MemoryStore scoring formula: 0.7*norm_timestamp + 0.3*norm_access_count — recency-weighted with frequency boost for pruning"
  - "prune_respects_access_count test uses same-age entries to isolate access_count effect — different timestamps cannot overcome 0.7 recency weight"
  - "MEMORY_PATH = ~/.ergos/memory.json at top level (not under plugins/) — cross-session memory is a core feature"

patterns-established:
  - "JSON persistence with dataclasses.asdict() pattern (follows kitchen plugin pattern)"
  - "Fixed budget injection: get_budget() returns top N by recency with access_count side-effect increment"
  - "LLM extraction: EXTRACTION_PROMPT template, parse_extraction_result handles CATEGORY: sentence lines and NOTHING"

requirements-completed: [PERS-02, PERS-03]

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 16 Plan 02: Cross-Session Memory Store Summary

**JSON-backed MemoryStore with scored pruning (0.7*recency + 0.3*access_count), fixed budget injection, LLM extraction helpers, and 13 tests covering CRUD, prune, and extraction parsing**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-04T00:05:00Z
- **Completed:** 2026-03-04T00:08:25Z
- **Tasks:** 2 (TDD: test + feat commits)
- **Files modified:** 4

## Accomplishments

- MemoryEntry dataclass with auto-timestamp and access_count=0 defaults
- MemoryStore.load()/save() JSON round-trip via dataclasses.asdict() with parent dir creation
- MemoryStore.prune() using 0.7*norm_timestamp + 0.3*norm_access_count scoring formula
- MemoryStore.get_budget() returning top N by recency with access_count increment side-effect
- parse_extraction_result() parsing CATEGORY: sentence lines, lowercasing categories, returning [] for NOTHING
- format_history_for_extraction() skipping short history (<4 messages), capping at 20 messages
- EXTRACTION_PROMPT constant for LLM self-extraction at session end
- 13 tests all passing: TestMemoryEntry (1), TestMemoryStore (7), TestMemoryExtraction (5)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Add failing tests for MemoryEntry and MemoryStore** - `9210c30` (test)
2. **Task 2: GREEN - Implement MemoryStore and extraction helpers** - `a7f7692` (feat)

**Plan metadata:** `bd4574b` (docs: complete cross-session memory store plan)

_Note: TDD tasks have two commits (test RED → feat GREEN)_

## Files Created/Modified

- `src/ergos/memory/__init__.py` - Package init exporting MemoryStore and MemoryEntry
- `src/ergos/memory/types.py` - MemoryEntry dataclass with content, category, timestamp, access_count
- `src/ergos/memory/store.py` - MemoryStore class, EXTRACTION_PROMPT, parse_extraction_result, format_history_for_extraction
- `tests/unit/test_tars_memory.py` - 13 unit tests for all memory module components (213 lines)

## Decisions Made

- **Scoring formula lock**: 0.7*norm_timestamp + 0.3*norm_access_count for pruning — recency-dominant with frequency boost. Prevents cache pollution by infrequently-accessed old entries.
- **Test isolation for access_count**: prune_respects_access_count test uses same-age entries (same timestamp) so only access_count differs — different timestamps would hide the access_count effect due to 0.7 recency weight.
- **Storage location**: ~/.ergos/memory.json at top level (not under plugins/) — cross-session memory is a core TARS feature, not a plugin.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Memory module complete and fully tested — ready for pipeline integration in plan 16-03
- MemoryStore.get_budget() provides the injection API consumed by persona builder
- EXTRACTION_PROMPT and parse_extraction_result() provide the end-of-session extraction pipeline

---
*Phase: 16-tars-personality*
*Completed: 2026-03-04*
