---
phase: 15-expressive-voice
plan: 01
subsystem: tts
tags: [tts, orpheus, expressive-voice, vram, pipeline]
dependency_graph:
  requires: []
  provides: [OrpheusSynthesizer, TTSConfig.engine=orpheus, pipeline-orpheus-wiring]
  affects: [src/ergos/tts, src/ergos/config.py, src/ergos/pipeline.py]
tech_stack:
  added: [orpheus-cpp>=0.0.3 (optional), orpheus-3b-q4 GGUF model]
  patterns: [lazy-loading, TDD-red-green, int16-to-float32-conversion]
key_files:
  created:
    - src/ergos/tts/orpheus_synthesizer.py
    - tests/unit/test_tts_orpheus.py
  modified:
    - src/ergos/tts/types.py
    - src/ergos/tts/__init__.py
    - src/ergos/config.py
    - src/ergos/pipeline.py
    - pyproject.toml
    - config.yaml
decisions:
  - "OrpheusSynthesizer uses orpheus_cpp.stream_tts() for streaming — yields (sample_rate, int16) tuples which are squeezed and converted to float32"
  - "orpheus-cpp registered as [orpheus] optional dependency extra, not core — users opt in"
  - "VRAM for Orpheus registered at 2000MB (Q4_K_M estimate) in engine selection block, matching CSM pattern"
  - "SynthesisConfig.orpheus_voice carries voice selection through TTSProcessor to synthesizer"
  - "Kokoro-82m excluded from VRAM when engine is csm OR orpheus (updated guard condition)"
metrics:
  duration_min: 8
  tasks_completed: 2
  files_changed: 8
  tests_added: 30
  completed_date: "2026-03-04"
---

# Phase 15 Plan 01: Orpheus TTS Engine Summary

**One-liner:** OrpheusSynthesizer wrapper for orpheus-cpp with lazy loading, int16->float32 conversion, and pipeline wiring at 2000MB VRAM budget.

## What Was Built

Added Orpheus 3B as a third TTS engine option alongside Kokoro (default) and CSM. Orpheus supports inline emotion tags (`<laugh>`, `<sigh>`, `<chuckle>`, etc.) for expressive speech synthesis, fulfilling VOICE-04.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| TDD RED | Failing tests for OrpheusSynthesizer | 464d820a | tests/unit/test_tts_orpheus.py |
| Task 1 + 2 GREEN | OrpheusSynthesizer + pipeline wiring | 7e2a0ef0 | orpheus_synthesizer.py, types.py, __init__.py, config.py, pipeline.py, pyproject.toml, config.yaml |

## Key Implementation Details

### OrpheusSynthesizer (src/ergos/tts/orpheus_synthesizer.py)

Same interface as KokoroSynthesizer and CSMSynthesizer:
- `synthesize(text, config)` → `SynthesisResult` — calls `orpheus.tts()`, converts int16 to float32
- `synthesize_stream(text, config)` → `AsyncIterator[(audio, sr)]` — wraps `orpheus.stream_tts()`
- `model_loaded` property, `sample_rate` = 24000, `close()` → sets `_orpheus = None`
- Lazy loading via `_ensure_model()` — no model downloaded at init

### Config Changes

- `SynthesisConfig.orpheus_voice: str = "tara"` — carries Orpheus voice selection
- `TTSConfig.engine` comment updated: `"kokoro", "csm", or "orpheus"`
- `TTSConfig.orpheus_voice: str = "tara"` and `TTSConfig.orpheus_n_gpu_layers: int = -1`
- `config.yaml`: `orpheus_voice: tara`, `orpheus_n_gpu_layers: -1` added under tts section

### Pipeline Wiring (src/ergos/pipeline.py)

- VRAM guard condition updated: `if config.tts.engine not in ("csm", "orpheus")` for kokoro-82m
- New `elif config.tts.engine == "orpheus"` branch creates `OrpheusSynthesizer` and registers `orpheus-3b-q4` at 2000MB
- `SynthesisConfig` built with `orpheus_voice` when engine is orpheus, passed to `TTSProcessor`

### Optional Dependency

`pyproject.toml` adds `[orpheus]` extra: `orpheus-cpp>=0.0.3`. Install with `pip install ergos[orpheus]`.

## Test Results

```
tests/unit/test_tts_orpheus.py  30 passed
tests/unit/test_tts_csm.py      25 passed (no regression)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test using `import toml` (not installed)**
- **Found during:** Task 1 TDD GREEN
- **Issue:** Test `test_orpheus_optional_dep_in_pyproject` used `import toml` which is not in the dev dependencies
- **Fix:** Removed the `import toml` line; the test already had raw file read fallback which was sufficient
- **Files modified:** tests/unit/test_tts_orpheus.py

## Self-Check: PASSED

All created/modified files verified:
- `src/ergos/tts/orpheus_synthesizer.py` — EXISTS (159 lines)
- `tests/unit/test_tts_orpheus.py` — EXISTS (438 lines, 30 tests pass)
- `src/ergos/tts/types.py` — MODIFIED (orpheus_voice field added)
- `src/ergos/tts/__init__.py` — MODIFIED (OrpheusSynthesizer exported)
- `src/ergos/config.py` — MODIFIED (orpheus_voice, orpheus_n_gpu_layers fields)
- `src/ergos/pipeline.py` — MODIFIED (orpheus engine branch + VRAM guard)
- `pyproject.toml` — MODIFIED ([orpheus] optional dependency)
- `config.yaml` — MODIFIED (orpheus fields added)

Commits verified:
- 464d820a — test(15-01) RED phase
- 7e2a0ef0 — feat(15-01) GREEN + pipeline wiring
