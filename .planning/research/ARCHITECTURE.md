# Real-Time Voice AI Pipeline Architecture

## Research Summary

This document captures best practices for real-time voice AI pipelines (2024-2025), focusing on STT to LLM to TTS architectures with barge-in support, optimized for sub-second voice-to-voice latency.

---

## System Overview

```
                           ERGOS VOICE AI ARCHITECTURE

    +------------------+          WebRTC/WebSocket          +------------------+
    |                  |  <==============================>  |                  |
    |   CLIENT SIDE    |       Opus Audio + Signaling       |   SERVER SIDE    |
    |                  |                                    |                  |
    +------------------+                                    +------------------+
            |                                                        |
            v                                                        v
    +------------------+                                    +------------------+
    | Audio Capture    |                                    | Transport Layer  |
    | (MediaRecorder)  |                                    | (WebRTC/WS)      |
    +--------+---------+                                    +--------+---------+
             |                                                       |
             v                                                       v
    +------------------+                                    +------------------+
    | Client-side VAD  |                                    | Audio Router     |
    | (Silero/WebRTC)  |                                    | (Echo Cancel)    |
    +--------+---------+                                    +--------+---------+
             |                                                       |
             | Speech Start/Stop Events                              v
             v                                              +------------------+
    +------------------+                                    |   STT Engine     |
    | Audio Streaming  |                                    | (Deepgram/       |
    | Controller       |                                    |  Whisper)        |
    +------------------+                                    +--------+---------+
                                                                     |
                                                                     | Text Chunks
                                                                     v
                                                            +------------------+
                                                            |   LLM Engine     |
                                                            | (GPT-4o/Claude)  |
                                                            +--------+---------+
                                                                     |
                                                                     | Token Stream
                                                                     v
                                                            +------------------+
                                                            |   TTS Engine     |
                                                            | (ElevenLabs/     |
                                                            |  Cartesia)       |
                                                            +--------+---------+
                                                                     |
                                                                     | Audio Chunks
                                                                     v
                                                            +------------------+
                                                            | Audio Playback   |
                                                            | Queue Manager    |
                                                            +------------------+
```

### State Machine Overview

```
                         CONVERSATIONAL STATE MACHINE

                              +-------------+
                              |    IDLE     |
                              +------+------+
                                     |
                     Speech Detected | (VAD start)
                                     v
                              +-------------+
                         +--->| LISTENING   |<---+
                         |    +------+------+    |
                         |           |           |
        User continues   |   End of  |           | Barge-in detected
        speaking         |   Turn    |           | (interrupt)
                         |           v           |
                         |    +-------------+    |
                         +----| PROCESSING  |----+
                              +------+------+
                                     |
                          LLM starts | responding
                                     v
                              +-------------+
                         +--->| SPEAKING    |----+
                         |    +------+------+    |
                         |           |           |
        Continue TTS     |   TTS     |           | Barge-in detected
        playback         |   Complete|           | (stop immediately)
                         |           v           |
                         |    +-------------+    |
                         +----+    IDLE     +----+
                              +-------------+
```

---

## Component Responsibilities

| Component | Responsibility | Latency Budget | Technology Options |
|-----------|---------------|----------------|-------------------|
| **Transport** | Real-time bidirectional audio/data | < 50ms RTT | WebRTC (preferred), WebSocket |
| **Client VAD** | Detect speech start/stop locally | < 30ms | Silero VAD, WebRTC VAD, Picovoice Cobra |
| **Audio Codec** | Compress/decompress audio | 5-20ms | Opus (mandatory for WebRTC) |
| **STT Engine** | Convert speech to text (streaming) | 100-200ms | Deepgram Nova-3, AssemblyAI, Whisper |
| **Turn Detector** | Determine when user finished speaking | 50-100ms | Silence threshold + semantic model |
| **LLM Engine** | Generate response text | 200-400ms (TTFT) | GPT-4o, Claude, Llama 3 |
| **TTS Engine** | Convert text to speech (streaming) | 75-150ms (TTFA) | ElevenLabs Flash, Cartesia Sonic |
| **State Manager** | Orchestrate conversation flow | < 10ms | Custom FSM |
| **Audio Router** | Handle echo cancellation, mixing | < 10ms | AEC algorithms |
| **Barge-in Handler** | Detect and handle interruptions | < 100ms | VAD + state coordination |

---

## Recommended Project Structure

```
ergos/
+-- src/
|   +-- ergos/
|   |   +-- __init__.py
|   |   +-- main.py                    # Application entry point
|   |   +-- config.py                  # Configuration management
|   |   |
|   |   +-- transport/                 # Layer 1: Real-time communication
|   |   |   +-- __init__.py
|   |   |   +-- webrtc_server.py       # WebRTC signaling and media
|   |   |   +-- websocket_server.py    # WebSocket fallback
|   |   |   +-- audio_codec.py         # Opus encode/decode
|   |   |   +-- session_manager.py     # Connection lifecycle
|   |   |
|   |   +-- audio/                     # Layer 2: Audio processing
|   |   |   +-- __init__.py
|   |   |   +-- vad.py                 # Voice activity detection
|   |   |   +-- echo_cancellation.py   # AEC processing
|   |   |   +-- audio_buffer.py        # Circular buffer management
|   |   |   +-- resampler.py           # Sample rate conversion
|   |   |
|   |   +-- pipeline/                  # Layer 3: AI pipeline
|   |   |   +-- __init__.py
|   |   |   +-- orchestrator.py        # Pipeline coordinator (Pipecat-style)
|   |   |   +-- stt/
|   |   |   |   +-- __init__.py
|   |   |   |   +-- base.py            # STT interface
|   |   |   |   +-- deepgram.py        # Deepgram streaming
|   |   |   |   +-- whisper.py         # Local Whisper
|   |   |   +-- llm/
|   |   |   |   +-- __init__.py
|   |   |   |   +-- base.py            # LLM interface
|   |   |   |   +-- openai.py          # OpenAI streaming
|   |   |   |   +-- anthropic.py       # Claude streaming
|   |   |   +-- tts/
|   |   |       +-- __init__.py
|   |   |       +-- base.py            # TTS interface
|   |   |       +-- elevenlabs.py      # ElevenLabs streaming
|   |   |       +-- cartesia.py        # Cartesia streaming
|   |   |
|   |   +-- conversation/              # Layer 4: Conversation management
|   |   |   +-- __init__.py
|   |   |   +-- state_machine.py       # FSM: IDLE/LISTENING/PROCESSING/SPEAKING
|   |   |   +-- turn_detector.py       # End-of-turn detection
|   |   |   +-- barge_in.py            # Interruption handling
|   |   |   +-- context.py             # Conversation history
|   |   |
|   |   +-- frames/                    # Data types (Pipecat pattern)
|   |   |   +-- __init__.py
|   |   |   +-- audio.py               # AudioFrame, SilenceFrame
|   |   |   +-- text.py                # TextFrame, TranscriptionFrame
|   |   |   +-- control.py             # StartFrame, EndFrame, InterruptFrame
|   |   |
|   |   +-- utils/
|   |       +-- __init__.py
|   |       +-- logging.py
|   |       +-- metrics.py             # Latency tracking
|   |       +-- async_utils.py
|   |
|   +-- client/                        # Web client
|       +-- index.html
|       +-- js/
|       |   +-- audio-capture.js       # MediaRecorder + AudioWorklet
|       |   +-- vad-client.js          # Client-side VAD
|       |   +-- webrtc-client.js       # WebRTC connection
|       |   +-- audio-player.js        # Audio queue playback
|       +-- wasm/
|           +-- silero-vad.wasm        # WASM VAD model
|
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- latency/                       # Latency benchmarks
|
+-- scripts/
    +-- benchmark.py                   # E2E latency testing
```

---

## Architectural Patterns

### 1. Frame-Based Pipeline (Pipecat Pattern)

The frame-based pipeline pattern treats all data as typed frames flowing through processors.

```
FRAME TYPES AND FLOW

    SystemFrames (bypass queue - immediate processing)
    +-- InterruptFrame      # Barge-in signal
    +-- ErrorFrame          # Error propagation
    +-- MetricsFrame        # Latency data

    DataFrames (queued processing)
    +-- AudioRawFrame       # Raw PCM audio
    +-- AudioEncodedFrame   # Opus-encoded audio
    +-- TranscriptionFrame  # STT output (interim/final)
    +-- TextFrame           # LLM tokens
    +-- TTSAudioFrame       # Synthesized speech

    ControlFrames (queued, flow control)
    +-- StartFrame          # Begin processing
    +-- EndFrame            # End processing
    +-- FlushFrame          # Clear buffers


PIPELINE PROCESSING

    +------------+     +------------+     +------------+     +------------+
    |  Transport |---->|    STT     |---->|    LLM     |---->|    TTS     |
    | (AudioIn)  |     | Processor  |     | Processor  |     | Processor  |
    +------------+     +------------+     +------------+     +------------+
          |                  |                  |                  |
          |                  |                  |                  |
          v                  v                  v                  v
    +-----------------------------------------------------------------+
    |                    FRAME QUEUE (async)                          |
    +-----------------------------------------------------------------+
                                    |
                                    v
                           +--------------+
                           | State Machine|
                           | (Orchestrator)|
                           +--------------+
```

### 2. Streaming Architecture

All components must support streaming to achieve low latency.

```
STREAMING DATA FLOW (Concurrent Processing)

    Time -->

    User Speaking:
    [====Audio Chunk 1====][====Audio Chunk 2====][====Audio Chunk 3====]
                |                   |                   |
                v                   v                   v
    STT:   [Partial 1][Partial 2][Partial 3][Final Transcript]
                          |           |           |
                          v           v           v
    LLM:              [Context builds...][Token 1][Token 2][Token 3]...
                                              |       |       |
                                              v       v       v
    TTS:                                 [Chunk 1][Chunk 2][Chunk 3]...
                                              |       |       |
                                              v       v       v
    Playback:                            [=Play=][=Play=][=Play=]...


    KEY INSIGHT: Stages overlap to minimize perceived latency
    - STT processes while user speaks (streaming ASR)
    - LLM can start with partial context
    - TTS synthesizes per-sentence
    - Playback begins with first audio chunk
```

### 3. State Machine Design

```python
# Recommended state machine implementation pattern

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional

class ConversationState(Enum):
    IDLE = auto()         # Waiting for user
    LISTENING = auto()    # User is speaking
    PROCESSING = auto()   # Generating response
    SPEAKING = auto()     # Playing TTS output

@dataclass
class StateContext:
    current_state: ConversationState
    audio_buffer: bytes
    transcript: str
    response_text: str
    tts_queue: list
    interrupted: bool

class StateMachine:
    """
    Transitions:
    - IDLE -> LISTENING: VAD detects speech start
    - LISTENING -> PROCESSING: End-of-turn detected
    - LISTENING -> IDLE: Silence timeout (no valid speech)
    - PROCESSING -> SPEAKING: First TTS audio ready
    - PROCESSING -> LISTENING: Barge-in during processing
    - SPEAKING -> LISTENING: Barge-in during playback
    - SPEAKING -> IDLE: TTS playback complete
    """

    def transition(self, event: str) -> ConversationState:
        # State transition logic with guards
        pass

    def on_barge_in(self):
        # Immediate interrupt handling
        # 1. Stop TTS playback
        # 2. Clear audio queue
        # 3. Preserve conversation context
        # 4. Transition to LISTENING
        pass
```

### 4. Async Concurrency Pattern

```python
# Recommended async architecture using asyncio

import asyncio
from asyncio import Queue

class VoicePipeline:
    def __init__(self):
        # Separate queues for each stage
        self.audio_in_queue: Queue = Queue()
        self.transcript_queue: Queue = Queue()
        self.llm_queue: Queue = Queue()
        self.tts_queue: Queue = Queue()
        self.audio_out_queue: Queue = Queue()

    async def run(self):
        # Run all processors concurrently
        await asyncio.gather(
            self.audio_receiver(),      # Receives WebRTC audio
            self.stt_processor(),       # Streams to STT
            self.turn_detector(),       # Monitors for end-of-turn
            self.llm_processor(),       # Streams to LLM
            self.tts_processor(),       # Streams to TTS
            self.audio_sender(),        # Sends audio back
            self.interrupt_monitor(),   # Watches for barge-in
        )

    async def interrupt_monitor(self):
        """
        Critical: Must run with highest priority
        Monitors VAD during SPEAKING state
        Triggers immediate state transition on barge-in
        """
        pass
```

---

## Data Flow Diagrams

### Request Flow (Turn-Based)

```
USER TURN (LISTENING -> PROCESSING -> SPEAKING)

    Client                  Server                    External Services
      |                        |                             |
      |   1. Audio Stream      |                             |
      |----------------------->|                             |
      |   (Opus via WebRTC)    |                             |
      |                        |                             |
      |                        |   2. STT WebSocket          |
      |                        |--------------------------->.|
      |                        |   (Deepgram/Whisper)        |
      |                        |                             |
      |                        |   3. Partial Transcripts    |
      |                        |<---------------------------|
      |                        |                             |
      |   4. Interim Text      |                             |
      |<-----------------------| (optional feedback)         |
      |                        |                             |
      |                        |   5. End-of-Turn Detected   |
      |                        |   (silence + semantic)      |
      |                        |                             |
      |                        |   6. LLM Streaming          |
      |                        |---------------------------->|
      |                        |   (OpenAI/Anthropic)        |
      |                        |                             |
      |                        |   7. Token Stream           |
      |                        |<----------------------------|
      |                        |                             |
      |                        |   8. Sentence Buffer        |
      |                        |   (chunk at boundaries)     |
      |                        |                             |
      |                        |   9. TTS Streaming          |
      |                        |---------------------------->|
      |                        |   (ElevenLabs/Cartesia)     |
      |                        |                             |
      |                        |   10. Audio Chunks          |
      |                        |<----------------------------|
      |                        |                             |
      |   11. Audio Playback   |                             |
      |<-----------------------|                             |
      |   (Opus via WebRTC)    |                             |
      |                        |                             |
```

### Barge-In Flow (Interruption)

```
BARGE-IN HANDLING (SPEAKING -> LISTENING)

    Client                  Server
      |                        |
      | [Playing TTS Audio]    | [State: SPEAKING]
      |                        |
      |   User starts speaking |
      |   (VAD triggers)       |
      |                        |
      |   1. InterruptFrame    |
      |----------------------->|
      |   (immediate)          |
      |                        |
      |                        |   2. State -> LISTENING
      |                        |   - Cancel pending TTS
      |                        |   - Flush TTS queue
      |                        |   - Stop LLM generation
      |                        |
      |   3. StopAudioFrame    |
      |<-----------------------|
      |   (stop playback)      |
      |                        |
      |   4. New audio stream  |
      |----------------------->|
      |   (user's interruption)|
      |                        |
      |                        |   5. Resume STT processing
      |                        |   (new context includes
      |                        |    interrupted response)
      |                        |
```

### Audio Flow Detail

```
AUDIO PROCESSING CHAIN

    Client Microphone
           |
           v
    +----------------+
    | Audio Capture  |  16-bit PCM, 48kHz
    | (AudioWorklet) |
    +-------+--------+
            |
            v
    +----------------+
    | Client VAD     |  Silero WASM
    | Speech detect  |  10-30ms frames
    +-------+--------+
            |
            | Only when speech detected
            v
    +----------------+
    | Opus Encoder   |  20ms frames
    | (WebRTC)       |  20-40 kbps
    +-------+--------+
            |
            | WebRTC DataChannel or MediaStream
            v
    ==================== NETWORK ====================
            |
            v
    +----------------+
    | Opus Decoder   |  Server-side
    +-------+--------+
            |
            v
    +----------------+
    | Resampler      |  48kHz -> 16kHz (for STT)
    +-------+--------+
            |
            v
    +----------------+
    | Echo Cancel    |  Subtract TTS playback
    | (AEC)          |  from mic input
    +-------+--------+
            |
            v
    +----------------+
    | STT Engine     |  Streaming transcription
    | (16kHz input)  |  100-200ms chunks
    +----------------+
```

---

## Scaling Considerations

### Horizontal Scaling Architecture

```
PRODUCTION SCALING TOPOLOGY

                         +------------------+
                         |   Load Balancer  |
                         | (sticky sessions)|
                         +--------+---------+
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
    +---------------+     +---------------+     +---------------+
    | WebRTC Edge 1 |     | WebRTC Edge 2 |     | WebRTC Edge 3 |
    | (Regional)    |     | (Regional)    |     | (Regional)    |
    +-------+-------+     +-------+-------+     +-------+-------+
            |                     |                     |
            +---------------------+---------------------+
                                  |
                         +--------v---------+
                         |  Message Queue   |
                         | (Redis/RabbitMQ) |
                         +--------+---------+
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
    +---------------+     +---------------+     +---------------+
    | Pipeline      |     | Pipeline      |     | Pipeline      |
    | Worker 1      |     | Worker 2      |     | Worker N      |
    | (GPU-enabled) |     | (GPU-enabled) |     | (GPU-enabled) |
    +---------------+     +---------------+     +---------------+
            |                     |                     |
            +---------------------+---------------------+
                                  |
                         +--------v---------+
                         | External AI APIs |
                         | (STT/LLM/TTS)    |
                         +------------------+
```

### Scaling Recommendations

| Component | Scaling Strategy | Key Considerations |
|-----------|-----------------|-------------------|
| WebRTC Edge | Horizontal + Geographic | Deploy in user regions; sticky sessions required |
| Pipeline Workers | Horizontal + GPU | Use Kubernetes HPA; GPU sharing for TTS/STT |
| STT | API-based (external) | Connection pooling; fallback providers |
| LLM | API-based (external) | Token streaming; timeout handling |
| TTS | API-based (external) | Audio chunk buffering; sentence batching |
| State Store | Redis Cluster | Session state; sub-10ms latency |

### Latency Budget Allocation

```
TARGET: 800ms Voice-to-Voice Latency

    Component               Target      Max
    ----------------------------------------
    Network (client-edge)    50ms      100ms
    VAD + Turn Detection     50ms      100ms
    STT (streaming)         150ms      250ms
    LLM (TTFT)              200ms      350ms
    TTS (TTFA)              100ms      150ms
    Network (edge-client)    50ms      100ms
    ----------------------------------------
    TOTAL                   600ms      1050ms

    Buffer for variance:    200ms
```

---

## Anti-Patterns to Avoid

### 1. Sequential Processing (HIGH IMPACT)

```
BAD: Wait for full transcript before LLM

    [====== Full User Speech ======]
                                    |
                                    v
                            [Full Transcript]
                                    |
                                    v
                            [===== LLM =====]
                                            |
                                            v
                                    [Full Response]
                                            |
                                            v
                                    [===== TTS =====]

    Result: 3-5 second latency


GOOD: Stream everything

    [Audio Chunk 1][Audio Chunk 2][Audio Chunk 3]
           |             |             |
           v             v             v
    [Partial 1]  [Partial 2]  [Final Transcript]
                       |             |
                       v             v
                 [LLM Token Stream Begins]
                       |
                       v
                 [TTS Chunk 1][TTS Chunk 2]...

    Result: 500-800ms latency
```

### 2. Geographic Distribution (HIGH IMPACT)

```
BAD: Components in different regions

    User (NYC) --> STT (Virginia) --> LLM (London) --> TTS (Tokyo)

    Network latency: 300-500ms added


GOOD: Co-located components

    User (NYC) --> [STT + LLM + TTS] (Virginia)

    Network latency: 20-50ms
```

### 3. REST APIs for Audio (HIGH IMPACT)

```
BAD: HTTP request per audio chunk

    Each chunk: TCP handshake + HTTP overhead = 50-100ms added


GOOD: Persistent WebSocket/WebRTC connections

    Single connection: <5ms per chunk
```

### 4. Blocking State Transitions (MEDIUM IMPACT)

```
BAD: Wait for state change confirmation

    async def on_speech_end():
        await self.flush_audio_buffer()  # 50ms
        await self.finalize_transcript()  # 100ms
        await self.notify_llm_ready()     # 10ms
        # Total: 160ms wasted


GOOD: Optimistic state transitions

    async def on_speech_end():
        # Fire events concurrently
        asyncio.gather(
            self.flush_audio_buffer(),
            self.finalize_transcript(),
            self.notify_llm_ready(),
        )
        # Continue immediately
```

### 5. Large Audio Buffers (MEDIUM IMPACT)

```
BAD: Buffer 1 second of audio before sending

    User perceives: 1 second delay before any processing


GOOD: Small chunked streaming

    Buffer: 20-40ms chunks
    User perceives: Real-time responsiveness
```

### 6. Monolithic Error Handling (LOW IMPACT)

```
BAD: Retry entire pipeline on failure

    if stt_fails:
        restart_entire_conversation()


GOOD: Component-level fallbacks

    if stt_fails:
        switch_to_backup_stt()
        continue_processing()
```

### 7. Ignoring Partial Transcripts (MEDIUM IMPACT)

```
BAD: Only use final transcript

    Wait for is_final=True before any processing


GOOD: Pre-process with partials

    - Begin LLM context building with high-confidence partials
    - Warm up TTS connection
    - Prepare likely responses
```

---

## Integration Points

### WebRTC Integration

```
WEBRTC CONFIGURATION FOR VOICE AI

    RTCPeerConnection Config:
    {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'turn:your-turn-server.com',
              username: 'user',
              credential: 'pass' }
        ],
        bundlePolicy: 'max-bundle',
        rtcpMuxPolicy: 'require'
    }

    Audio Constraints:
    {
        audio: {
            echoCancellation: true,      // Browser AEC
            noiseSuppression: true,      // Browser noise reduction
            autoGainControl: true,       // Normalize volume
            sampleRate: 48000,           // Match Opus
            channelCount: 1              // Mono for voice
        }
    }

    Opus Codec Parameters:
    {
        'maxaveragebitrate': 32000,      // 32 kbps for voice
        'stereo': 0,                      // Mono
        'useinbandfec': 1,               // Forward error correction
        'usedtx': 1                       // Discontinuous transmission
    }
```

### Audio Codec Specifications

```
SUPPORTED AUDIO FORMATS

    OPUS (Primary - WebRTC)
    +-----------------------+-------------------+
    | Sample Rate           | 48 kHz            |
    | Channels              | 1 (mono)          |
    | Bitrate               | 20-40 kbps        |
    | Frame Size            | 20ms              |
    | Latency               | ~26.5ms           |
    +-----------------------+-------------------+

    PCM (Internal Processing)
    +-----------------------+-------------------+
    | Sample Rate (STT)     | 16 kHz            |
    | Sample Rate (TTS)     | 24 kHz / 48 kHz   |
    | Bit Depth             | 16-bit            |
    | Channels              | 1 (mono)          |
    +-----------------------+-------------------+

    CONVERSION CHAIN:
    Opus 48kHz --> Decode --> Resample 16kHz --> STT
    TTS Output 24kHz --> Resample 48kHz --> Encode Opus
```

### Model Inference Integration

```
STT INTEGRATION (Deepgram Example)

    WebSocket URL: wss://api.deepgram.com/v1/listen

    Query Parameters:
    - model=nova-3
    - language=en
    - encoding=opus
    - sample_rate=48000
    - channels=1
    - interim_results=true
    - endpointing=300         # ms of silence for endpoint
    - vad_events=true

    Send: Binary audio frames
    Receive: JSON transcription events


LLM INTEGRATION (OpenAI Streaming)

    Endpoint: POST /v1/chat/completions
    Headers:
    - Authorization: Bearer <key>
    - Content-Type: application/json

    Body:
    {
        "model": "gpt-4o",
        "messages": [...],
        "stream": true,
        "max_tokens": 150,        # Keep responses short
        "temperature": 0.7
    }

    Response: SSE stream of token chunks


TTS INTEGRATION (ElevenLabs WebSocket)

    WebSocket URL: wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input

    Send: JSON with text chunks
    {
        "text": "Hello, ",
        "voice_settings": {...},
        "generation_config": {
            "chunk_length_schedule": [50]  # Characters per chunk
        }
    }

    Receive: Binary audio chunks (MP3/PCM)
```

---

## Sources

### HIGH Confidence (Official Documentation)

- [Deepgram Live Audio API Docs](https://developers.deepgram.com/reference/speech-to-text/listen-streaming) - Official streaming STT documentation
- [Deepgram Text Chunking for TTS](https://developers.deepgram.com/docs/text-chunking-for-tts-optimization) - Official TTS optimization guide
- [LiveKit Agents Documentation](https://docs.livekit.io/agents/) - Official voice agent framework docs
- [LiveKit Turn Detection](https://docs.livekit.io/agents/multimodality/audio/) - End-of-turn handling
- [Pipecat Pipeline & Frame Processing](https://docs.pipecat.ai/guides/learn/pipeline) - Official pipeline architecture
- [Pipecat GitHub Architecture](https://github.com/pipecat-ai/pipecat/blob/main/docs/architecture.md) - Framework design
- [WebRTC Audio Codec Requirements (RFC 7874)](https://datatracker.ietf.org/doc/html/rfc7874) - IETF standard
- [MDN WebRTC Codecs](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/WebRTC_codecs) - Web standards reference
- [Amazon Nova Barge-in Docs](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-barge-in.html) - AWS interruption handling
- [Nuance Barge-in Documentation](https://docs.nuance.com/nvp-for-speech-suite/appdev/rc-bargin.html) - Enterprise voice platform

### MEDIUM Confidence (Industry Analysis/Tutorials)

- [AssemblyAI Voice AI Stack 2025](https://www.assemblyai.com/blog/the-voice-ai-stack-for-building-agents) - Industry overview and stack recommendations
- [AssemblyAI 300ms Latency Rule](https://www.assemblyai.com/blog/low-latency-voice-ai) - Latency optimization guide
- [Cartesia State of Voice AI 2024](https://cartesia.ai/blog/state-of-voice-ai-2024) - Industry analysis
- [Softcery Real-Time vs Turn-Based Architecture](https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture) - Architecture comparison
- [Modal Low-Latency Voice Bot](https://modal.com/blog/low-latency-voice-bot) - Pipecat implementation guide
- [Deepgram Flux State Machine](https://deepgram.com/learn/fluxing-conversational-state-and-speech-to-text) - State machine design
- [Gladia Concurrent Pipelines](https://www.gladia.io/blog/concurrent-pipelines-for-voice-ai) - Production deployment lessons
- [Cloudflare Realtime Voice AI](https://blog.cloudflare.com/cloudflare-realtime-voice-ai/) - Edge deployment patterns
- [VideoSDK WebRTC VAD](https://www.videosdk.live/developer-hub/webrtc/webrtc-voice-activity-detection) - VAD implementation
- [Gnani Barge-in AI](https://www.gnani.ai/resources/blogs/real-time-barge-in-ai-for-voice-conversations-31347) - Interruption handling
- [Sparkco Barge-in Detection](https://sparkco.ai/blog/master-voice-agent-barge-in-detection-handling) - Best practices
- [Introl Voice AI Infrastructure](https://introl.com/blog/voice-ai-infrastructure-real-time-speech-agents-asr-tts-guide-2025) - Infrastructure guide

### LOW Confidence (Community/Blog Posts)

- [ZedIoT WebRTC Real-Time ASR](https://zediot.com/blog/real-time-asr-sensevoice-webrtc/) - Integration tutorial
- [ZedIoT Full-Duplex Voice AI](https://zediot.com/blog/building-full-duplex-conversational-ai-with-rtc-ai/) - Implementation guide
- [Medium FastRTC Voice Agent](https://medium.com/thedeephub/fastrtc-voice-ai-agent-534aa8dec899) - Hugging Face FastRTC
- [GitHub py-webrtcvad](https://github.com/wiseman/py-webrtcvad) - Python VAD wrapper
- [GitHub voixen-vad](https://github.com/voixen/voixen-vad) - WebRTC VAD JavaScript
- [GitHub RealtimeTTS](https://github.com/KoljaB/RealtimeTTS) - Python TTS streaming library
- [GitHub Vocalis](https://github.com/Lex-au/Vocalis) - Open-source voice assistant reference
- [arXiv Low-Latency Voice Agents for Telecom](https://arxiv.org/html/2508.04721v1) - Research paper
- [arXiv Small-footprint AEC](https://arxiv.org/abs/2508.07561) - Echo cancellation research
- [SignalWire Latency Truth](https://signalwire.com/blogs/industry/ai-providers-lying-about-latency) - Industry critique
- [Twilio Core Latency Guide](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents) - Best practices
- [ZenML ElevenLabs Scaling](https://www.zenml.io/llmops-database/scaling-voice-ai-with-gpu-accelerated-infrastructure) - GPU infrastructure
- [Tencent Conversational State Machine](https://www.tencentcloud.com/techpedia/127736) - FSM design patterns
- [Dev.to AI Voice Agents Guide](https://dev.to/kaymen99/ai-voice-agents-in-2025-a-comprehensive-guide-3kl) - Implementation overview

---

## Key Takeaways for Ergos

1. **Use streaming everywhere**: Every component (STT, LLM, TTS) must support streaming for sub-second latency

2. **Client-side VAD is critical**: Reduces server load and enables faster barge-in detection

3. **State machine should be simple**: IDLE/LISTENING/PROCESSING/SPEAKING with clear transitions

4. **Barge-in requires immediate response**: Use SystemFrames that bypass queues

5. **Sentence-level TTS chunking**: Buffer LLM output until sentence boundaries for natural speech

6. **WebRTC over WebSocket**: Better latency, built-in echo cancellation, NAT traversal

7. **Co-locate services**: All AI services in same region to minimize network latency

8. **Target 800ms end-to-end**: Human conversations have 200-500ms pauses; stay under 800ms

9. **Measure everything**: Track TTFB for each component separately

10. **Plan for failures**: Fallback providers, graceful degradation, timeout handling
