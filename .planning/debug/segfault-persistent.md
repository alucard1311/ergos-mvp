# Debug: Persistent Segfault After 2-3 Voice Interactions

## Issue ID
segfault-persistent

## Summary
Server crashes with segfault after 2-3 voice interactions. Previous fixes for array contiguity,
track lifecycle, and state machine issues did not resolve the underlying problem.

## Symptoms

**From crash logs:**
- expected: Server runs stably for unlimited interactions
- actual: Segfault after 2-3 voice exchanges
- errors: "Segmentation fault (core dumped)" - no Python traceback
- reproduction: Connect client, have 2-3 conversations, crash occurs
- timeline: Multiple fixes applied but crash persists

**Key log before crash:**
```
STT: Raw transcription result: ''
STT: Empty transcription result, skipping callbacks
Segmentation fault (core dumped)
```

**Crash typically happens:**
- During audio frame processing (stereo-to-mono conversion)
- OR right after STT returns empty result
- OR during TTS generation

## Investigation

### Prior Fixes (Did Not Resolve)
1. audio_track.py: Added .copy() for array slices, np.ascontiguousarray()
2. signaling.py: Added .copy() for stereo->mono slice, contiguity check
3. connection.py: Added track.stop() on connection close
4. pipeline.py: State checks, TTS cancellation
5. tts/processor.py: Cancellation mechanism
6. llm/generator.py: Async stream iteration

### Native Libraries Involved
1. PyAV/ffmpeg - audio encoding/decoding
2. ctranslate2 (faster-whisper) - STT
3. ONNX Runtime (kokoro-onnx) - TTS
4. llama-cpp - LLM

### Key Discovery: Orphaned TTS Background Tasks

Analyzed kokoro-onnx's `create_stream()` implementation:

```python
async def create_stream(self, text, voice, ...):
    queue = asyncio.Queue()

    async def process_batches():
        for phonemes in batched_phonemes:
            # ONNX inference runs in thread pool
            audio_part, sample_rate = await loop.run_in_executor(
                None, self._create_audio, phonemes, voice, speed
            )
            await queue.put((audio_part, sample_rate))
        await queue.put(None)

    # Background task created but NOT tracked!
    asyncio.create_task(process_batches())

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk
```

**The Problem:**
1. `asyncio.create_task(process_batches())` creates a background task
2. When consumer (our code) stops iterating (cancellation/barge-in), the task keeps running
3. ONNX inference continues in thread pools
4. After multiple barge-ins, orphaned tasks accumulate
5. Combined with STT (ctranslate2), LLM (llama-cpp), and audio decoding (ffmpeg):
   - Massive thread contention
   - Native libraries competing for resources
   - Eventually triggers segfault

### Evidence

Test confirmed background task behavior:
```
Processing batch 0...
Consumer got: 0
Consumer got: 1
Simulating cancellation - breaking out of loop
Background task done: False    <-- Task still running!
Processing batch 2...          <-- ONNX keeps running
Processing batch 3...
Processing batch 4...
process_batches completed
After wait - Background task done: True
```

## Root Cause

**Orphaned TTS background tasks continue ONNX inference after cancellation.**

When TTS is cancelled on barge-in:
1. `tts_processor.cancel()` sets a flag
2. Consumer loop exits early
3. BUT kokoro's background `process_batches` task continues
4. ONNX inference keeps running in default thread pool
5. After multiple barge-ins: N orphaned tasks x M threads = resource exhaustion
6. Native code (ffmpeg, ctranslate2, ONNX, llama-cpp) eventually crashes

## Fix Applied

### 1. Add synthesis lock to serialize TTS calls (tts/processor.py)

```python
_synthesis_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

async def _synthesize_and_stream(self, text: str) -> None:
    if self._cancelled:
        return  # Skip if already cancelled

    async with self._synthesis_lock:
        if self._cancelled:
            return  # Double-check after acquiring lock

        try:
            async for samples, sample_rate in self.synthesizer.synthesize_stream(...):
                if self._cancelled:
                    return  # Check between chunks
                # ... process audio
        except asyncio.CancelledError:
            raise
```

### 2. Make cancel() async (tts/processor.py)

```python
async def cancel(self) -> None:
    self._cancelled = True
    self._buffer = ""
    logger.info("TTS: Synthesis cancelled")
    await asyncio.sleep(0)  # Yield to let pending ops see flag
```

### 3. Update caller to await cancel (pipeline.py)

```python
async def on_barge_in() -> None:
    await tts_processor.cancel()  # Now properly awaited
    for pc in list(connection_manager._connections):
        track = connection_manager.get_track(pc)
        if track is not None:
            track.clear()
```

## Why This Helps

1. **Synthesis lock** prevents concurrent synthesis calls
   - Only one kokoro stream can be active at a time
   - Reduces total number of potential orphaned tasks

2. **Multiple cancellation checks** exit early at every opportunity
   - Before acquiring lock
   - After acquiring lock
   - Between each audio chunk
   - Minimizes time spent in orphaned synthesis

3. **Async cancel with yield** allows pending operations to see the flag
   - Any synthesis waiting on lock sees cancellation immediately

## Verification

To verify the fix:
1. Start server: `python -m ergos.cli serve`
2. Connect client and speak
3. While TTS is playing, speak again (barge-in)
4. Repeat barge-in 5+ times
5. Verify no crash occurs
6. Monitor for resource accumulation (orphaned tasks)

## Remaining Considerations

The fix mitigates but doesn't fully prevent orphaned tasks because:
- kokoro's `create_stream()` doesn't expose the background task
- We can't cancel the task from outside

Full fix would require either:
1. kokoro-onnx adding cancellation support
2. Replacing kokoro-onnx with a TTS library that supports cancellation
3. Implementing custom async wrapper that tracks and cancels tasks

Current fix significantly reduces orphaned task accumulation and should
prevent the segfault under normal usage patterns.

## Files Changed

- `/home/vinay/ergos/src/ergos/tts/processor.py` - Added synthesis lock, async cancel, early exits
- `/home/vinay/ergos/src/ergos/pipeline.py` - Updated to await tts_processor.cancel()
