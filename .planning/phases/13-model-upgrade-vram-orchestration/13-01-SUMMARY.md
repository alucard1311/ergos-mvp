---
phase: 13-model-upgrade-vram-orchestration
plan: "01"
subsystem: core-infrastructure
tags: [vram, orchestration, stt, config, tdd]
dependency_graph:
  requires: []
  provides: [vram-monitor, stt-small-en-int8, config-v2-schema]
  affects: [pipeline, all-v2-models]
tech_stack:
  added: [torch.cuda.mem_get_info]
  patterns: [dataclass, pydantic-defaults, tdd-red-green]
key_files:
  created:
    - src/ergos/core/__init__.py
    - src/ergos/core/vram.py
    - tests/unit/test_vram.py
    - tests/unit/test_config_v2.py
  modified:
    - src/ergos/hardware.py
    - src/ergos/config.py
    - src/ergos/pipeline.py
    - config.yaml
decisions:
  - "VRAMMonitor uses torch.cuda.mem_get_info() (free, total) — not pynvml — for zero extra deps"
  - "Module-level torch import with None fallback avoids ImportError on CPU-only machines"
  - "LLMConfig defaults context_length=4096 in code but config.yaml was already 1024 — yaml upgraded to 4096"
metrics:
  duration_minutes: 4
  tasks_completed: 2
  tests_written: 38
  files_created: 4
  files_modified: 4
  completed_date: "2026-03-03"
---

# Phase 13 Plan 01: VRAM Monitor and Config v2 Summary

**One-liner:** VRAMMonitor with GPU memory querying + STT upgrade to faster-whisper small.en INT8 with backward-compatible v2 config schema.

## What Was Built

### Task 1: VRAM Monitor Module (TDD)

Created `src/ergos/core/vram.py` with three public types:

- **`VRAMSnapshot`** — dataclass capturing `total_mb`, `used_mb`, `free_mb`, `utilization_pct` from a point-in-time GPU query
- **`ModelVRAMProfile`** — dataclass tracking a model's name, estimated VRAM in MB, and category (stt/llm/tts/vision)
- **`VRAMMonitor`** — class for tracking GPU memory across all v2 models:
  - `snapshot()` — queries `torch.cuda.mem_get_info()`, returns zero snapshot if CUDA unavailable
  - `register_model(name, estimated_mb, category)` — adds to internal registry
  - `unregister_model(name)` — removes from registry (silent if not found)
  - `budget_check(headroom_mb=4000.0)` — returns `(fits, total_estimated_mb, available_mb)`
  - `report()` — returns structured dict for diagnostics and logging

Added `get_vram_usage() -> tuple[float, float]` to `src/ergos/hardware.py` returning `(used_mb, total_mb)` using the same torch.cuda approach.

GPU detection at module level: `torch` imported at top level with `None` fallback so CPU-only environments don't error.

On real hardware at execution time: GPU detected as 7805MB total, 253MB used (RTX present and working).

### Task 2: Config Schema v2 and STT Upgrade (TDD)

Updated `src/ergos/config.py`:
- `STTConfig.compute_type: str = "auto"` — faster-whisper compute precision
- `LLMConfig.chat_format: str = "chatml"` — Qwen3 chat template format
- `LLMConfig.n_gpu_layers: int = -1` — full GPU layer offload for llama.cpp

Updated `config.yaml` defaults:
- `stt.model: small.en` (was `tiny.en`)
- `stt.compute_type: int8` (new, ~1GB VRAM for small.en)
- `llm.context_length: 4096` (was `1024`)
- `llm.chat_format: chatml` (new)
- `llm.n_gpu_layers: -1` (new)

Updated `src/ergos/pipeline.py` line ~132 to pass `compute_type=config.stt.compute_type` to `WhisperTranscriber`.

## Test Results

| Test Suite | Tests | Result |
|---|---|---|
| tests/unit/test_vram.py | 21 | PASSED |
| tests/unit/test_config_v2.py | 17 | PASSED |
| tests/test_integration.py | 17 | PASSED (no regressions) |
| **Total** | **55** | **All passed** |

## Commits

| Hash | Message |
|---|---|
| `4117ecf5` | test(13-01): add failing tests for VRAM monitoring module |
| `577f9d65` | feat(13-01): implement VRAMMonitor module and GPU memory utilities |
| `28ffc80f` | test(13-01): add failing tests for config v2 schema |
| `84ca2e48` | feat(13-01): config schema v2 and STT model upgrade to small.en INT8 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_get_vram_usage_no_torch scoping error**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test imported `get_vram_usage` inside a block with stale reference, causing `NameError`
- **Fix:** Moved import to top of test method, removed stale reference
- **Files modified:** tests/unit/test_vram.py
- **Commit:** 577f9d65

No other deviations — plan executed as written.

## Verification

```
# Config loading
STT: small.en (int8)
LLM: chat_format=chatml, n_gpu_layers=-1

# VRAM module
Budget: 16384.0MB
GPU: 7805.5625MB total, 253.3125MB used
```

## Self-Check: PASSED

All created files exist on disk. All 4 task commits verified in git log.
