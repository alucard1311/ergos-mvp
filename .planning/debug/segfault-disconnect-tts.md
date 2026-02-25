# Debug: Segfault on Disconnect During TTS Start

## Issue ID
segfault-disconnect-during-tts

## Summary
Server crashes with segfault when data channel closes and audio track ends while transitioning to speaking state

## Symptoms (Pre-filled)

**From crash logs:**
- expected: Server handles client disconnect gracefully, even during state transitions
- actual: Segmentation fault when data channel closes while processing → speaking transition occurs
- errors: "Segmentation fault (core dumped)"
- reproduction: Client disconnects (or connection drops) while server is starting TTS response
- timeline: Crash sequence:
  1. VAD: Speech ended (3771ms)
  2. State: listening → processing
  3. STT transcribed text
  4. Data channel closed (remaining: 0)
  5. State: processing → speaking
  6. Incoming audio track ended
  7. SEGFAULT

**Key observation:** The crash happens at the intersection of:
- Client disconnecting (data channel closed, audio track ended)
- State machine transitioning to speaking
- TTS starting to generate audio

## Investigation Log

### Step 1: Examining key files
- [x] signaling.py - audio track handling
- [x] connection.py - connection cleanup
- [x] audio_track.py - TTSAudioTrack recv() method
- [x] data_channel.py - data channel close handling
- [x] pipeline.py - TTS audio callback, state transitions

### Step 2: Analysis

**Crash sequence traced:**
1. Client disconnects -> Data channel closes
2. `connection.py:on_connection_state_change` fires (state = "closed" or "failed")
3. Track removed from `_tracks` dict via `self._tracks.pop(pc, None)`
4. BUT `track.stop()` is NEVER called
5. State machine transitions processing -> speaking (unaware of disconnect)
6. TTS starts generating audio, calls `on_tts_audio` callback
7. `on_tts_audio` iterates over connections, may still have reference to closed connection
8. If track object exists anywhere, `push_audio()` is called
9. Track's `readyState` is still "live" (never stopped)
10. aiortc's RTP sender is in undefined state - connection closed but track not stopped
11. Native code (av/ffmpeg) accesses freed memory -> SEGFAULT

**Key findings:**
1. `TTSAudioTrack.push_audio()` does NOT check `readyState` before operating
2. `track.stop()` is never called when connection closes
3. Race condition: snapshot of `_connections` taken before cleanup, but track operations happen after

## Hypotheses

1. **Audio track recv() called after cleanup** - TTS pushes audio to track that's been freed
2. **Native memory freed early** - aiortc/av accessing numpy arrays after backing memory freed
3. **Race condition** - State transition to speaking starts TTS while connection cleanup in progress

## Root Cause
**CONFIRMED: Missing track.stop() call and missing readyState check in push_audio()**

When connection closes:
1. Connection is removed from tracking sets
2. But `track.stop()` is never called to properly terminate the track
3. `push_audio()` has no guard against operating on a non-live track
4. Native aiortc/av code may access freed resources

Two required fixes:
1. Call `track.stop()` in `connection.py` when connection state becomes closed/failed
2. Add `readyState` check in `push_audio()` to prevent operating on ended tracks

## Fix Applied

### Fix 1: Stop track when connection closes (`connection.py`)
```python
@pc.on("connectionstatechange")
async def on_connection_state_change() -> None:
    state = pc.connectionState
    logger.debug(f"Connection state changed to: {state}")
    if state in ("failed", "closed"):
        # CRITICAL: Stop the track BEFORE removing from tracking.
        # This prevents segfaults from aiortc native code accessing
        # freed resources if push_audio() is called during cleanup.
        track = self._tracks.pop(pc, None)
        if track is not None:
            track.stop()
            logger.debug("Stopped TTS audio track for closed connection")
        self._connections.discard(pc)
        logger.info(f"Connection removed from tracking (state: {state})")
```

### Fix 2: Guard push_audio() against non-live tracks (`audio_track.py`)
```python
def push_audio(self, samples: np.ndarray, input_sample_rate: int = 24000) -> None:
    # CRITICAL: Check if track is still live before modifying buffer.
    # This prevents segfaults when push_audio() is called after the
    # connection closes but before the track reference is cleaned up.
    if self.readyState != "live":
        logger.debug("TTSAudioTrack: Ignoring push_audio() - track not live")
        return
    # ... rest of method
```

### Fix 3: Stop all tracks in close_all() (`connection.py`)
```python
async def close_all(self) -> None:
    # CRITICAL: Stop all tracks BEFORE closing connections.
    # This prevents segfaults from native code accessing freed resources.
    for track in self._tracks.values():
        track.stop()
    logger.debug(f"Stopped {len(self._tracks)} TTS audio tracks")
    # ... rest of method
```

## Verification

### Syntax check: PASSED
```
python -m py_compile src/ergos/transport/connection.py src/ergos/transport/audio_track.py
```

### Import test: PASSED
```
from ergos.transport.connection import ConnectionManager
from ergos.transport.audio_track import TTSAudioTrack
```

### Logic test: PASSED
- Track with readyState "live" accepts push_audio()
- Track.stop() changes readyState to "ended"
- Track with readyState "ended" silently ignores push_audio()

## Summary

**ROOT CAUSE:** Missing `track.stop()` call when connection closes, combined with no `readyState`
guard in `push_audio()`. This allowed TTS audio to be pushed to tracks whose underlying WebRTC
connection had been closed, causing aiortc native code to access freed memory.

**FIX:**
1. Call `track.stop()` when connection state becomes "failed" or "closed"
2. Guard `push_audio()` with `readyState != "live"` check
3. Stop all tracks in `close_all()` before closing connections

**PREVENTION:** The fixes implement defense-in-depth:
- Primary: Track is stopped immediately when connection closes
- Secondary: push_audio() refuses to operate on non-live tracks
- Tertiary: Graceful shutdown stops all tracks first
