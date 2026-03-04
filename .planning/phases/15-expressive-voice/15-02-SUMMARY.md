---
phase: 15-expressive-voice
plan: 02
subsystem: tts
tags: [tts, orpheus, emotion-markup, expressive-voice, sarcasm, prosody]
dependency_graph:
  requires:
    - phase: 15-01
      provides: OrpheusSynthesizer, TTSConfig.engine=orpheus, pipeline-orpheus-wiring
  provides:
    - EmotionMarkupProcessor with EMOTION_MAP hint conversion
    - Sarcasm ellipsis -> comma pause injection
    - TTSProcessor.engine field for markup activation
    - Updated LLM system prompt with emotion hint guidance
    - pipeline.py engine kwarg passthrough to TTSProcessor
  affects: [src/ergos/tts, src/ergos/llm, src/ergos/pipeline.py]
tech-stack:
  added: []
  patterns: [TDD-red-green, regex-hint-conversion, engine-passthrough-guard]
key-files:
  created:
    - src/ergos/tts/emotion_markup.py
    - tests/unit/test_emotion_markup.py
  modified:
    - src/ergos/tts/__init__.py
    - src/ergos/tts/processor.py
    - src/ergos/llm/processor.py
    - src/ergos/pipeline.py
key-decisions:
  - "EmotionMarkupProcessor uses regex r'\\*(\\w+)\\*' for hint matching — case-insensitive via .lower() on matched word"
  - "Unknown hints stripped entirely (removed from output, not passed through) to avoid TTS speaking asterisk words"
  - "Ellipsis (...) converted to ', ' (comma+space) for natural Orpheus pause cadence — trailing comma cleaned up"
  - "engine field added to TTSProcessor dataclass (default 'kokoro') — single field controls emotion markup activation"
  - "Emotion markup called in _synthesize_and_stream before synthesis — text transformation is transparent to callers"
  - "LLM system prompt updated with *laughs*/*sighs*/*chuckles* examples and ellipsis guidance"

patterns-established:
  - "Engine passthrough pattern: if engine != 'orpheus': return text — zero-cost for Kokoro/CSM users"
  - "Inline _emotion_markup field on TTSProcessor — no dependency injection needed, EmotionMarkupProcessor is stateless"

requirements-completed: [VOICE-04]

duration: 12min
completed: "2026-03-04"
---

# Phase 15 Plan 02: Emotion Markup Preprocessing Summary

**EmotionMarkupProcessor converts LLM *laughs*/*sighs* hints to Orpheus emotion tags, injects ellipsis pause timing for sarcasm, with engine passthrough for Kokoro/CSM.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-04T03:10:00Z
- **Completed:** 2026-03-04T03:22:00Z
- **Tasks:** 1 completed (Task 2 is a human-verify checkpoint)
- **Files modified:** 6

## Accomplishments

- Created EmotionMarkupProcessor with 11-entry EMOTION_MAP (laughs/laughing, chuckles/chuckling, sighs/sighing, gasps, coughs, groans, yawns, sniffles)
- Implemented sarcasm pause injection: `...` -> `, ` (comma pause) for dry delivery timing
- Added `engine` field to TTSProcessor, wired EmotionMarkupProcessor in `_synthesize_and_stream`
- Updated LLM system prompt with emotion hint guidance and ellipsis/sarcasm examples
- All 39 new emotion markup tests pass; 193 total unit tests pass (no regressions)

## Task Commits

1. **TDD RED: Failing tests for EmotionMarkupProcessor** - `032af26a` (test)
2. **Task 1 GREEN: EmotionMarkupProcessor + pipeline wiring** - `420b6f63` (feat)

## Files Created/Modified

- `src/ergos/tts/emotion_markup.py` — EmotionMarkupProcessor class (90 lines), EMOTION_MAP, _convert_emotion_hints, _inject_sarcasm_pauses
- `tests/unit/test_emotion_markup.py` — 39 tests across 7 test classes (349 lines)
- `src/ergos/tts/__init__.py` — Added EmotionMarkupProcessor export
- `src/ergos/tts/processor.py` — Added engine field + _emotion_markup field; call process() in _synthesize_and_stream
- `src/ergos/llm/processor.py` — Updated default system_prompt with emotion hints and ellipsis guidance
- `src/ergos/pipeline.py` — Added engine=config.tts.engine kwarg to TTSProcessor constructor

## Decisions Made

- Used regex `r'\*(\w+)\*'` with `.lower()` for case-insensitive hint matching — simple, reliable, no external deps
- Unknown hints (e.g. `*dances*`) stripped entirely — avoids TTS literally speaking the word "dances" in context
- Ellipsis → comma-space conversion for pauses — natural Orpheus prosody, no special pause syntax needed
- `engine` field on TTSProcessor defaults to `"kokoro"` — backward compatible, zero change in behavior for existing deployments
- Emotion markup called in `_synthesize_and_stream` not `receive_token` — keeps transformation close to synthesis, after sentence boundary detection

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- EmotionMarkupProcessor is complete and wired
- Task 2 (human-verify checkpoint) requires: running Orpheus TTS and listening for perceptible expressiveness vs Kokoro flat output
- After human verification, phase 15 is complete and VOICE-04 requirement is fulfilled

---
*Phase: 15-expressive-voice*
*Completed: 2026-03-04*
