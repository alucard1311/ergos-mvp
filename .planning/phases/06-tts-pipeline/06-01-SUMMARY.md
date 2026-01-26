---
phase: 06-tts-pipeline
plan: 01
subsystem: tts
tags: [tts-synthesizer, kokoro-onnx, lazy-loading, async-streaming]

# Dependency graph
requires:
  - phase: 05-llm-integration
    provides: LLMGenerator patterns for lazy loading and streaming
provides:
  - TTSSynthesizer wrapper for kokoro-onnx
  - SynthesisResult and SynthesisConfig types
  - Lazy model loading pattern
  - Async streaming audio generation
affects: [tts-processor, webrtc-transport, audio-playback]

# Tech tracking
tech-stack:
  added: [kokoro-onnx>=0.4]
  patterns: [lazy-loading, async-streaming, dataclasses]

key-files:
  created:
    - src/ergos/tts/__init__.py
    - src/ergos/tts/types.py
    - src/ergos/tts/synthesizer.py
  modified:
    - pyproject.toml

key-decisions:
  - "Lazy model loading on first synthesize() call to avoid startup delay"
  - "Sample rate fixed at 24000 Hz (Kokoro's native output)"
  - "kokoro-onnx create_stream() is natively async, no executor needed"
  - "AudioCallback type for streaming audio chunks to playback"

patterns-established:
  - "TTSSynthesizer mirrors LLMGenerator lazy loading pattern"
  - "Async streaming via native async iteration from kokoro-onnx"

# Metrics
duration: 3min
completed: 2026-01-26
---

# Phase 6 Plan 1: TTS Types and Synthesizer Summary

**TTSSynthesizer wrapping kokoro-onnx with lazy loading and async streaming support**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-26T22:00:00Z
- **Completed:** 2026-01-26T22:03:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added kokoro-onnx>=0.4 to pyproject.toml dependencies
- Created TTS types: SynthesisResult, SynthesisConfig, AudioCallback
- Created TTSSynthesizer class with lazy model loading
- Implemented synchronous synthesize() method returning SynthesisResult
- Implemented async synthesize_stream() yielding (samples, sample_rate) tuples
- Added model_loaded and sample_rate properties
- Exported all types and TTSSynthesizer from ergos.tts package

## Task Commits

1. **Task 1: Add kokoro-onnx dependency and create TTS types** - `4a92b98` (feat)
2. **Task 2: Create TTSSynthesizer wrapper** - `dab8f62` (feat)

## Files Created/Modified

- `pyproject.toml` - Added kokoro-onnx>=0.4 dependency
- `src/ergos/tts/__init__.py` - Package exports: TTSSynthesizer, SynthesisResult, SynthesisConfig, AudioCallback
- `src/ergos/tts/types.py` - TTS result types and synthesis config dataclasses
- `src/ergos/tts/synthesizer.py` - TTSSynthesizer class wrapping kokoro-onnx

## Verification Results

All verification commands passed:
```
pip install -e .
# Output: Successfully installed kokoro-onnx-0.4.9 ergos-0.1.0 ...

python -c "from ergos.tts.types import SynthesisResult, SynthesisConfig, AudioCallback"
# Output: TTS types import successful

python -c "from ergos.tts import TTSSynthesizer; t = TTSSynthesizer('/tmp/fake.onnx', '/tmp/fake.bin'); print('Synthesizer created')"
# Output: Synthesizer created

python -c "from ergos.tts import TTSSynthesizer, SynthesisResult"
# Output: Full import successful
```

## Decisions Made

- Used dataclasses for types (following llm/types.py pattern)
- SynthesisConfig defaults: voice="af_sarah", speed=1.0, lang="en-us"
- kokoro-onnx create_stream() is natively async (unlike llama-cpp-python)
- Duration calculated from samples length and sample rate

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## User Setup Required

- Download Kokoro model files to use with TTSSynthesizer:
  - kokoro-v1.0.onnx (model file)
  - voices-v1.0.bin (voices file)
- Model paths must be provided when instantiating TTSSynthesizer

## Next Phase Readiness

- TTSSynthesizer ready for TTSProcessor integration (06-02)
- Types ready for audio streaming and playback
- Async streaming available for real-time sentence-based synthesis

---
*Phase: 06-tts-pipeline*
*Completed: 2026-01-26*
