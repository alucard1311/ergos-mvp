---
phase: 17-agentic-execution
plan: "01"
subsystem: tools
tags: [pyyaml, asyncio, tool-calling, agentic, shell-allowlist, registry]

# Dependency graph
requires:
  - phase: 16-tars-personality
    provides: "Core pipeline architecture, LLM generator with model lock pattern"
provides:
  - "ToolRegistry: YAML loader -> ChatCompletionTool dicts with get_tools(), get_impl_map(), get_tool_config()"
  - "ToolExecutor: async dispatcher from tool name to built-in implementation, injects allowed_prefixes"
  - "file_read builtin: reads files with ~ expansion, 4096-char truncation, error strings"
  - "shell_run builtin: command allowlist enforcement via allowed_prefixes, 30s max timeout, async subprocess"
  - "file_list builtin: glob pattern support, error strings for missing dirs"
  - "tools/default.yaml: conservative allowlist (ls, cat, head, tail, wc, find, grep, echo, etc.)"
affects: [17-02-tool-call-processor, 17-03-pipeline-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "YAML tool registry: tools/*.yaml -> ChatCompletionTool list (no code changes for new tools)"
    - "_config pattern: extra YAML fields stored in _config; stripped from LLM-facing get_tools() output"
    - "allowed_prefixes=None means allow all (backwards-compatible); [] means reject all"
    - "TDD: RED (failing tests) then GREEN (implementation) per task"

key-files:
  created:
    - src/ergos/tools/__init__.py
    - src/ergos/tools/registry.py
    - src/ergos/tools/executor.py
    - src/ergos/tools/builtins.py
    - tests/unit/test_tool_registry.py
    - tests/unit/test_tool_executor.py
    - tools/default.yaml
  modified: []

key-decisions:
  - "allowed_prefixes=None allows all commands for backwards-compatible user-defined tools; list (even empty) enforces allowlist"
  - "_config stores extra YAML fields generically — any tool can carry extra config without registry code changes"
  - "file_read/shell_run/file_list all return error strings (never raise) — callers never need try/except"
  - "shell_run uses asyncio.create_subprocess_exec with asyncio.wait_for for non-blocking timeout"

patterns-established:
  - "Tool registry pattern: registry.get_tools() -> LLM; registry.get_impl_map() -> executor; registry.get_tool_config(name) -> per-tool config"
  - "Builtin impl pattern: async def tool_name(**kwargs) -> str (always returns string, never raises)"

requirements-completed: [AGENT-01, AGENT-04]

# Metrics
duration: 4min
completed: 2026-03-05
---

# Phase 17 Plan 01: Tool Registry and Executor Summary

**YAML-based tool registry with ToolRegistry/ToolExecutor/builtins (file_read, shell_run with configurable allowlist, file_list) — 32 tests green**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-05T06:18:33Z
- **Completed:** 2026-03-05T06:22:20Z
- **Tasks:** 2
- **Files modified:** 7 created

## Accomplishments
- ToolRegistry scans `tools_dir/*.yaml`, validates entries, produces clean ChatCompletionTool dicts for `create_chat_completion(tools=...)`, with per-tool config via `get_tool_config()`
- ToolExecutor dispatches by name to built-in implementations; injects `allowed_prefixes` from registry config into `shell_run` automatically
- shell_run enforces `allowed_prefixes` before execution — `rm`, `sudo`, and other dangerous commands rejected; `None` allows all for backwards compatibility
- Default YAML (`tools/default.yaml`) ships with conservative allowlist ready to copy to `~/.ergos/tools/`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tool registry with YAML loading and validation** - `07df038` (feat)
2. **Task 2: Create tool executor and built-in implementations with shell_run allowlist** - `b12a3d0` (feat)

## Files Created/Modified
- `src/ergos/tools/__init__.py` - Module exports: ToolRegistry, ToolExecutor
- `src/ergos/tools/registry.py` - YAML registry loader with load/reload/get_tools/get_impl_map/get_tool_config
- `src/ergos/tools/executor.py` - Async dispatcher from tool name to built-in implementation
- `src/ergos/tools/builtins.py` - Built-in implementations: file_read, shell_run (allowlist), file_list
- `tests/unit/test_tool_registry.py` - 13 unit tests for registry (TDD)
- `tests/unit/test_tool_executor.py` - 19 unit tests for executor and builtins (TDD)
- `tools/default.yaml` - Default tool registry with conservative shell allowlist

## Decisions Made
- `allowed_prefixes=None` (field absent from YAML) allows all commands for user-defined tools; providing a list (even empty `[]`) enforces the allowlist — clean backwards-compatible design
- Extra YAML fields stored generically in `_config` dict, stripped from `get_tools()` output — LLM never sees `_impl` or `_config` keys
- All built-in functions return error strings (never raise), simplifying error handling in the agentic loop
- `asyncio.create_subprocess_exec` + `asyncio.wait_for` for non-blocking subprocess with hard timeout cap at 30s

## Deviations from Plan

None - plan executed exactly as written. TDD pattern followed: failing tests written first, then implementation.

## Issues Encountered
None.

## User Setup Required
To enable agentic mode, copy the default tool registry to the user config location:
```bash
mkdir -p ~/.ergos/tools
cp tools/default.yaml ~/.ergos/tools/default.yaml
```

## Next Phase Readiness
- Tool infrastructure complete; ready for Plan 02 (ToolCallProcessor with agentic loop)
- ToolRegistry and ToolExecutor are standalone — no dependencies on LLM or pipeline yet
- 32 tests passing (13 registry + 19 executor/builtins)
- AGENT-01 and AGENT-04 requirements satisfied by this plan

---
*Phase: 17-agentic-execution*
*Completed: 2026-03-05*
