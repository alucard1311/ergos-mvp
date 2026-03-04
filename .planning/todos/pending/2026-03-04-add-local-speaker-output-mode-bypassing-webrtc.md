---
created: 2026-03-04T03:24:13.100Z
title: Add local speaker output mode bypassing WebRTC
area: general
files:
  - src/ergos/pipeline.py
  - src/ergos/tts/processor.py
---

## Problem

Currently all TTS audio routes through WebRTC to the Flutter client on a phone. For local development and single-machine use, this adds unnecessary latency (encode → network → decode → speaker). There's no way to play synthesized audio directly on the dev machine's speakers/headphones.

## Solution

Add a `--local-audio` mode (or config flag) that pipes TTS output directly to the local audio device via `sounddevice` or `pyaudio`, bypassing the WebRTC transport entirely. This would:

- Eliminate network round-trip latency for local use
- Enable faster iteration during TTS development/testing
- Support headless server use without a phone client
- Could be toggled via config.yaml (`audio_output: local` vs `audio_output: webrtc`)
