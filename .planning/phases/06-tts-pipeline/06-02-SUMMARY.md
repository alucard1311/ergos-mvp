---
phase: 06-tts-pipeline
plan: 02
subsystem: tts
tags: [tts-processor, sentence-chunking, streaming-audio, barge-in]

# Dependency graph
requires:
  - phase: 06-tts-pipeline
    plan: 01
    provides: TTSSynthesizer wrapper for kokoro-onnx
provides:
  - TTSProcessor with sentence chunking
  - Streaming audio callbacks
  - Buffer management for barge-in
affects: [pipeline-integration, webrtc-transport, audio-playback]

# Tech tracking
tech-stack:
  added: []
  patterns: [sentence-buffering, async-callbacks, dataclasses]

key-files:
  created:
    - src/ergos/tts/processor.py
  modified:
    - src/ergos/tts/__init__.py

key-decisions:
  - "Sentence boundaries detected by .!? followed by space or end of buffer"
  - "receive_token() designed as LLMProcessor token callback"
  - "Buffer cleared synchronously for immediate barge-in response"
  - "flush() called after LLM generation to synthesize remaining text"

patterns-established:
  - "TTSProcessor mirrors LLMProcessor callback registration pattern"
  - "Stats property pattern for monitoring processor state"

# Metrics
duration: 2min
completed: 2026-01-26
---

# Phase 6 Plan 2: TTS Processor Summary

**TTSProcessor with sentence chunking and streaming audio to callbacks**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-26T22:10:00Z
- **Completed:** 2026-01-26T22:12:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created TTSProcessor dataclass with TTSSynthesizer and SynthesisConfig
- Implemented receive_token() method for LLM token callback integration
- Implemented sentence boundary detection with configurable endings (.!?)
- Implemented sentence extraction from buffer
- Implemented _synthesize_and_stream() for synthesis and callback dispatch
- Implemented flush() to synthesize remaining buffer after LLM completes
- Implemented clear_buffer() for barge-in support
- Added add_audio_callback() and remove_audio_callback() methods
- Added stats property for monitoring (buffer_length, audio_callbacks, model_loaded)
- Added buffer property for read-only buffer inspection
- Updated ergos.tts exports to include TTSProcessor

## Task Commits

1. **Task 1: Create TTSProcessor with sentence chunking** - `766d215` (feat)
2. **Task 2: Add stats and update exports** - `f264959` (feat)

## Files Created/Modified

- `src/ergos/tts/processor.py` - TTSProcessor class with sentence chunking and streaming
- `src/ergos/tts/__init__.py` - Added TTSProcessor to package exports

## Verification Results

All verification commands passed:
```
python -c "from ergos.tts.processor import TTSProcessor; print('TTSProcessor importable')"
# Output: TTSProcessor importable

python -c "from ergos.tts import TTSProcessor, TTSSynthesizer, SynthesisResult, SynthesisConfig, AudioCallback; print('All TTS exports work')"
# Output: All TTS exports work

# Verification checklist:
# 1. All TTS classes importable from ergos.tts: PASS
# 2. Sentence chunking logic implemented: PASS
# 3. Buffer management for barge-in support: PASS
# 4. Streaming audio callbacks implemented: PASS
# 5. Stats and buffer properties: PASS
```

## Decisions Made

- Sentence endings configurable via sentence_endings field (default ".!?")
- Sentence complete when ending char at buffer end or followed by space
- Buffer lstripped after sentence extraction to avoid leading whitespace
- Audio callbacks receive (samples, sample_rate) tuples matching synthesizer output
- Errors in callbacks logged but don't stop other callbacks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## Integration Points

TTSProcessor is designed to integrate with LLMProcessor:
```python
# Wire LLM tokens to TTS
llm_processor.add_token_callback(tts_processor.receive_token)

# Process transcription (tokens stream to TTS)
completion = await llm_processor.process_transcription(result)

# Synthesize any remaining text
await tts_processor.flush()
```

## Next Phase Readiness

- Phase 06 (TTS Pipeline) complete
- TTSProcessor ready for pipeline integration (Phase 07)
- Streaming audio ready for WebRTC transport
- Barge-in support ready for state machine integration

---
*Phase: 06-tts-pipeline*
*Completed: 2026-01-26*
