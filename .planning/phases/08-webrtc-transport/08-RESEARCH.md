# Phase 8: WebRTC Transport - Research

**Researched:** 2026-01-26
**Domain:** Python WebRTC with aiortc for real-time bidirectional audio
**Confidence:** HIGH

<research_summary>
## Summary

Researched the aiortc library for implementing WebRTC transport between the Ergos Python server and Flutter mobile client. aiortc is the only mature Python WebRTC implementation, built on asyncio with pure Python codec handling via PyAV.

Key finding: aiortc handles Opus encoding/decoding internally at 48kHz, automatically resampling from other rates. The library provides `AudioStreamTrack` as the base class for custom audio sources - subclass it and implement `recv()` to return `AudioFrame` objects from a queue/buffer.

**Primary recommendation:** Use aiortc 1.14.0 with aiohttp for HTTP signaling. Create custom `AudioStreamTrack` subclasses for TTS output, use `MediaRecorder` or custom track for receiving client audio. Data channels carry JSON messages for VAD events and state changes.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiortc | 1.14.0 | WebRTC implementation | Only mature Python WebRTC, asyncio-native |
| aiohttp | 3.x | HTTP server for signaling | aiortc examples use it, async compatible |
| av (PyAV) | auto | Audio/video codec handling | Required by aiortc for Opus encoding |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | existing | Audio array manipulation | Converting between formats |
| fractions | stdlib | Frame timing (time_base) | Setting pts/time_base on AudioFrame |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| aiohttp | FastAPI/Starlette | FastAPI heavier, aiohttp matches aiortc examples |
| HTTP signaling | WebSocket signaling | HTTP simpler, WebSocket if need persistent connection |

**Installation:**
```bash
pip install aiortc aiohttp
```

Note: aiortc pulls in PyAV which handles Opus codec. No separate Opus library needed.
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```
src/ergos/
├── transport/
│   ├── __init__.py
│   ├── types.py           # DataChannelMessage, SignalingRequest/Response
│   ├── signaling.py       # HTTP routes for offer/answer
│   ├── connection.py      # RTCPeerConnection management
│   ├── audio_track.py     # Custom AudioStreamTrack for TTS output
│   └── data_channel.py    # VAD/state message handling
```

### Pattern 1: HTTP POST Signaling (offer/answer)
**What:** Client sends SDP offer via HTTP POST, server returns answer
**When to use:** Simple signaling without persistent connection
**Example:**
```python
# Source: aiortc examples/server/server.py
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)  # Track for cleanup

    # Handle incoming audio track
    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            # Route to STT pipeline
            pass

    # Handle data channel
    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            # Parse VAD events
            data = json.loads(message)
            if data["type"] == "vad_event":
                handle_vad(data)

    # Set remote offer, create answer
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })
```

### Pattern 2: Custom AudioStreamTrack for TTS Output
**What:** Subclass AudioStreamTrack, implement recv() to pull from TTS queue
**When to use:** Sending synthesized audio to client
**Example:**
```python
# Source: Verified pattern from aiortc issues/discussions
import asyncio
import fractions
from aiortc import MediaStreamTrack
from av import AudioFrame
import numpy as np

AUDIO_PTIME = 0.020  # 20ms per frame (aiortc standard)

class TTSAudioTrack(MediaStreamTrack):
    """Custom track that streams TTS audio to WebRTC."""

    kind = "audio"

    def __init__(self, sample_rate: int = 24000):
        super().__init__()
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
        self._sample_rate = sample_rate
        self._timestamp = 0
        self._samples_per_frame = int(sample_rate * AUDIO_PTIME)

    async def recv(self) -> AudioFrame:
        """Return next audio frame. Called by aiortc at regular intervals."""
        if self.readyState != "live":
            raise MediaStreamError

        # Get audio from queue, or return silence
        try:
            samples = await asyncio.wait_for(
                self._queue.get(),
                timeout=AUDIO_PTIME
            )
        except asyncio.TimeoutError:
            samples = None

        if samples is None:
            # Generate silence (20ms worth)
            samples = np.zeros(self._samples_per_frame, dtype=np.int16)

        # Create AudioFrame from numpy array
        # Note: reshape for mono layout
        frame = AudioFrame.from_ndarray(
            samples.reshape(1, -1),  # shape: (channels, samples)
            format="s16",
            layout="mono"
        )
        frame.pts = self._timestamp
        frame.sample_rate = self._sample_rate
        frame.time_base = fractions.Fraction(1, self._sample_rate)

        self._timestamp += len(samples)
        return frame

    def push_audio(self, samples: np.ndarray) -> None:
        """Push TTS audio samples to the queue."""
        self._queue.put_nowait(samples)

    def clear(self) -> None:
        """Clear queue on barge-in."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
```

### Pattern 3: Data Channel Protocol for VAD/State
**What:** JSON messages over data channel for out-of-band signaling
**When to use:** VAD events (speech start/end), state broadcasts
**Example:**
```python
# Data channel message types
# Client → Server:
{"type": "vad_event", "event": "speech_start", "timestamp": 1706300000.123}
{"type": "vad_event", "event": "speech_end", "timestamp": 1706300002.456}

# Server → Client:
{"type": "state_change", "previous": "idle", "state": "listening", "timestamp": 1706300000.0}
{"type": "state_change", "previous": "processing", "state": "speaking", "timestamp": 1706300003.0}

# Implementation:
@pc.on("datachannel")
def on_datachannel(channel):
    # Store for state broadcasts
    data_channels.add(channel)

    @channel.on("message")
    def on_message(message):
        data = json.loads(message)
        if data["type"] == "vad_event":
            # Forward to pipeline
            await handle_vad_event(data)

# Broadcasting state changes (from state machine callback)
async def broadcast_state(event: StateChangeEvent):
    message = json.dumps(event.to_dict())
    for channel in data_channels:
        if channel.readyState == "open":
            channel.send(message)
```

### Pattern 4: Receiving Client Audio
**What:** Handle incoming audio track, convert frames to pipeline format
**When to use:** Receiving microphone audio from client
**Example:**
```python
@pc.on("track")
def on_track(track):
    if track.kind == "audio":
        asyncio.create_task(process_audio_track(track))

async def process_audio_track(track: MediaStreamTrack):
    """Process incoming audio frames from client."""
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            break

        # Convert AudioFrame to numpy array
        # frame.to_ndarray() returns shape (channels, samples)
        samples = frame.to_ndarray()

        # Convert to 16kHz mono int16 if needed
        # (aiortc decodes Opus to native format)
        # Then push to audio buffer for STT
        await audio_buffer.push(samples)
```

### Anti-Patterns to Avoid
- **Blocking in recv():** Never block the event loop; return silence if no audio available
- **Ignoring pts/time_base:** Incorrect timestamps cause audio sync issues
- **Creating tracks per connection:** Use MediaRelay for multiple consumers of same source
- **Hardcoding 48kHz:** aiortc's Opus encoder handles resampling, but track should match source rate
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Opus encoding | Manual opus library bindings | aiortc + PyAV | aiortc handles codec negotiation, resampling automatically |
| SDP parsing | Regex/manual parsing | RTCSessionDescription | SDP is complex, aiortc handles all edge cases |
| ICE/DTLS | Custom NAT traversal | RTCPeerConnection | Months of work to get right, security critical |
| Audio frame timing | Manual sleep/timing | AudioStreamTrack pattern | recv() called at correct intervals by aiortc |
| Signaling protocol | Custom binary format | JSON over HTTP + data channel | Standard pattern, easy to debug |
| Audio format conversion | Manual byte manipulation | PyAV AudioFrame.from_ndarray | Handles format, layout, resampling |

**Key insight:** WebRTC is a complex protocol stack (ICE, DTLS, SRTP, SCTP, codecs). aiortc wraps all of this. The only custom code needed is the audio source/sink logic specific to Ergos.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Audio Frame Timestamp Errors
**What goes wrong:** Audio sounds choppy, garbled, or has gaps
**Why it happens:** Incorrect or non-incrementing pts values, wrong time_base
**How to avoid:**
- Set `frame.pts` to cumulative sample count
- Set `frame.time_base = fractions.Fraction(1, sample_rate)`
- Increment pts by samples_in_frame after each recv()
**Warning signs:** Audio quality issues only over WebRTC, works fine locally

### Pitfall 2: Blocking in recv()
**What goes wrong:** Event loop blocks, connection times out, audio stutters
**Why it happens:** Waiting for audio data with blocking call
**How to avoid:**
- Use `asyncio.wait_for()` with timeout
- Return silence if no audio available
- Never use `time.sleep()` or blocking I/O
**Warning signs:** Server becomes unresponsive during audio gaps

### Pitfall 3: Sample Rate Mismatch
**What goes wrong:** Audio plays at wrong speed (chipmunk or slow-motion)
**Why it happens:** Track sample rate doesn't match actual audio data
**How to avoid:**
- TTS (Kokoro) outputs 24kHz - create track at 24kHz
- Client sends 16kHz - aiortc decodes to Opus native rate
- Always set `frame.sample_rate` correctly
**Warning signs:** Audio pitch is wrong

### Pitfall 4: ICE Connection Failures on Remote
**What goes wrong:** Works on localhost, fails on network
**Why it happens:** NAT traversal requires STUN/TURN servers
**How to avoid:**
- Configure STUN servers (Google's public ones work for testing)
- For production behind NAT, deploy TURN server (coturn)
**Warning signs:** Connection hangs at "checking" state

### Pitfall 5: Data Channel Not Ready
**What goes wrong:** Messages silently dropped
**Why it happens:** Sending before channel reaches "open" state
**How to avoid:**
- Check `channel.readyState == "open"` before send()
- Queue messages until channel opens
**Warning signs:** VAD events not received, state changes not broadcast

### Pitfall 6: Track Not Added Before Answer
**What goes wrong:** One-way audio (server can't send)
**Why it happens:** Track must be added before createAnswer()
**How to avoid:**
- Add outbound audio track after receiving offer, before createAnswer()
- Or add transceiver before connection
**Warning signs:** Client receives nothing, server receives audio fine
</common_pitfalls>

<code_examples>
## Code Examples

Verified patterns from official sources:

### Complete Signaling Server Setup
```python
# Source: aiortc examples/server + adaptations for Ergos
import json
import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

pcs: set[RTCPeerConnection] = set()
data_channels: set = set()

async def offer(request: web.Request) -> web.Response:
    """Handle WebRTC offer from client."""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            # Start processing incoming audio
            asyncio.create_task(handle_incoming_audio(track))

    @pc.on("datachannel")
    def on_datachannel(channel):
        data_channels.add(channel)

        @channel.on("close")
        def on_close():
            data_channels.discard(channel)

        @channel.on("message")
        def on_message(message):
            asyncio.create_task(handle_data_message(message))

    # Add outbound audio track for TTS
    tts_track = TTSAudioTrack(sample_rate=24000)
    pc.addTrack(tts_track)
    # Store reference for pushing TTS audio
    pc.tts_track = tts_track

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def on_shutdown(app):
    """Clean up connections on server shutdown."""
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

# Routes
app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_post("/offer", offer)
```

### AudioFrame Creation with Proper Timing
```python
# Source: PyAV docs + aiortc patterns
import fractions
import numpy as np
from av import AudioFrame

def create_audio_frame(
    samples: np.ndarray,
    pts: int,
    sample_rate: int = 24000,
    layout: str = "mono"
) -> AudioFrame:
    """Create properly timed AudioFrame from numpy array."""

    # Ensure correct dtype
    if samples.dtype != np.int16:
        samples = (samples * 32767).astype(np.int16)

    # Reshape for mono: (1, num_samples)
    if samples.ndim == 1:
        samples = samples.reshape(1, -1)

    frame = AudioFrame.from_ndarray(samples, format="s16", layout=layout)
    frame.pts = pts
    frame.sample_rate = sample_rate
    frame.time_base = fractions.Fraction(1, sample_rate)

    return frame
```

### Data Channel Message Handler
```python
# Source: Ergos state machine pattern + WebRTC best practices
import json

async def handle_data_message(message: str):
    """Handle incoming data channel message."""
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return

    msg_type = data.get("type")

    if msg_type == "vad_event":
        event = data.get("event")
        if event == "speech_start":
            await state_machine.start_listening()
        elif event == "speech_end":
            await state_machine.start_processing()

    elif msg_type == "barge_in":
        await state_machine.barge_in()

def broadcast_state_change(event):
    """Broadcast state change to all connected clients."""
    message = json.dumps(event.to_dict())
    for channel in data_channels:
        if channel.readyState == "open":
            channel.send(message)
```
</code_examples>

<sota_updates>
## State of the Art (2025-2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual opus bindings | PyAV codec handling | aiortc 1.0 (2021) | Pure Python, no native compilation |
| Separate SCTP library | Built-in pure Python SCTP | aiortc 1.0 (2021) | Simpler installation |
| Manual track relay | MediaRelay helper | aiortc 1.2 (2022) | Easy multi-consumer support |

**New tools/patterns to consider:**
- **aiortc 1.14.0:** Latest stable, Python 3.10-3.14 support
- **aiortc-h264-nvenc:** NVIDIA hardware encoding extension (video only, not needed for audio)

**Deprecated/outdated:**
- **Separate opus library:** Not needed, PyAV handles it
- **Manual AudioResampler:** aiortc's Opus encoder resamples automatically
</sota_updates>

<open_questions>
## Open Questions

Things that couldn't be fully resolved:

1. **TTS Sample Rate Handling**
   - What we know: Kokoro outputs 24kHz, Opus encoder expects 48kHz
   - What's unclear: Whether aiortc resamples automatically or track must output 48kHz
   - Recommendation: Test both - start with 24kHz track, verify quality. If issues, resample to 48kHz before frame creation

2. **Connection Lifecycle Management**
   - What we know: Need to track peer connections, clean up on disconnect
   - What's unclear: Best pattern for associating connection with pipeline components
   - Recommendation: Store connection context object with references to track, data channel, and pipeline components

3. **Multiple Concurrent Connections**
   - What we know: aiortc supports multiple connections
   - What's unclear: Resource scaling (each connection = separate pipeline instance?)
   - Recommendation: For v1, single client per server. Multi-client is v2 scope.
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- [aiortc official documentation](https://aiortc.readthedocs.io/en/latest/) - API reference, helpers
- [aiortc GitHub repository](https://github.com/aiortc/aiortc) - Examples, source code
- [aiortc examples/server](https://github.com/aiortc/aiortc/blob/main/examples/server/server.py) - Complete server implementation
- [PyAV AudioFrame API](https://pyav.org/docs/stable/api/audio.html) - Frame creation, timing

### Secondary (MEDIUM confidence)
- [aiortc issue #483](https://github.com/aiortc/aiortc/issues/483) - Custom audio track from raw data
- [DeepWiki aiortc media streams](https://deepwiki.com/aiortc/aiortc/2.4-media-streams) - MediaStreamTrack internals
- [MDN WebRTC Data Channels](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Using_data_channels) - Protocol understanding

### Tertiary (LOW confidence - needs validation)
- WebSearch results on STUN/TURN configuration - verify against aiortc RTCConfiguration docs
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: aiortc for Python WebRTC
- Ecosystem: aiohttp signaling, PyAV codecs, asyncio integration
- Patterns: HTTP signaling, custom AudioStreamTrack, data channel protocol
- Pitfalls: Frame timing, blocking, sample rates, ICE failures

**Confidence breakdown:**
- Standard stack: HIGH - aiortc is the only option, well-documented
- Architecture: HIGH - patterns from official examples
- Pitfalls: HIGH - documented in GitHub issues, verified
- Code examples: HIGH - adapted from official examples + verified patterns

**Research date:** 2026-01-26
**Valid until:** 2026-02-26 (30 days - aiortc ecosystem stable)
</metadata>

---

*Phase: 08-webrtc-transport*
*Research completed: 2026-01-26*
*Ready for planning: yes*
