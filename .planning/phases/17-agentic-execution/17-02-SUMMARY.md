---
phase: 17-agentic-execution
plan: "02"
subsystem: llm
tags: [agentic, tool-calling, asyncio, concurrent-narration, history-isolation, qwen3]

# Dependency graph
requires:
  - phase: 17-01
    provides: "ToolRegistry, ToolExecutor, built-in tool implementations"
provides:
  - "LLMGenerator.create_chat_completion_sync: blocking wrapper with model_lock for thread safety"
  - "ToolCallProcessor: agentic loop with multi-step chaining, concurrent narration+execution"
  - "History isolation: tool messages ephemeral, only user+assistant in LLM history"
  - "/no_think injection to suppress Qwen3 chain-of-thought in tool-call mode"
affects: [17-03-pipeline-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "create_chat_completion_sync: blocking call with model_lock — run via loop.run_in_executor"
    - "asyncio.gather(speak(narration), executor.execute(...)): concurrent voice + tool (no pause)"
    - "Ephemeral tool messages: local messages list grows during loop, only user+assistant written to _history"
    - "role=tool with tool_call_id: correct format for tool results per llama-cpp-python API"

key-files:
  created:
    - src/ergos/llm/tool_processor.py
    - tests/unit/test_tool_processor.py
  modified:
    - src/ergos/llm/generator.py
    - src/ergos/llm/__init__.py

key-decisions:
  - "create_chat_completion_sync holds model_lock — prevents segfaults from concurrent llama_cpp access"
  - "asyncio.gather for narration+execution — avoids audible pause between user request and tool completion"
  - "'Done.' spoken after asyncio.gather completes — signals tool finished before LLM gets result"
  - "Tool messages are ephemeral: only original user text + final response written to llm_processor._history"
  - "/no_think appended to last user message in messages list (not system prompt) — Qwen3 requirement"

patterns-established:
  - "Agentic loop: build messages -> call LLM -> if tool_calls: execute+narrate -> loop; if stop: return text"
  - "Max steps guard: max_steps=8 default, returns 'Reached step limit' message on overflow"

requirements-completed: [AGENT-02, AGENT-03]

# Metrics
duration: 3min
completed: 2026-03-05
---

# Phase 17 Plan 02: ToolCallProcessor Summary

**ToolCallProcessor with agentic loop: concurrent narration+execution via asyncio.gather, multi-step chaining, history isolation — 15 tests green (47 total across all tool tests)**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-05T06:26:16Z
- **Completed:** 2026-03-05T06:29:22Z
- **Tasks:** 2
- **Files modified:** 2 created, 2 modified

## Accomplishments

- `LLMGenerator.create_chat_completion_sync` wraps `create_chat_completion` with `model_lock` held — prevents segfaults from concurrent llama_cpp model access
- `ToolCallProcessor.process()` implements the full agentic loop: builds messages from history, calls LLM with tools, executes tools concurrently with narration, chains multiple steps, and returns when model gives plain text
- Concurrent narration+execution via `asyncio.gather(speak(narration), executor.execute(...))` — user hears narration while tool runs, no audible gap
- `"Done."` spoken after `asyncio.gather` completes — confirms to user the action finished before LLM processes result
- Multi-step chaining: loop runs up to `max_steps` (default 8), each step extending the local messages list with tool call + result
- History isolation: tool messages stay in the ephemeral local `messages` list; only the original user text and final assistant response are appended to `llm_processor._history`
- `/no_think` appended to the last user message in the messages list (Qwen3 requirement — must be in user turn, not system message)
- Tool result messages use `role="tool"` with `tool_call_id` (per llama-cpp-python API — not `role="user"`)
- `ToolCallProcessor` exported from `ergos.llm.__init__` for pipeline wiring

## Task Commits

Each task was committed atomically:

1. **Task 1: Add create_chat_completion_sync and create ToolCallProcessor** - `903be3e` (feat)
2. **Task 2: Extend ToolCallProcessor test suite with edge cases** - `d3ca092` (feat)

## Files Created/Modified

- `src/ergos/llm/tool_processor.py` - ToolCallProcessor with agentic loop (120 lines)
- `src/ergos/llm/generator.py` - Added `create_chat_completion_sync` with model_lock
- `src/ergos/llm/__init__.py` - Added `ToolCallProcessor` to exports
- `tests/unit/test_tool_processor.py` - 15 unit tests for ToolCallProcessor (TDD)

## Decisions Made

- `create_chat_completion_sync` holds `_model_lock` during the entire LLM call — this is the same pattern as `generate()` and prevents concurrent access segfaults
- `asyncio.gather` is used (not `asyncio.create_task` + `await`) because it ensures both coroutines start and complete before proceeding to `"Done."`
- `/no_think` is appended to the last user message in the `messages` list passed to `create_chat_completion`, not to the `llm_processor._history` — history stores clean user text
- `LLMProcessor._trim_history()` is called after appending user+assistant to history — reuses existing history management logic

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed use of removed asyncio.coroutine in test**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Test `test_done_spoken_after_tool_completes` used `asyncio.coroutine()` which was removed in Python 3.12
- **Fix:** Replaced the complicated executor mock with a simple `AsyncMock()` and checked `speak_calls` list for `"Done."` ordering
- **Files modified:** `tests/unit/test_tool_processor.py`

**2. [Rule 1 - Bug] Fixed IndexError in test accessing mock call args**
- **Found during:** Task 2
- **Issue:** `test_tool_error_string_passed_as_tool_result` tried to access positional args `[0][0]` from a lambda-wrapped call, but `run_in_executor` uses keyword args
- **Fix:** Rewrote test to use a `capture_calls` side_effect function that appends to a `captured` list directly
- **Files modified:** `tests/unit/test_tool_processor.py`

## Next Phase Readiness

- ToolCallProcessor is standalone — ready for Plan 03 (pipeline wiring)
- `ergos.llm.ToolCallProcessor` is importable from `ergos.llm`
- All 47 tool infrastructure tests passing (13 registry + 19 executor/builtins + 15 tool processor)
- AGENT-02 (concurrent narration) and AGENT-03 (multi-step chaining) requirements satisfied

## Self-Check: PASSED

- src/ergos/llm/tool_processor.py: FOUND
- tests/unit/test_tool_processor.py: FOUND
- 17-02-SUMMARY.md: FOUND
- Commit 903be3e (Task 1): FOUND
- Commit d3ca092 (Task 2): FOUND

---
*Phase: 17-agentic-execution*
*Completed: 2026-03-05*
