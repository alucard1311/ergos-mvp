# Ergos Technology Stack Research

**Last Updated:** 2026-01-26
**Research Focus:** Local-first voice assistant stack for Python 3.11+

---

## Core Technologies

| Component | Library | Version | Python | Purpose | Confidence |
|-----------|---------|---------|--------|---------|------------|
| **STT** | faster-whisper | 1.2.1 | >=3.9 | Speech-to-text via CTranslate2 (4x faster than OpenAI Whisper) | HIGH |
| **LLM** | llama-cpp-python | 0.3.16 | >=3.8 | Local LLM inference via llama.cpp with GGUF models | HIGH |
| **WebRTC** | aiortc | 1.14.0 | >=3.10 | Real-time audio/video streaming over WebRTC | HIGH |
| **TTS** | kokoro-onnx | 0.4.9 | >=3.10, <3.14 | Kokoro 82M TTS model via ONNX Runtime | HIGH |
| **API** | FastAPI | latest | >=3.8 | Async web framework with WebSocket support | HIGH |
| **ONNX Runtime** | onnxruntime(-gpu) | 1.23.2 | >=3.10 | Neural network inference (required for Kokoro) | HIGH |

### Version Compatibility Matrix for Python 3.11

All core libraries support Python 3.11. This is the recommended Python version for Ergos because:
- Full support from all core dependencies
- Stable async/await performance improvements
- Better error messages for debugging
- kokoro-onnx requires <3.14, so 3.11 provides good forward compatibility

---

## Supporting Libraries

### Audio Processing

| Library | Version | Purpose | Notes | Confidence |
|---------|---------|---------|-------|------------|
| **silero-vad** | 6.2.0 | Voice Activity Detection | Best accuracy, <1ms per 30ms chunk on CPU, MIT license | HIGH |
| **sounddevice** | 0.5.5 | Audio I/O with NumPy | Simpler API than PyAudio, better cross-platform | HIGH |
| **av (PyAV)** | 9.x | FFmpeg bindings | Required by aiortc for codec support | HIGH |
| **numpy** | latest | Audio array processing | Foundation for all audio manipulation | HIGH |
| **scipy** | latest | Audio signal processing | Resampling, FFT, wav file I/O | HIGH |
| **pydub** | latest | Audio format conversion | High-level API, requires FFmpeg | MEDIUM |

### Async & Networking

| Library | Version | Purpose | Notes | Confidence |
|---------|---------|---------|-------|------------|
| **uvloop** | 0.22.1 | Fast asyncio event loop | 2-4x faster than default asyncio, Linux/macOS only | HIGH |
| **httpx** | latest | Async HTTP client | Supports both sync/async, HTTP/2, modern API | HIGH |
| **aiohttp** | latest | Async HTTP client/server | Faster for pure async, good WebSocket support | HIGH |
| **websockets** | latest | WebSocket client/server | Lightweight, good for simple cases | MEDIUM |

### ML Infrastructure

| Library | Version | Purpose | Notes | Confidence |
|---------|---------|---------|-------|------------|
| **ctranslate2** | 4.5.0+ | Transformer inference | Backend for faster-whisper, CUDA 12 + cuDNN 9 | HIGH |
| **torch** | 2.4+ | Deep learning framework | Optional, for Silero VAD (can use ONNX instead) | MEDIUM |
| **huggingface-hub** | latest | Model downloading | For downloading GGUF models to llama-cpp-python | HIGH |

---

## Development Tools

| Tool | Purpose | Recommendation |
|------|---------|----------------|
| **uv** | Fast Python package manager | Preferred over pip for speed |
| **ruff** | Linting and formatting | Replaces flake8, black, isort |
| **pytest** | Testing framework | With pytest-asyncio for async tests |
| **mypy** | Type checking | For type safety in complex pipelines |
| **pre-commit** | Git hooks | Automate code quality checks |

---

## Alternatives Considered

### STT Alternatives

| Library | Verdict | Reason |
|---------|---------|--------|
| **openai-whisper** | Not recommended | 4x slower than faster-whisper, higher memory usage |
| **whisper.cpp** | Consider for C++ integration | Python bindings less mature than faster-whisper |
| **Vosk** | Good for resource-constrained | Lower accuracy but real-time streaming, smaller models (~50MB) |
| **RealtimeSTT** | Wrapper option | Combines faster-whisper + VAD, but project maintenance uncertain |

### TTS Alternatives

| Library | Verdict | Reason |
|---------|---------|--------|
| **Coqui TTS** | Good alternative | More voices but heavier, slower than Kokoro ONNX |
| **Piper** | Lightweight alternative | Fast, offline, good quality but fewer options than Kokoro |
| **edge-tts** | Not recommended | Requires internet (Microsoft Edge cloud TTS) |
| **pyttsx3** | Not recommended | Low quality, system TTS wrapper |
| **RealtimeTTS** | Wrapper option | Multi-engine support but maintenance uncertain |

### VAD Alternatives

| Library | Verdict | Reason |
|---------|---------|--------|
| **webrtcvad** | Not recommended | 4x more errors than Silero at 5% FPR, outdated GMM approach |
| **TEN-VAD** | Consider for lower latency | Newer, claims faster speech-to-non-speech detection than Silero |

### LLM Alternatives

| Library | Verdict | Reason |
|---------|---------|--------|
| **Ollama** | Good for simplicity | Easier setup but less control than llama-cpp-python |
| **vLLM** | Server deployments | Better for high-throughput servers, not local-first |
| **transformers** | Not recommended for local | Heavy, slower than llama.cpp for GGUF models |

### Voice Framework Alternatives

| Library | Verdict | Reason |
|---------|---------|--------|
| **Pipecat** | Consider as enhancement | Excellent for complex pipelines, integrates with aiortc |
| **LiveKit** | Cloud-focused | Good WebRTC but adds complexity for local-only use |

---

## What NOT to Use (Outdated or Problematic)

### Deprecated/Problematic Libraries

| Library | Issue | Alternative |
|---------|-------|-------------|
| **PyAudio** | Installation issues, callback complexity | Use sounddevice |
| **SpeechRecognition** | Wrapper only, limited offline support | Use faster-whisper directly |
| **pyttsx3** | Low quality system TTS | Use Kokoro ONNX or Piper |
| **webrtcvad** | Outdated GMM approach, poor accuracy | Use silero-vad |
| **openai (>=1.0 API changes)** | Breaking changes in 1.0 | Pin version or migrate code |

### Version-Specific Warnings

| Situation | Issue | Solution |
|-----------|-------|----------|
| **ctranslate2 + CUDA 11** | Not supported in latest versions | Use ctranslate2==3.24.0 |
| **ctranslate2 + cuDNN 8** | Compatibility issues with 4.5+ | Use ctranslate2==4.4.0 for CUDA 12 |
| **torch 2.3 + onnxruntime-gpu** | cuDNN version mismatch | Use torch >=2.4 with cuDNN 9 |
| **faster-whisper + Python 3.13** | ctranslate2 wheel availability varies | Use Python 3.11-3.12 for stability |

### Patterns to Avoid

1. **Using openai-whisper for real-time**: It's batch-oriented and 4x slower
2. **Creating HTTP clients per request**: Reuse aiohttp.ClientSession or httpx.AsyncClient
3. **Blocking I/O in async code**: Use asyncio.to_thread() for CPU-bound work
4. **Large Whisper models without GPU**: Use "small" or "base" models on CPU
5. **Synchronous FFmpeg calls**: Use av (PyAV) with async wrappers

---

## Version Compatibility Notes

### CUDA/cuDNN Compatibility (Critical)

```
CUDA 12.x + cuDNN 9.x:
  - ctranslate2 >= 4.5.0
  - onnxruntime-gpu >= 1.19.0
  - torch >= 2.4.0

CUDA 12.x + cuDNN 8.x:
  - ctranslate2 == 4.4.0
  - onnxruntime-gpu from Azure DevOps feed
  - torch == 2.3.x

CUDA 11.x + cuDNN 8.x (Legacy):
  - ctranslate2 == 3.24.0
  - onnxruntime-gpu from Azure DevOps feed
  - torch == 2.1.x
```

### Recommended Base Dependencies (pyproject.toml)

```toml
[project]
requires-python = ">=3.11,<3.14"

dependencies = [
    # Core voice pipeline
    "faster-whisper>=1.2.0",
    "llama-cpp-python>=0.3.0",
    "aiortc>=1.14.0",
    "kokoro-onnx>=0.4.0",

    # API framework
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.24.0",

    # Audio processing
    "silero-vad>=6.0.0",
    "sounddevice>=0.5.0",
    "numpy>=1.24.0",
    "scipy>=1.11.0",

    # Async performance
    "uvloop>=0.19.0; sys_platform != 'win32'",
    "httpx>=0.25.0",

    # ONNX Runtime (pick one based on hardware)
    "onnxruntime>=1.16.0",
    # "onnxruntime-gpu>=1.19.0",  # For CUDA 12 + cuDNN 9
]
```

### Audio Codec Support in aiortc

Supported incoming audio codecs:
- Opus (48 kHz) - recommended
- PCM (8 kHz, 16 kHz)

For optimal quality with WebRTC, target Opus at 48 kHz.

---

## Architecture Recommendations

### Pipeline Flow (Low Latency)

```
Audio Input (WebRTC/mic)
    |
    v
VAD (silero-vad) -----> Silence (skip processing)
    |
    v (speech detected)
Buffer until speech ends
    |
    v
STT (faster-whisper)
    |
    v
LLM (llama-cpp-python)
    |
    v
TTS (kokoro-onnx)
    |
    v
Audio Output (WebRTC/speakers)
```

### Latency Targets

| Component | Target | Notes |
|-----------|--------|-------|
| VAD | <5ms | Silero processes 30ms chunks in <1ms |
| STT | <500ms | faster-whisper with "small" model |
| LLM | <1000ms | Depends on model size and hardware |
| TTS | <200ms | Kokoro ONNX with streaming |
| **Total Round-Trip** | <2000ms | Achievable with proper async pipelining |

### Async Best Practices

1. Use `uvloop` on Linux/macOS for 2-4x event loop speedup
2. Run CPU-bound operations (STT, TTS) in thread pools via `asyncio.to_thread()`
3. Use streaming responses where possible (LLM token streaming, TTS chunk streaming)
4. Implement proper backpressure handling in WebSocket audio streams

---

## Sources

### Official Documentation (HIGH Confidence)
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) - SYSTRAN
- [llama-cpp-python GitHub](https://github.com/abetlen/llama-cpp-python) - abetlen
- [aiortc GitHub](https://github.com/aiortc/aiortc) - aiortc team
- [kokoro-onnx GitHub](https://github.com/thewh1teagle/kokoro-onnx) - thewh1teagle
- [silero-vad GitHub](https://github.com/snakers4/silero-vad) - Silero Team
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Tiangolo
- [uvloop GitHub](https://github.com/MagicStack/uvloop) - MagicStack
- [ONNX Runtime Documentation](https://onnxruntime.ai/docs/) - Microsoft

### PyPI Package Pages (HIGH Confidence)
- [faster-whisper PyPI](https://pypi.org/project/faster-whisper/)
- [llama-cpp-python PyPI](https://pypi.org/project/llama-cpp-python/)
- [aiortc PyPI](https://pypi.org/project/aiortc/)
- [kokoro-onnx PyPI](https://pypi.org/project/kokoro-onnx/)
- [silero-vad PyPI](https://pypi.org/project/silero-vad/)
- [sounddevice PyPI](https://pypi.org/project/sounddevice/)
- [uvloop PyPI](https://pypi.org/project/uvloop/)
- [onnxruntime PyPI](https://pypi.org/project/onnxruntime/)
- [pipecat-ai PyPI](https://pypi.org/project/pipecat-ai/)

### Technical Articles & Guides (MEDIUM Confidence)
- [Picovoice VAD Comparison 2025](https://picovoice.ai/blog/best-voice-activity-detection-vad-2025/) - Detailed VAD accuracy benchmarks
- [VideoSDK LLM Voice Assistant Architecture 2025](https://www.videosdk.live/developer-hub/llm/llm-for-voice-assistant) - Architecture patterns
- [Trinesis Real-Time Audio Processing 2024](https://trinesis.com/blog/articles-1/real-time-audio-processing-with-fastapi-whisper-complete-guide-2024-70) - FastAPI + Whisper guide
- [WebRTC.ventures Real-Time Voice AI 2024](https://webrtc.ventures/2024/10/real-time-voice-ai-openai-vs-open-source-solutions/) - Pipecat and aiortc usage
- [Speakeasy HTTP Clients Comparison](https://www.speakeasy.com/blog/python-http-clients-requests-vs-httpx-vs-aiohttp) - aiohttp vs httpx analysis
- [AssemblyAI Python Speech Recognition 2025](https://www.assemblyai.com/blog/the-state-of-python-speech-recognition) - STT library comparison

### Community Resources (LOW-MEDIUM Confidence)
- [Home Assistant Community - faster-whisper](https://community.home-assistant.io/t/even-faster-whisper-for-local-voice-low-latency-stt/864762) - Real-world latency discussions
- [Pipecat Documentation](https://docs.pipecat.ai/) - Voice agent framework
- [Neuphonic Pipecat Review 2025](https://www.neuphonic.com/blog/pipecat-review-open-source-ai-voice-agents) - Framework comparison
- [freeCodeCamp Private Voice Assistant Guide](https://www.freecodecamp.org/news/private-voice-assistant-using-open-source-tools/) - Implementation walkthrough

---

## Summary

For Ergos (local-first voice assistant with Python 3.11+, FastAPI, aiortc), the recommended 2024-2025 stack is:

**Core Pipeline:**
- STT: faster-whisper (1.2.x) with silero-vad (6.x) for voice activity detection
- LLM: llama-cpp-python (0.3.x) with GGUF quantized models
- TTS: kokoro-onnx (0.4.x) for high-quality, fast local synthesis
- Transport: aiortc (1.14.x) for WebRTC, FastAPI for HTTP/WebSocket

**Key Supporting Libraries:**
- Audio: sounddevice, numpy, scipy, av (PyAV)
- Async: uvloop (Linux/macOS), httpx
- ML Runtime: onnxruntime, ctranslate2

**Avoid:**
- openai-whisper (use faster-whisper)
- webrtcvad (use silero-vad)
- PyAudio (use sounddevice)
- pyttsx3 (use kokoro-onnx)

This stack provides sub-second latency with complete privacy through local-only processing.
