---
phase: 08-webrtc-transport
plan: 01
subsystem: transport
tags: [webrtc, aiortc, audio, json, signaling]

# Dependency graph
requires:
  - phase: 04-state-machine
    provides: StateChangeEvent for StateMessage conversion
  - phase: 06-tts-pipeline
    provides: Audio sample format (24kHz float32)
provides:
  - DataChannelMessage base class for WebRTC messaging
  - VADMessage for speech start/end events
  - StateMessage for state broadcasts to client
  - SignalingRequest/SignalingResponse for SDP exchange
  - TTSAudioTrack for streaming TTS audio to WebRTC
affects: [08-02-signaling, 08-03-connection, 08-04-data-channel]

# Tech tracking
tech-stack:
  added: [aiortc, aiohttp]
  patterns: [async-queue-audio-track, json-message-protocol]

key-files:
  created:
    - src/ergos/transport/types.py
    - src/ergos/transport/audio_track.py
  modified:
    - src/ergos/transport/__init__.py

key-decisions:
  - "24kHz sample rate for TTSAudioTrack to match Kokoro output"
  - "20ms frame duration (AUDIO_PTIME=0.020) for aiortc standard pacing"
  - "Non-blocking recv() returns silence when no audio available"

patterns-established:
  - "JSON serialization pattern for data channel messages"
  - "from_json/to_json methods on message types"
  - "Async queue pattern for audio streaming"

# Metrics
duration: 2 min
completed: 2026-01-26
---

# Phase 8 Plan 01: Transport Types and Audio Track Summary

**TTSAudioTrack with async queue pattern for non-blocking audio streaming, plus JSON-serializable message types for WebRTC data channel protocol**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-26T21:04:21Z
- **Completed:** 2026-01-26T21:05:56Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- DataChannelMessage base class with JSON serialization and deserialization
- VADMessage for speech_start/speech_end events with factory methods
- StateMessage that can be created directly from StateChangeEvent
- SignalingRequest/SignalingResponse for WebRTC SDP offer/answer exchange
- TTSAudioTrack that subclasses aiortc MediaStreamTrack
- Non-blocking recv() that returns silence when queue is empty
- Proper pts/time_base/sample_rate for smooth audio playback
- clear() method for barge-in support

## Task Commits

Each task was committed atomically:

1. **Task 1: Create transport types module** - `224111b` (feat)
2. **Task 2: Create custom AudioStreamTrack for TTS output** - `b25a5ab` (feat)
3. **Task 3: Update transport package exports** - `68363bb` (feat)

## Files Created/Modified

- `src/ergos/transport/types.py` - DataChannelMessage, VADMessage, StateMessage, SignalingRequest, SignalingResponse
- `src/ergos/transport/audio_track.py` - TTSAudioTrack with async queue and non-blocking recv()
- `src/ergos/transport/__init__.py` - Package exports with __all__ list

## Decisions Made

- **24kHz sample rate:** Matches Kokoro TTS output directly, aiortc handles resampling to Opus internally
- **20ms frame duration:** Standard for WebRTC audio pacing (AUDIO_PTIME = 0.020)
- **Non-blocking recv():** Uses asyncio.wait_for with timeout, returns silence to prevent connection stalls
- **Float32 to int16 conversion:** TTSAudioTrack handles TTS output format conversion automatically

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Transport types ready for signaling and connection modules
- TTSAudioTrack ready to be added to RTCPeerConnection
- Message types ready for data channel protocol implementation
- Ready for 08-02-PLAN.md (HTTP signaling server)

---
*Phase: 08-webrtc-transport*
*Completed: 2026-01-26*
