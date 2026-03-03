---
phase: 13-model-upgrade-vram-orchestration
plan: "02"
subsystem: llm
tags: [qwen3, chatml, vram, llama-cpp, pipeline, monitoring]

requires:
  - phase: 13-model-upgrade-vram-orchestration/13-01
    provides: VRAMMonitor class, updated LLMConfig with chat_format/n_gpu_layers, STTConfig with compute_type

provides:
  - LLMGenerator with configurable chat_format parameter (chatml/phi3)
  - LLMProcessor with multi-format prompt builder (_build_chatml_prompt, _build_phi3_prompt)
  - _get_stop_sequences() returning format-appropriate stop tokens per format
  - Pipeline.vram_monitor field with VRAMMonitor integrated into pipeline dataclass
  - create_pipeline registers STT/LLM/TTS models with VRAM estimates and runs budget check
  - preload_models logs VRAM budget before loading and snapshot after
  - Server.start logs VRAM report with per-model breakdown
  - config.yaml model_path points to Qwen3-8B-Q4_K_M.gguf

affects:
  - 17-agentic-execution (uses Qwen3 tool-calling format, depends on chatml)
  - 18-vision-integration (registers additional vision model in pipeline)
  - 19-tts-upgrade (registers Orpheus model in pipeline)

tech-stack:
  added: []
  patterns:
    - "Multi-format prompt builder: _build_chatml_prompt / _build_phi3_prompt dispatch on self.chat_format"
    - "VRAM registration at pipeline creation: register all models before loading"
    - "Budget check before preload: log warning if models exceed available budget"
    - "Stop sequence injection: _get_stop_sequences() called per-request, not hardcoded"

key-files:
  created:
    - tests/unit/test_llm_qwen3.py
    - tests/unit/test_vram_integration.py
  modified:
    - src/ergos/llm/generator.py
    - src/ergos/llm/processor.py
    - src/ergos/pipeline.py
    - src/ergos/server.py
    - src/ergos/core/vram.py
    - config.yaml

key-decisions:
  - "chatml is default chat_format for both LLMGenerator and LLMProcessor — enables Qwen3 out of the box"
  - "phi3 format preserved as backward-compatible fallback for users on older models"
  - "VRAM registration hardcoded in create_pipeline with known estimates (STT=1000MB, LLM=5200MB, TTS=500MB)"
  - "budget_check uses sum(iterable, 0.0) to guarantee float return type even when no models registered"

patterns-established:
  - "Chat format dispatch: if self.chat_format == 'chatml' else phi3 — extend for new formats by adding elif"
  - "VRAM registration: add register_model() call in create_pipeline() for each new model added in later phases"
  - "Pipeline dataclass: add fields at end of dataclass definition to avoid breaking existing positional construction"

requirements-completed:
  - MODEL-01
  - MODEL-03

duration: 5min
completed: 2026-03-03
---

# Phase 13 Plan 02: Model Upgrade and VRAM Integration Summary

**Qwen3 chatml prompt format replacing Phi-3 in LLMGenerator/LLMProcessor, with VRAMMonitor wired into Pipeline registering all three v2 models (STT 1GB, LLM 5.2GB, TTS 0.5GB = 6.7GB total, fits within 12.4GB budget)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-03T21:35:54Z
- **Completed:** 2026-03-03T21:40:33Z
- **Tasks:** 3 (2 auto + 1 checkpoint auto-approved)
- **Files modified:** 6 + 2 test files created

## Accomplishments

- LLMGenerator now accepts `chat_format` parameter with `chatml` as default, enabling Qwen3-8B out of the box
- LLMProcessor builds chatml-format prompts (`<|im_start|>`/`<|im_end|>`) and Phi-3 prompts preserved as fallback
- Pipeline registers all three v2 models with VRAMMonitor at creation time; budget check confirms 6.7GB fits within 12.4GB available
- Server startup logs VRAM report showing per-model estimates before and after preload
- config.yaml model_path updated to `~/.ergos/models/Qwen3-8B-Q4_K_M.gguf`
- 66 unit tests pass across all Phase 13 test files

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Qwen3 chatml test** - `ec8bfbf0` (test)
2. **Task 1 GREEN: Qwen3 chatml implementation** - `296f74b9` (feat)
3. **Task 2 RED: VRAM integration tests** - `1485795c` (test)
4. **Task 2 GREEN: VRAM integration implementation** - `318683a6` (feat)

*Note: Task 3 (checkpoint:human-verify) auto-approved per skip_checkpoints=true config.*

## Files Created/Modified

- `src/ergos/llm/generator.py` - Added `chat_format` parameter and property
- `src/ergos/llm/processor.py` - Added `chat_format` field, `_build_chatml_prompt()`, `_build_phi3_prompt()`, `_get_stop_sequences()`
- `src/ergos/pipeline.py` - Added VRAMMonitor import, `vram_monitor` field, model registration in `create_pipeline()`, VRAM logging in `preload_models()`
- `src/ergos/server.py` - Added VRAM report logging after `preload_models()`
- `src/ergos/core/vram.py` - Fixed `budget_check()` and `report()` to return float for empty model registry
- `config.yaml` - Updated `llm.model_path` to Qwen3-8B-Q4_K_M.gguf
- `tests/unit/test_llm_qwen3.py` - 17 tests for chatml/phi3 format switching
- `tests/unit/test_vram_integration.py` - 11 tests for pipeline VRAM integration

## Decisions Made

- chatml is the default format for both LLMGenerator and LLMProcessor so the v2 Qwen3 model works without any config change
- Phi-3 format preserved as backward-compatible fallback accessible via `chat_format="phi3"`
- VRAM estimates hardcoded at pipeline creation time (not dynamically queried from model files) — simpler, fast, and estimates match known model sizes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed budget_check() and report() returning int 0 for empty registry**
- **Found during:** Task 2 (VRAM integration tests)
- **Issue:** Python's `sum([])` returns `0` (int), but tests and type annotations expected `float`. The `total_estimated` value in both `budget_check()` and `report()` would be `int` when no models registered.
- **Fix:** Changed to `sum((p.estimated_mb for p in self._models.values()), 0.0)` with explicit float start value
- **Files modified:** `src/ergos/core/vram.py`
- **Verification:** `test_budget_check_returns_tuple` now passes; manual check confirms `type(total)` is `float`
- **Committed in:** `318683a6` (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Float type correctness fix; no scope creep.

## Issues Encountered

- ROS Jazzy pytest plugins interfered with the system Python3 test runner — resolved by using project venv (`.venv/bin/python3`) with `--override-ini="addopts="` to avoid plugin conflicts.

## User Setup Required

Manual setup required before server will run with real models:

1. Download Qwen3-8B-Q4_K_M.gguf (~5GB) to `~/.ergos/models/`
   - Source: https://huggingface.co/Qwen/Qwen3-8B-GGUF
2. Faster-whisper small.en model auto-downloads on first use
3. Verify: `ls -la ~/.ergos/models/Qwen3-8B-Q4_K_M.gguf`
4. Test server startup: `ergos start -v` and look for "VRAM budget OK" in logs

## Next Phase Readiness

- Qwen3 chatml format ready for native tool-calling (Phase 17 prerequisite)
- VRAM monitor integrated — Phase 18 (Vision) only needs to add `vram_monitor.register_model("moondream-2b-int8", 1500.0, "vision")` in `create_pipeline()`
- All Phase 13 unit tests pass (66 tests across 4 test files)
- Human hardware verification (Task 3) required before deploying to production

---
*Phase: 13-model-upgrade-vram-orchestration*
*Completed: 2026-03-03*

## Self-Check: PASSED

All 9 files verified present. All 4 task commits verified in git log.

| Item | Status |
|------|--------|
| src/ergos/llm/generator.py | FOUND |
| src/ergos/llm/processor.py | FOUND |
| src/ergos/pipeline.py | FOUND |
| src/ergos/server.py | FOUND |
| src/ergos/core/vram.py | FOUND |
| config.yaml | FOUND |
| tests/unit/test_llm_qwen3.py | FOUND |
| tests/unit/test_vram_integration.py | FOUND |
| 13-02-SUMMARY.md | FOUND |
| Commit ec8bfbf0 (test RED Task 1) | FOUND |
| Commit 296f74b9 (feat GREEN Task 1) | FOUND |
| Commit 1485795c (test RED Task 2) | FOUND |
| Commit 318683a6 (feat GREEN Task 2) | FOUND |
