---
phase: quick
plan: 1
subsystem: tts
tags: [research, tts, orpheus, audio-quality, naturalness]
dependency_graph:
  requires: []
  provides: [tts-naturalness-root-causes, tts-fix-recommendations]
  affects: [src/ergos/tts/orpheus_synthesizer.py, src/ergos/tts/processor.py, src/ergos/transport/audio_track.py]
tech_stack:
  added: []
  patterns: []
key_files:
  created:
    - .planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md
  modified: []
decisions:
  - "SNAC trailing token drop (up to 73ms per utterance) identified as primary cause of cut-off word endings"
  - "Per-chunk normalization creates volume discontinuities — utterance-level normalization recommended"
  - "Digital zeros between sentences are the primary 'robotic' indicator — comfort noise at -62dBFS recommended"
  - "ZOH (np.repeat) upsampling causes -4dB at 12kHz — scipy resample_poly recommended as P2 fix"
  - "All P1+P2 fixes are in 3 files, ~60 lines total, no new dependencies"
metrics:
  duration: "25 minutes"
  completed: "2026-03-04"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Quick Task 1: TTS Naturalness Research Summary

**One-liner:** Identified 4 root causes of unnatural TTS voice output with ranked implementation fixes requiring only 3 file changes.

## What Was Built

RESEARCH.md (681 lines) covering the full audio path from Orpheus SNAC token generation through WebRTC delivery. Direct ONNX inference was run against the cached SNAC decoder model to verify output shapes and energy distribution empirically.

## Key Findings

### Primary Cause of "Last Word Cuts Off" (Hypothesis A — CRITICAL)

The `_decode` generator in `orpheus_cpp/model.py` silently drops the last 0–6 audio tokens per utterance because it only yields when `count % 7 == 0`. Up to 73ms of speech is discarded at every sentence end. Fix: pad trailing tokens to next multiple of 7 and force a final decode. Can be done as a monkey-patch in `OrpheusSynthesizer._ensure_model()` — no fork required.

### Primary Cause of "Unnatural Sentence Endings" (Hypothesis D — HIGH)

Each 85ms SNAC chunk is independently normalized to 0.95 peak. The last chunk naturally trails off (low amplitude), gets boosted to 0.95 by normalization, then immediately faded out — creating an audible volume surge before the fade. Fix: normalize the full utterance after collecting all chunks, then re-split.

### Primary Cause of "Not Like Human Conversation" (Hypothesis G — HIGH)

`np.zeros` between sentences creates true digital silence (-96dBFS). Human conversation has ambient noise at -40 to -60dBFS even in "silent" gaps. The abrupt `speech → 0 → speech` transition is immediately perceived as synthetic. Fix: `np.random.normal(0, 0.0008, n)` comfort noise at -62dBFS.

### Secondary Contributing Factors

- **Fade-in too short (8ms):** Fricatives and nasals need 20-50ms onset — 8ms clips them. Fix: 22ms.
- **Linear fades:** Cosine (equal-power) fades sound more natural. Fix: replace `np.linspace` with `np.sin(np.linspace(0, π/2, n))`.
- **ZOH upsampling:** `np.repeat` applies zero-order hold with -4dB at 12kHz. Fix: `scipy.signal.resample_poly`.
- **No cross-sentence prosody:** Each sentence restarts Orpheus inference from scratch — architectural limitation.

## Deviations from Plan

None. All hypotheses A–K were investigated and evidence was found for each. SNAC ONNX model was directly queried to confirm the 2048:4096 crop is intentional architecture (Hypothesis B), not a bug.

## Self-Check

- [x] RESEARCH.md exists: `.planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md`
- [x] Line count: 681 lines (requirement: 100+)
- [x] All three reported symptoms covered
- [x] All hypotheses A–K documented with evidence, likelihood, and impact ratings
- [x] Recommendations ranked by impact/effort ratio
- [x] Implementation notes specific enough to code from

## Self-Check: PASSED
