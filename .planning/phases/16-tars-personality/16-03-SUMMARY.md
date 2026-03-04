---
phase: 16-tars-personality
plan: "03"
subsystem: pipeline
tags: [tars, personality, memory, sarcasm, pipeline-wiring, connection-manager, integration]

# Dependency graph
requires:
  - phase: 16-tars-personality-01
    provides: TARSPromptBuilder, try_sarcasm_command, get_time_context, Persona.is_tars_persona
  - phase: 16-tars-personality-02
    provides: MemoryStore, MemoryEntry, EXTRACTION_PROMPT, parse_extraction_result, format_history_for_extraction

provides:
  - LLMProcessor.update_system_prompt() method for runtime system prompt changes
  - Pipeline uses TARSPromptBuilder at startup when persona.is_tars_persona is True
  - Sarcasm voice command intercept before plugins and LLM; TARS-style confirmation spoken via TTS
  - Memories loaded at pipeline startup and injected into system prompt via get_budget()
  - Memory extraction on peer disconnect using generator.generate() in run_in_executor
  - ConnectionManager.set_disconnect_callback() for peer disconnect event hook

affects: [16-04, tars-end-to-end, pipeline-integration-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sarcasm command intercept: try_sarcasm_command() checked BEFORE plugin routing — returns early to avoid LLM processing"
    - "Memory extraction at disconnect: generator.generate() in asyncio.run_in_executor — never blocks event loop, never pollutes history"
    - "Disconnect callback pattern: ConnectionManager.set_disconnect_callback() registers async callback for peer lifecycle events"
    - "Mutable closure via list wrapper: current_sarcasm_level = [N] allows mutation by nested async functions"

key-files:
  created: []
  modified:
    - src/ergos/llm/processor.py
    - src/ergos/pipeline.py
    - src/ergos/transport/connection.py

key-decisions:
  - "Memory extraction uses generator.generate() directly (not llm_processor) to avoid polluting conversation history"
  - "Disconnect callback added to ConnectionManager via set_disconnect_callback() — clean hook without modifying signaling code"
  - "Sarcasm command intercept placed before plugin routing (first gate) to prevent commands reaching LLM"
  - "current_sarcasm_level stored as [int] list for mutable closure access in nested async functions"

patterns-established:
  - "Pattern 1: Sarcasm intercept guard — if prompt_builder is not None: check try_sarcasm_command() before any routing"
  - "Pattern 2: Memory extraction safety — format_history_for_extraction returns None for < 4 messages; extraction wrapped in try/except to never lose existing memories"
  - "Pattern 3: ConnectionManager disconnect hook — set_disconnect_callback() for session-end cleanup tasks"

requirements-completed: [PERS-01, PERS-02, PERS-03]

# Metrics
duration: 8min
completed: 2026-03-04
---

# Phase 16 Plan 03: Pipeline Integration Summary

**TARS personality fully wired into pipeline: TARSPromptBuilder at startup, sarcasm command intercept, memories injected at session start, extraction on disconnect**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-04T05:15:00Z
- **Completed:** 2026-03-04T05:23:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- LLMProcessor.update_system_prompt() added — enables runtime sarcasm level changes without recreating the processor
- Pipeline builds system prompt via TARSPromptBuilder when persona.is_tars_persona is True, with memories and time context injected at startup
- Sarcasm voice commands ("set sarcasm to N%") intercepted before plugins and LLM, rebuild prompt, and speak a TARS-style confirmation without going through LLM
- Memory extraction runs on WebRTC peer disconnect using generator.generate() directly in run_in_executor — preserves conversation history integrity and does not block the event loop
- ConnectionManager.set_disconnect_callback() provides a clean hook for session-end lifecycle events

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dynamic system_prompt update to LLMProcessor** - `a013845c` (feat)
2. **Task 2: Wire TARS personality into pipeline** - `196cc536` (feat)

## Files Created/Modified

- `src/ergos/llm/processor.py` - Added update_system_prompt(new_prompt) method with info logging
- `src/ergos/pipeline.py` - Import TARSPromptBuilder/MemoryStore/helpers; TARS prompt builder at startup; sarcasm command intercept in on_transcription_with_plugins; memory extraction on disconnect
- `src/ergos/transport/connection.py` - Added set_disconnect_callback() and invocation in on_connection_state_change (failed/closed states)

## Decisions Made

- Memory extraction uses `generator.generate()` directly (not `llm_processor.process_transcription()`) to avoid adding extraction output to conversation history and avoid confusing LLM context with meta-analysis
- Disconnect callback added to `ConnectionManager` via `set_disconnect_callback()` rather than modifying `create_signaling_app()` — preserves separation of concerns; signaling layer doesn't need to know about memory
- Sarcasm intercept is the FIRST gate inside `on_transcription_with_plugins()` — returns early so command never reaches plugins or LLM
- `current_sarcasm_level` stored as `[int]` list (mutable closure pattern) so nested async callbacks can update it in-place
- Extraction wrapped in broad `except Exception` to guarantee existing memories are never lost on extraction failure

## Deviations from Plan

None - plan executed exactly as written. All four integration points implemented as specified.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TARS personality is fully active for all conversations using the default TARS persona or any persona with is_tars_persona=True
- Memory extraction will begin populating ~/.ergos/memory.json after first real conversation session
- All 223 unit tests passing, no regressions

---
*Phase: 16-tars-personality*
*Completed: 2026-03-04*
