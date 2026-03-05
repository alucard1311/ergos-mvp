---
status: awaiting_human_verify
trigger: "tts-inter-sentence-static"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:05:00Z
---

## Current Focus

hypothesis: CONFIRMED. Per-chunk peak normalization in synthesize_stream amplified near-silent SNAC warmup/trailing frames to 0.95 peak, creating audible static between sentences.
test: Added regression test + verified 31/31 tests pass
expecting: Clean audio in production after fix
next_action: Human verification — test in production with Orpheus engine

## Symptoms

expected: Clean, smooth audio transitions between sentences — each sentence flows naturally into the next
actual: A static/buzzing noise ("zzzzzz") occurs between every sentence. The pattern is: sentence audio → static buzz → next sentence audio
errors: No error messages in logs — this is an audio quality issue
reproduction: Ask the system any question that produces a multi-sentence response. The static noise appears at every sentence boundary.
started: Has always been present with Orpheus TTS engine — never worked cleanly

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-03-04T00:01:00Z
  checked: orpheus_cpp/model.py _decode() function
  found: _decode yields audio from buffer[-28:] on every 7-token boundary after count > 27. This is a sliding window — each chunk overlaps with the previous. The audio data itself is from `audio_hat[:, :, 2048:4096]` — always the same slice of each SNAC frame output.
  implication: The stream yields many small chunks. Each chunk in synthesize_stream is independently peak-normalized to 0.95.

- timestamp: 2026-03-04T00:01:30Z
  checked: OrpheusSynthesizer.synthesize_stream() lines 171-178
  found: Each chunk from stream_tts is independently peak-normalized: `peak = np.abs(audio_float32).max(); if peak > 0: audio_float32 = audio_float32 * (0.95 / peak)`. This runs for EVERY chunk independently.
  implication: If any chunk has very low amplitude (near-silence warmup/transition), it gets amplified to 0.95 peak. This is the difference vs synthesize() which collects ALL samples first then normalizes once.

- timestamp: 2026-03-04T00:02:00Z
  checked: OrpheusSynthesizer.synthesize() lines 128-137
  found: The non-streaming version collects the entire audio array first, then normalizes once: `audio_float32 = audio_int16.astype(np.float32) / 32768.0; peak = np.abs(audio_float32).max(); if peak > 0: audio_float32 = audio_float32 * (0.95 / peak)`. This is correct.
  implication: The streaming version's per-chunk normalization is the bug. The synthesize() reference does it correctly.

- timestamp: 2026-03-04T00:02:30Z
  checked: stream_tts_sync pre-buffer behavior
  found: The first chunk yielded in stream_tts_sync is the entire pre_buffer (1.5 seconds of buffered audio). Subsequent chunks are individual decoded frames. First chunk is fine (enough audio for meaningful normalization). But the LAST chunk before sentence ends, or transition chunks between sentences, can be small with low amplitude.
  implication: The per-chunk normalization is most dangerous for small/quiet chunks. But actually, the main issue is that EVERY sentence synthesis call to stream_tts uses a fresh LLM generation starting from scratch, so the very first chunk emitted (pre_buffer = 1.5s worth) could contain warmup/garbage audio that gets normalized, OR subsequent small chunks get over-amplified.

- timestamp: 2026-03-04T00:03:00Z
  checked: Where static noise occurs — "between sentences"
  found: The pattern is sentence audio → static buzz → next sentence. This means the noise occurs at the START of each new sentence synthesis call (second sentence onward). Each sentence calls synthesize_stream() independently from a cold-start LLM context. The pre_buffer at start of each call accumulates until 1.5s worth, then yields — that first chunk includes the warm-up tokens.
  implication: The SNAC decoder processes 4-frame windows (28 tokens). The first 28 tokens may decode to garbage/initialization audio before the model settles into clean speech. This "warmup noise" is present in every synthesis call, and per-chunk normalization amplifies it to 0.95 peak, making it clearly audible as static.

- timestamp: 2026-03-04T00:03:30Z
  checked: _token_to_id filtering — tokens with value <= 0 are discarded
  found: `if token is not None and token > 0: buffer.append(token)` — negative or zero tokens are skipped. But tokens that decode to near-silence (valid tokens, just very small amplitude) still pass through.
  implication: Even valid tokens can decode to very low amplitude if they represent silence or transition frames at the start/end of utterance. Per-chunk normalization then amplifies this to loud noise.

## Resolution

root_cause: Per-chunk peak normalization in OrpheusSynthesizer.synthesize_stream() amplified near-silent SNAC warmup/trailing frames to 0.95 peak. The Orpheus/SNAC decoder produces small-amplitude "warmup" chunks at the start of each synthesis call and potentially "trailing" chunks at the end. With the old code `if peak > 0: audio_float32 = audio_float32 * (0.95 / peak)`, a chunk with peak=0.001 would be amplified by factor 950x to full 0.95 peak — clearly audible as loud static/buzzing. Since each sentence is synthesized in a separate stream_tts call, this warmup noise appeared at every sentence boundary.

fix: Added _MIN_SPEECH_PEAK = 0.05 threshold. Normalization is now only applied when `peak >= _MIN_SPEECH_PEAK`. Near-silent chunks (warmup/trailing frames, peak < 0.05) are passed through as-is at their natural low amplitude. Real speech peaks at ~0.25 so it passes the threshold and gets normalized correctly to 0.95 peak.

verification: 31/31 unit tests pass including new regression test `test_synthesize_stream_no_normalization_for_quiet_chunks` that explicitly verifies quiet chunks (peak < 0.05) are not amplified, and speech chunks (peak ~0.25) are still normalized to 0.95.

files_changed:
  - src/ergos/tts/orpheus_synthesizer.py: Added _MIN_SPEECH_PEAK = 0.05 class constant; changed normalization guard from `if peak > 0` to `if peak >= self._MIN_SPEECH_PEAK`
  - tests/unit/test_tts_orpheus.py: Added regression test `test_synthesize_stream_no_normalization_for_quiet_chunks`
