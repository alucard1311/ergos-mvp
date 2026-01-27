# Ergos

**Local-first voice assistant with complete privacy**

Ergos is a voice assistant that runs entirely on your local hardware. All speech recognition, language processing, and voice synthesis happen on your device - your voice data never leaves your machine.

## Features

- **Complete Privacy**: All processing runs locally - no cloud services, no data collection
- **Low Latency**: Optimized pipeline for responsive voice interactions
- **WebRTC Transport**: Real-time audio streaming via WebRTC
- **Flutter Client**: Mobile client for Android and iOS
- **Customizable Personas**: Define your assistant's personality and voice

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ergos.git
cd ergos

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e .
```

### Setup

```bash
# Create default configuration file
ergos setup
```

This creates `config.yaml` with default settings and shows detected hardware.

### Download Models

Ergos uses three AI models that need to be available:

1. **Speech-to-Text (STT)**: faster-whisper
   - Downloads automatically on first use
   - Default model: `base` (~150MB)

2. **Language Model (LLM)**: Phi-3 Mini via llama-cpp-python
   - You must provide a GGUF model file
   - Download from: https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf
   - Recommended: `Phi-3-mini-4k-instruct-q4.gguf` (~2GB)
   - Set path in `config.yaml` under `llm.model_path`

3. **Text-to-Speech (TTS)**: Kokoro ONNX
   - Downloads automatically on first use
   - Model files: `kokoro-v1.0.onnx`, `voices-v1.0.bin`

### Start Server

```bash
# Start the Ergos server
ergos start

# In another terminal, check status
ergos status

# Stop the server
ergos stop
```

## Client Connection

The Flutter mobile client connects to the Ergos server via WebRTC.

### Connection Flow

1. Client discovers server IP (manual or mDNS)
2. Client sends WebRTC offer to `http://<server>:8765/offer`
3. Server returns SDP answer
4. WebRTC connection established for:
   - Audio track: Client sends microphone audio
   - Audio track: Server sends TTS audio response
   - Data channel: VAD events and state updates

### Flutter Client

See the `client/` directory for the Flutter mobile app:

```bash
cd client
flutter pub get
flutter run
```

Configure the server IP in the app settings.

## Configuration

Edit `config.yaml` to customize Ergos:

```yaml
# Server settings
server:
  host: "0.0.0.0"    # Listen on all interfaces
  port: 8765          # HTTP port for signaling

# Speech-to-Text
stt:
  model: "base"       # Whisper model: tiny, base, small, medium, large
  device: "auto"      # auto, cuda, cpu

# Language Model
llm:
  model_path: "/path/to/Phi-3-mini-4k-instruct-q4.gguf"
  context_length: 4096
  max_tokens: 512
  device: "auto"

# Text-to-Speech
tts:
  voice: "af_heart"   # Kokoro voice name
  speed: 1.0
  device: "auto"

# Persona (assistant personality)
persona:
  persona_file: "~/.ergos/personas/default.yaml"
  # Or inline:
  # name: "Ergos"
  # system_prompt: "You are a helpful voice assistant."
```

### Persona Files

Create custom personas in YAML format:

```yaml
# ~/.ergos/personas/aria.yaml
name: Aria
description: a friendly AI companion
personality_traits:
  - warm
  - curious
  - helpful
voice: af_sarah
speaking_style: conversational
```

## Architecture

Ergos uses a streaming pipeline architecture:

```
[Client Microphone]
        |
        v
[WebRTC Audio Track] ---> [VAD Events via Data Channel]
        |                          |
        v                          v
[STT: faster-whisper] <--- [Speech Detection]
        |
        v
[LLM: Phi-3 Mini] -----> [Streaming Tokens]
        |
        v
[TTS: Kokoro ONNX] -----> [Audio Chunks]
        |
        v
[WebRTC Audio Track]
        |
        v
[Client Speaker]
```

### Component Overview

| Component | Library | Purpose |
|-----------|---------|---------|
| STT | faster-whisper | Speech-to-text transcription |
| LLM | llama-cpp-python | Response generation |
| TTS | kokoro-onnx | Text-to-speech synthesis |
| Transport | aiortc | WebRTC audio/data channels |
| Server | aiohttp | HTTP signaling endpoint |

### Latency Tracking

Ergos measures voice-to-voice latency:
- From: User stops speaking (VAD speech end)
- To: First TTS audio chunk ready

Target latency with GPU: P50 < 500ms, P95 < 800ms

## Requirements

### Hardware

- **CPU**: Modern multi-core processor
- **RAM**: 8GB minimum, 16GB recommended
- **GPU**: NVIDIA GPU with CUDA (recommended for low latency)
  - CPU-only mode works but with higher latency
- **Storage**: ~5GB for models

### Software

- **Python**: 3.11 or higher
- **CUDA**: 11.8+ (for GPU acceleration)
- **Flutter**: 3.0+ (for mobile client)

### Platform Support

| Platform | Server | Client |
|----------|--------|--------|
| Linux | Yes | - |
| macOS | Yes | - |
| Windows | Yes | - |
| Android | - | Yes |
| iOS | - | Yes |

## CLI Commands

```bash
ergos --help          # Show help
ergos --version       # Show version
ergos setup           # Create config file
ergos start           # Start server
ergos start -c path   # Start with custom config
ergos status          # Show server status
ergos stop            # Stop server
ergos -v start        # Verbose mode
```

## Troubleshooting

### Server won't start

1. Check if another instance is running: `ergos status`
2. Check port availability: `lsof -i :8765`
3. Run with verbose mode: `ergos -v start`

### High latency

1. Ensure GPU is detected: check startup logs for GPU info
2. Use smaller models: `stt.model: "tiny"` for faster transcription
3. Reduce LLM context: `llm.context_length: 2048`

### Client can't connect

1. Verify server IP is accessible from client device
2. Check firewall allows port 8765
3. Ensure both devices are on same network

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
python -m pytest tests/ -v
```

### Project Structure

```
ergos/
  src/ergos/
    audio/        # Audio types and VAD
    llm/          # Language model integration
    persona/      # Persona loading and types
    state/        # Conversation state machine
    stt/          # Speech-to-text pipeline
    transport/    # WebRTC connection handling
    tts/          # Text-to-speech pipeline
    cli.py        # Command line interface
    config.py     # Configuration loading
    pipeline.py   # Pipeline orchestration
    server.py     # Server lifecycle
  client/         # Flutter mobile app
  tests/          # Integration tests
```

## License

[License details here]

## Contributing

Contributions welcome! Please read our contributing guidelines before submitting PRs.
