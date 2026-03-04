---
phase: 16-tars-personality
plan: 01
subsystem: persona
tags: [tars, personality, sarcasm, prompt-builder, pydantic, pytest, tdd]

# Dependency graph
requires:
  - phase: 15-expressive-voice
    provides: EmotionMarkupProcessor with *sighs*/*chuckles*/ellipsis support used in TARS persona hints
provides:
  - TARSPromptBuilder class with section-based sarcasm blending (0/50/100 tiers)
  - try_sarcasm_command() voice command parser returning clamped 0-100 int
  - get_time_context() natural-language time period helper (morning/afternoon/evening/night)
  - tars.yaml curated TARS persona file with is_tars_persona: true
  - Extended Persona dataclass with sarcasm_level and is_tars_persona fields
  - DEFAULT_PERSONA updated to TARS identity in loader.py
  - PersonaConfig extended with sarcasm_level Field(ge=0, le=100)
  - 17-test unit suite covering all TARS personality behaviors
affects:
  - 16-02 (sarcasm command wiring into pipeline)
  - 16-03 (pipeline integration — TARSPromptBuilder will replace system_prompt)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Section-based sarcasm blending: NEUTRAL (0-20) / mid-range (21-79) / MAX_SARCASM (80-100) tiers"
    - "Regex lookbehind (?<!\\w) for capturing signed integers in voice commands"
    - "TDD RED/GREEN pattern: test file committed before implementation"

key-files:
  created:
    - src/ergos/persona/builder.py
    - src/ergos/persona/tars.yaml
    - tests/unit/test_tars_personality.py
  modified:
    - src/ergos/persona/types.py
    - src/ergos/persona/loader.py
    - src/ergos/config.py

key-decisions:
  - "Section-based blending uses two fixed template tiers (NEUTRAL / MAX_SARCASM) rather than interpolation — cleaner output, easier to tune"
  - "Mid-range (21-79) humor frequency uses 'some' (21-49) vs 'most' (50-79) as frequency modifiers"
  - "Regex uses (?<!\\w)(-?\\d{1,3})(?!\\d) lookbehind to capture negative sarcasm values like -10%"
  - "DEFAULT_PERSONA changed from Ergos to TARS — TARS is the identity for v2"
  - "PersonaConfig.name default changed from 'Ergos' to 'TARS' for consistency"

patterns-established:
  - "Pattern 1: Section dict template blending — separate NEUTRAL/MAX dicts, mid-range interpolates frequency words only"
  - "Pattern 2: Voice command parsing via try_X_command() returning Optional[int] — None means not a command"
  - "Pattern 3: Builder.build() always returns complete, self-contained prompt string — no partial composition at call site"

requirements-completed: [PERS-01]

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 16 Plan 01: TARS Personality Infrastructure Summary

**TARSPromptBuilder with section-based sarcasm blending (0/50/100), voice command parser, time context helper, tars.yaml persona, and 17 passing unit tests**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-04T04:44:22Z
- **Completed:** 2026-03-04T04:47:03Z
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files modified:** 6

## Accomplishments

- TARSPromptBuilder builds distinct prompts at sarcasm levels 0/50/100 using section-based blending from two curated template tiers
- Voice command parser try_sarcasm_command() handles "set sarcasm to N%" patterns with clamping and negative-value edge cases
- get_time_context() returns correct natural-language period for all 5 hour ranges (night/morning/afternoon/evening/late night)
- DEFAULT_PERSONA updated to TARS identity; PersonaConfig extended with validated sarcasm_level field

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Add failing tests for TARS personality infrastructure** - `fb41467` (test)
2. **Task 2 (TDD GREEN): Implement TARS persona infrastructure** - `61fc6b4` (feat)

**Plan metadata:** `b3a1077` (docs: complete plan)

_Note: TDD tasks have two commits — test commit (RED) then implementation commit (GREEN)_

## Files Created/Modified

- `src/ergos/persona/builder.py` - TARSPromptBuilder, try_sarcasm_command(), get_time_context()
- `src/ergos/persona/tars.yaml` - Curated TARS persona YAML (is_tars_persona: true, sarcasm_level: 75)
- `src/ergos/persona/types.py` - Extended Persona dataclass with sarcasm_level and is_tars_persona fields
- `src/ergos/persona/loader.py` - DEFAULT_PERSONA updated to TARS; load_persona reads new fields
- `src/ergos/config.py` - PersonaConfig.sarcasm_level = Field(default=75, ge=0, le=100); name default -> "TARS"
- `tests/unit/test_tars_personality.py` - 17 tests across 5 test classes (RED then GREEN)

## Decisions Made

- Section-based blending uses two fixed template tiers (NEUTRAL / MAX_SARCASM) rather than linear interpolation — produces cleaner, tunable prompt output
- Mid-range (21-79) humor frequency uses "some" vs "most" as frequency modifiers, threshold at 50
- Regex uses `(?<!\w)(-?\d{1,3})(?!\d)` lookbehind to correctly capture negative sarcasm values such as "-10%"
- DEFAULT_PERSONA and PersonaConfig.name both changed from "Ergos" to "TARS" — TARS is the v2 identity

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed regex pattern failing to capture negative sarcasm values**
- **Found during:** Task 2 (GREEN phase — running full test suite)
- **Issue:** Original regex `\b(\d{1,3})\b` matched "10" from "-10" because `\b` anchors on word boundaries, not sign characters; updated regex with `.{0,30}` suffix was greedy and consumed number digits
- **Fix:** Rewrote regex pattern to use `(?<!\w)(-?\d{1,3})(?!\d)` with negative lookbehind, capturing optional minus sign before digits
- **Files modified:** src/ergos/persona/builder.py
- **Verification:** All 3 sarcasm command tests pass (80%, 150%->100, -10%->0)
- **Committed in:** `61fc6b4` (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Necessary for correctness of clamped negative sarcasm values. No scope creep.

## Issues Encountered

None beyond the regex fix documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All TARS personality infrastructure is ready for Plan 02/03 pipeline wiring
- TARSPromptBuilder.build() interface is stable: (name, sarcasm_level, memories, time_context) -> str
- try_sarcasm_command() ready to be wired into the voice command handler in Plan 02
- DEFAULT_PERSONA is TARS — no config change needed for default behavior

---
*Phase: 16-tars-personality*
*Completed: 2026-03-04*
