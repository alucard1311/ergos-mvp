---
status: fixed
trigger: "Server crashes with segfault during TTS audio streaming"
created: 2026-01-28T11:40:00Z
updated: 2026-01-28T12:15:00Z
---

## Current Focus

hypothesis: Non-contiguous numpy array passed to AudioFrame.from_ndarray() causes memcpy segfault
test: Review array operations in recv() for contiguity issues
expecting: Sliced arrays may not be C-contiguous, causing invalid memory access
next_action: Verify hypothesis and implement fix with np.ascontiguousarray()

## Symptoms

expected: TTS audio streams smoothly to client, server stays running
actual: Server crashes with "Segmentation fault (core dumped)" during TTS playback. User hears vague/garbled audio briefly before crash.
errors: Segmentation fault (core dumped) - no Python traceback, native code crash
reproduction: Start server, connect client, speak to trigger TTS response, crash occurs during TTS audio buffering
started: Ongoing issue during TTS streaming

## Key observations from logs

1. Crash happens DURING active TTS buffering (buffer at 872ms when crashed)
2. Buffer is being filled while also being read (concurrent operations)
3. Incoming audio still being processed (1920 sample chunks) while TTS pushes audio
4. TTS processor synthesizing short sentences like ' Have.'
5. Previous crash had buffer at 4813ms, this one at 872ms - buffer size varies

## Eliminated

[none yet]

## Evidence

### Evidence 1: AudioFrame.from_ndarray lacks contiguity check

In `/home/vinay/ergos/.venv/lib/python3.12/site-packages/av/audio/frame.py`:
- VideoFrame.from_ndarray checks `C_CONTIGUOUS` on arrays
- AudioFrame.from_ndarray does NOT check for C_CONTIGUOUS
- This means non-contiguous arrays can be passed to native code

### Evidence 2: buffer.pyx uses memcpy on buffer data

In `/home/vinay/ergos/.venv/lib/python3.12/site-packages/av/buffer.pyx` line 54:
```cython
memcpy(self._buffer_ptr(), source.ptr, size)
```
This assumes contiguous memory. If the numpy array is a view/slice with strides,
the buffer protocol will report the total "view" length but memory may not be
contiguous, causing memcpy to read invalid memory -> SEGFAULT.

### Evidence 3: recv() creates non-contiguous sliced arrays

In `/home/vinay/ergos/src/ergos/transport/audio_track.py` lines 76-78:
```python
all_samples = np.concatenate(self._buffer)  # Creates new contiguous array
samples = all_samples[:self._samples_per_frame]  # SLICE - creates VIEW, shares memory
remaining = all_samples[self._samples_per_frame:]  # Another VIEW
```

The slice `samples = all_samples[:N]` creates a VIEW, not a copy.
- Views share memory with the original array
- For 1D arrays along axis 0, slices ARE typically contiguous
- BUT after reshape(1, -1), slices along axis 1 may not be

### Evidence 4: reshape(1, -1) changes memory layout

In `/home/vinay/ergos/src/ergos/transport/audio_track.py` line 98:
```python
samples = samples.reshape(1, -1)  # Reshape for mono layout: (1, num_samples)
```

After reshape:
- Shape becomes (1, 960) for a 2D array
- When from_ndarray iterates planes and calls update(array[0, :])
- `array[0, :]` is a VIEW that depends on the underlying array's memory layout

### Evidence 5: Threading context

Even though threading.Lock is used:
1. `recv()` is called from aiortc's async event loop thread
2. `push_audio()` is called from TTS callback (potentially different thread context)
3. Lock protects list operations but not numpy array memory lifetime
4. `all_samples` created inside lock, but `samples` view used OUTSIDE lock (lines 92-108)

This is the CRITICAL BUG: samples array (a view of all_samples) is used
AFTER the lock is released. If push_audio modifies _buffer, the underlying
all_samples memory could be affected.

## Resolution

root_cause: Memory aliasing between samples array and buffer views causes segfault

The bug is a combination of two issues:

**Issue A: Memory view aliasing**
1. `all_samples = np.concatenate(self._buffer)` creates a new array
2. `samples = all_samples[:N]` creates a VIEW (not a copy)
3. `remaining = all_samples[N:]` creates another VIEW
4. `self._buffer = [remaining]` stores the view in the buffer

On the next `recv()` call, `np.concatenate(self._buffer)` may create a NEW array
that reuses or references the same memory region as `remaining`. The `samples`
view from the previous call might still be in use (being passed to from_ndarray).

**Issue B: View escapes lock scope while buffer is mutated**
- `samples` view is created inside the lock
- `samples` is used OUTSIDE the lock for dtype conversion, reshape, from_ndarray
- Meanwhile, another thread could call `push_audio()` which appends to buffer
- If timing is unlucky, memory gets corrupted

**Issue C: Non-contiguous array after reshape**
- `samples.reshape(1, -1)` creates a 2D view
- When `AudioFrame.from_ndarray` calls `plane.update(array[0, :])`, it accesses
  the underlying buffer via Python buffer protocol
- If the view's memory layout doesn't match what memcpy expects, segfault occurs

fix:
1. Create a COPY of samples before leaving the lock, not a view
2. Ensure the copy is C-contiguous before passing to from_ndarray
3. Do not store views in the buffer - store copies

Key changes to audio_track.py:
- Use `.copy()` on the samples slice to ensure independent memory
- Use `np.ascontiguousarray()` before from_ndarray to guarantee contiguous memory
- Consider using a contiguous copy for `remaining` as well

verification:
- Run server with TTS enabled
- Connect client and trigger multiple TTS responses
- Observe no crashes during sustained audio streaming
- Verify audio quality is not degraded

**Test Results:**
1. Basic recv() test: PASSED - frames created correctly, arrays contiguous
2. Concurrent push/recv test: PASSED - 100 frames received with continuous pushes
3. No segfaults in testing

files_changed:
- /home/vinay/ergos/src/ergos/transport/audio_track.py
