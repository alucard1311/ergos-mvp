# Ergos Technical Requirements Document

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Desktop Client                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────────┐  │
│  │   VAD   │→ │  Opus   │→ │ WebRTC  │→ │ Data Channel  │  │
│  │ (Web)   │  │ Encoder │  │  Stack  │  │ (VAD events)  │  │
│  └─────────┘  └─────────┘  └─────────┘  └───────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ WebRTC (Audio + Data)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Ergos Server                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   State Machine                      │   │
│  │  IDLE ←→ LISTENING ←→ PROCESSING ←→ SPEAKING        │   │
│  │                    ↖ INTERRUPTED ↗                   │   │
│  └─────────────────────────────────────────────────────┘   │
│           │              │              │                   │
│           ▼              ▼              ▼                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │     STT     │ │     LLM     │ │     TTS     │          │
│  │  (Whisper)  │ │ (llama.cpp) │ │  (Kokoro)   │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Core Dependencies

| Component | Library | Version | Purpose |
|-----------|---------|---------|---------|
| Web Framework | FastAPI | >=0.109.0 | HTTP/WebSocket server |
| ASGI Server | Uvicorn | >=0.27.0 | Production server |
| WebRTC | aiortc | >=1.6.0 | Real-time audio transport |
| STT | faster-whisper | >=1.0.0 | Speech-to-text |
| LLM | llama-cpp-python | >=0.2.50 | Local LLM inference |
| TTS | ONNX Runtime | >=1.16.0 | Kokoro TTS inference |
| Numerics | NumPy | >=1.26.0 | Array operations |
| Audio | SciPy | >=1.12.0 | Audio processing |
| Config | PyYAML | >=6.0.1 | YAML parsing |
| CLI | Click | >=8.1.7 | Command-line interface |
| Console | Rich | >=13.7.0 | Pretty terminal output |
| HTTP Client | aiohttp | >=3.9.0 | Async HTTP |
| Validation | Pydantic | >=2.5.0 | Data validation |

### Development Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| pytest | >=7.4.0 | Testing framework |
| pytest-asyncio | >=0.23.0 | Async test support |
| ruff | >=0.1.0 | Linting and formatting |

## Project Structure

```
ergos/
├── src/ergos/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── main.py              # Server entry point
│   ├── config.py            # Configuration management
│   ├── core/
│   │   ├── __init__.py
│   │   ├── state_machine.py # Conversation state machine
│   │   └── persona.py       # Persona loader
│   ├── stt/
│   │   ├── __init__.py
│   │   ├── base.py          # STT interface
│   │   └── whisper.py       # Whisper implementation
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py          # LLM interface
│   │   └── llamacpp.py      # llama.cpp implementation
│   ├── tts/
│   │   ├── __init__.py
│   │   ├── base.py          # TTS interface
│   │   └── kokoro.py        # Kokoro implementation
│   └── transport/
│       ├── __init__.py
│       ├── signaling.py     # WebRTC signaling server
│       └── protocol.py      # Data channel protocol
├── personas/
│   └── default.yaml         # Default persona
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
├── scripts/
└── client/                  # Desktop client (Flutter)
```

## State Machine

### States

| State | Description |
|-------|-------------|
| IDLE | Waiting for user input |
| LISTENING | Recording user speech |
| PROCESSING | STT → LLM pipeline running |
| SPEAKING | TTS playback in progress |
| INTERRUPTED | Barge-in detected, stopping playback |

### Transitions

```
IDLE        --[vad_start]--> LISTENING
LISTENING   --[vad_stop]-->  PROCESSING
PROCESSING  --[response_ready]--> SPEAKING
SPEAKING    --[playback_complete]--> IDLE
SPEAKING    --[vad_start]--> INTERRUPTED
INTERRUPTED --[playback_stopped]--> LISTENING
```

### Callbacks

| Callback | Trigger | Data |
|----------|---------|------|
| on_transcript | STT complete | Transcribed text |
| on_response | LLM response chunk | Response text |
| on_audio_out | TTS audio ready | Audio bytes |
| on_state_change | Any transition | New state |

## WebRTC Signaling Protocol

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /offer | Accept SDP offer, return answer |
| GET | /health | Server status |
| POST | /disconnect | Close connection |

### Data Channel Messages

```typescript
// Client → Server
{ "type": "vad_start" }
{ "type": "vad_stop", "audio_duration_ms": number }

// Server → Client
{ "type": "interrupt_ack" }
{ "type": "state_change", "state": string }
{ "type": "error", "message": string }
```

## Configuration Schema

```yaml
server:
  host: "0.0.0.0"
  port: 8420
  log_level: "info"

hardware:
  device: "auto"  # auto | cuda | cpu | mps
  gpu_layers: -1  # -1 = all layers on GPU

models:
  stt:
    engine: "whisper"
    model: "base.en"  # tiny.en | base.en | small.en | medium.en
  llm:
    engine: "llamacpp"
    model: "~/.ergos/models/llm/default.gguf"
    context_length: 4096
    max_tokens: 256
    temperature: 0.7
  tts:
    engine: "kokoro"
    model: "~/.ergos/models/tts/kokoro.onnx"
    voice: "af_nova"
    speed: 1.0

audio:
  sample_rate: 16000
  vad_threshold: 0.5
  silence_duration_ms: 500

privacy:
  save_transcripts: false
  save_audio: false
  telemetry: false
```

## Hardware Detection

### Detection Logic

```python
def detect_hardware() -> str:
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"
```

### Model Selection by Hardware

| Hardware | STT Model | LLM Size | Notes |
|----------|-----------|----------|-------|
| CPU only | tiny.en | 3B Q4 | Functional but slow |
| NVIDIA 8GB | base.en | 7B Q4 | Good experience |
| NVIDIA 12GB+ | small.en | 7B Q8 | Better accuracy |
| Apple M1 | base.en | 7B Q4 | Metal acceleration |
| Apple M1 Pro+ | small.en | 7B Q8 | Better accuracy |

## CLI Commands

| Command | Description |
|---------|-------------|
| `ergos start` | Start the server |
| `ergos setup` | First-time setup wizard |
| `ergos persona list` | List available personas |
| `ergos persona set <name>` | Set active persona |
| `ergos status` | Show server status |
| `ergos --version` | Show version |

## Performance Targets

| Metric | Target |
|--------|--------|
| VAD → STT start | < 50ms |
| STT processing | < 500ms |
| LLM first token | < 200ms |
| TTS first audio | < 100ms |
| Total voice-to-voice | < 1000ms |
| Barge-in response | < 100ms |
| Memory (full pipeline) | < 8GB |

## Security Considerations

1. **No external network calls** for core functionality
2. **Local-only file access** - config and models in ~/.ergos/
3. **Input validation** on all WebRTC messages
4. **No arbitrary code execution** from personas
5. **Sandboxed audio processing**

## Testing Strategy

### Unit Tests
- State machine transitions
- Configuration loading
- Persona parsing
- Protocol message serialization

### Integration Tests
- Full pipeline (mock audio → transcript → response → audio)
- WebRTC connection lifecycle
- Barge-in handling

### End-to-End Tests
- Desktop client → Server round trip
- Multi-turn conversation
- Error recovery
