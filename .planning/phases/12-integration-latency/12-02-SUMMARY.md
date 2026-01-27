# Plan 12-02 Summary: Latency Instrumentation

## Completed Tasks

### Task 1: Create latency metrics module
- **File**: `src/ergos/metrics.py` (168 lines)
- **Exports**: `LatencyTracker`, `LatencyMetrics`
- Created `LatencyMetrics` dataclass with:
  - `record(latency_ms)`: Add sample, update total, trim to last 100
  - `p50()`: Return median (0 if no samples)
  - `p95()`: Return 95th percentile (0 if no samples)
  - `mean()`: Return average (0 if no samples)
  - `to_dict()`: Return all stats as dictionary
- Created `LatencyTracker` class with:
  - `mark_speech_end()`: Record time when user stops speaking
  - `mark_first_audio()`: Record time when first TTS audio is ready
  - `compute_latency()`: Return ms between speech_end and first_audio
  - `reset()`: Clear current cycle times
  - `log_current()`: Log current cycle latency and cumulative stats
  - `is_waiting_for_audio`: Property to check if waiting for first audio

### Task 2: Integrate latency tracking into pipeline
- **File**: `src/ergos/pipeline.py` (277 lines, +29 lines)
- Added `latency_tracker: LatencyTracker` to Pipeline dataclass
- Created latency tracker instance in `create_pipeline()`
- Added VAD callback to mark speech_end on SPEECH_END events
- Wrapped TTS audio callback to:
  - Mark first audio when `is_waiting_for_audio` is True
  - Log current latency metrics
  - Reset tracker for next cycle
- Wired latency tracking at correct timing points:
  - `mark_speech_end`: When VAD emits SPEECH_END
  - `mark_first_audio`: When first TTS audio chunk is emitted

## Verification Results

All verification checks passed:
- `python -c "from ergos.metrics import LatencyTracker"` - SUCCESS
- LatencyMetrics computes P50, P95, mean correctly
- Pipeline wires latency tracking callbacks
- `python -c "from ergos.pipeline import create_pipeline"` - SUCCESS

## Key Links Verified

| From | To | Via | Pattern |
|------|-----|-----|---------|
| pipeline.py | metrics.py | LatencyTracker integration | `LatencyTracker` |

## Artifacts Summary

| File | Lines | Min Required | Status |
|------|-------|--------------|--------|
| `src/ergos/metrics.py` | 168 | 50 | PASS |
| `src/ergos/pipeline.py` | 277 | - | PASS |

## Commits

1. `feat(12-02): add LatencyTracker and LatencyMetrics module`
2. `feat(12-02): integrate latency tracking into pipeline`

## Duration

Approximately 3 minutes

## Notes

- Latency is measured from speech_end (VAD SPEECH_END event) to first TTS audio chunk
- This represents true "voice-to-voice" latency including STT + LLM + TTS
- Rolling window of 100 samples kept for percentile calculations
- Log format: `Latency: {current}ms | P50: {p50}ms | P95: {p95}ms | Mean: {mean}ms (n={count})`
