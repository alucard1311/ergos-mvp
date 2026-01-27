# Plan 12-01 Summary: Pipeline Orchestration and Server Integration

## Completed Tasks

### Task 1: Create Pipeline orchestration module
- **File**: `src/ergos/pipeline.py` (251 lines)
- **Exports**: `Pipeline`, `create_pipeline`
- Created `Pipeline` dataclass containing all components
- Created `create_pipeline(config: Config) -> Pipeline` factory function
- Wired complete callback chain:
  - VAD events -> STT processor (`vad_processor.add_callback`)
  - STT transcription -> LLM processor (`stt_processor.add_transcription_callback`)
  - LLM tokens -> TTS processor (`llm_processor.add_token_callback`)
  - TTS audio -> WebRTC tracks (custom `on_tts_audio` callback)
  - State changes -> Data channel broadcast (`state_machine.add_callback`)
  - Barge-in -> TTS buffer clear (`state_machine.add_barge_in_callback`)
- Created `on_incoming_audio` callback to bridge WebRTC audio to STT pipeline
- Created signaling app via `create_signaling_app()`

### Task 2: Integrate pipeline with Server
- **File**: `src/ergos/server.py` (153 lines)
- Added `_pipeline` and `_runner` attributes to `Server.__init__`
- Updated `start()` to:
  - Create pipeline via `create_pipeline(self.config)`
  - Create aiohttp `AppRunner` and `TCPSite`
  - Start site on configured host:port
  - Log pipeline component status (STT model, LLM path, TTS engine)
- Updated `stop()` to:
  - Cleanup aiohttp runner
  - Close all pipeline connections
  - Continue existing PID file cleanup

### Task 3: Update __init__.py exports
- **File**: `src/ergos/__init__.py`
- Added `Pipeline` and `create_pipeline` to package exports
- Added `__all__` for explicit export list

## Verification Results

All verification checks passed:
- `python -c "from ergos.pipeline import create_pipeline"` - SUCCESS
- `python -c "from ergos.server import Server"` - SUCCESS
- `python -c "from ergos import Pipeline"` - SUCCESS
- No import errors in any module
- Pipeline wires STT -> LLM -> TTS callback chain correctly

## Key Links Verified

| From | To | Via | Pattern |
|------|-----|-----|---------|
| server.py | pipeline.py | `create_pipeline()` call | `create_pipeline` |
| pipeline.py | signaling.py | `create_signaling_app()` | `create_signaling_app` |
| pipeline.py | stt/processor.py | STTProcessor callback registration | `add_transcription_callback` |
| pipeline.py | llm/processor.py | LLMProcessor callback registration | `add_token_callback` |
| pipeline.py | tts/processor.py | TTSProcessor audio callback | `add_audio_callback` |

## Artifacts Summary

| File | Lines | Min Required | Status |
|------|-------|--------------|--------|
| `src/ergos/pipeline.py` | 251 | 100 | PASS |
| `src/ergos/server.py` | 153 | 120 | PASS |

## Commits

1. `feat(12-01): add Pipeline orchestration module`
2. `feat(12-01): integrate pipeline with server lifecycle`
3. `feat(12-01): export Pipeline from package root`

## Duration

Approximately 3 minutes

## Notes

- Models load lazily on first use (already implemented in each component)
- Server logs detailed pipeline status on startup for visibility
- Barge-in clears both TTS text buffer and audio track queues
- Audio sequence counter maintained per pipeline instance for AudioChunk creation
