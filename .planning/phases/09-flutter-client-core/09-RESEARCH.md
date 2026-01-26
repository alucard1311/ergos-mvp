# Phase 9: Flutter Client Core - Research

**Researched:** 2026-01-26
**Domain:** Flutter mobile app with audio capture, playback, VAD, and WebRTC
**Confidence:** HIGH

<research_summary>
## Summary

Researched the Flutter ecosystem for building a mobile voice assistant client with real-time audio streaming to a Python aiortc server. The standard approach uses `flutter_webrtc` for WebRTC peer connections and data channels, the `vad` package for client-side Silero VAD, and either `mic_stream` or `record` for audio capture when needed outside of WebRTC.

Key finding: WebRTC via `flutter_webrtc` handles both audio capture (microphone) and playback (remote audio) through `navigator.mediaDevices.getUserMedia()`. Client-side VAD should use the cross-platform `vad` package which wraps Silero VAD ONNX models. Data channels handle VAD events and state messages - this is already implemented on the server side.

**Primary recommendation:** Use flutter_webrtc for all WebRTC functionality (audio tracks, data channels), the `vad` package for speech detection, and `permission_handler` for runtime permissions. The signaling is already implemented on the server at `/offer` endpoint - Flutter client just needs to POST the SDP offer and receive the answer.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| flutter_webrtc | ^1.3.0 | WebRTC peer connection, audio tracks, data channels | Official Flutter WebRTC plugin, cross-platform, GoogleWebRTC-based |
| vad | ^0.0.7 | Client-side Voice Activity Detection | Cross-platform Silero VAD v4/v5, ONNX Runtime, no custom ML needed |
| permission_handler | ^11.0.0 | Runtime microphone permissions | Standard Flutter permission management, handles iOS/Android differences |
| http | ^1.0.0 | HTTP POST for signaling | Dart standard, for /offer SDP exchange |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| provider | ^6.0.0 | State management | WebRTC connection state, VAD state |
| equatable | ^2.0.0 | Value equality | For state classes if using BLoC |
| flutter_riverpod | ^2.0.0 | Alternative state management | If preferring Riverpod over Provider |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| vad | flutter_silero_vad | vad is more actively maintained, cross-platform |
| mic_stream | record | record is more feature-rich but vad package has built-in recording |
| Provider | BLoC/Riverpod | BLoC more boilerplate, Riverpod more modern but Provider simpler for MVP |

**Installation (pubspec.yaml):**
```yaml
dependencies:
  flutter_webrtc: ^1.3.0
  vad: ^0.0.7
  permission_handler: ^11.0.0
  http: ^1.0.0
  provider: ^6.0.0
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```
lib/
├── main.dart                    # App entry point
├── app.dart                     # MaterialApp configuration
├── services/
│   ├── webrtc_service.dart      # WebRTC connection management
│   ├── signaling_service.dart   # HTTP signaling to server
│   └── vad_service.dart         # Voice activity detection
├── models/
│   ├── connection_state.dart    # WebRTC connection states
│   ├── vad_event.dart           # VAD events (speech_start/end)
│   └── server_state.dart        # Server state messages
├── screens/
│   └── voice_screen.dart        # Main voice interaction UI
├── widgets/
│   └── connection_indicator.dart # Connection status widget
└── utils/
    └── permissions.dart         # Permission request helpers
```

### Pattern 1: WebRTC Service Singleton
**What:** Single WebRTC service managing connection lifecycle
**When to use:** Always - one connection per app instance
**Example:**
```dart
// Source: flutter-webrtc patterns
class WebRTCService {
  RTCPeerConnection? _peerConnection;
  RTCDataChannel? _dataChannel;
  MediaStream? _localStream;

  Future<void> connect(String serverUrl) async {
    // 1. Get local audio stream
    _localStream = await navigator.mediaDevices.getUserMedia({
      'audio': true,
      'video': false,
    });

    // 2. Create peer connection
    _peerConnection = await createPeerConnection({
      'iceServers': [{'urls': 'stun:stun.l.google.com:19302'}]
    });

    // 3. Add local audio track
    _localStream!.getAudioTracks().forEach((track) {
      _peerConnection!.addTrack(track, _localStream!);
    });

    // 4. Create data channel BEFORE offer
    _dataChannel = await _peerConnection!.createDataChannel(
      'data',
      RTCDataChannelInit(),
    );

    // 5. Create offer
    RTCSessionDescription offer = await _peerConnection!.createOffer();
    await _peerConnection!.setLocalDescription(offer);

    // 6. Send offer to server, get answer
    final answer = await _sendOfferToServer(serverUrl, offer);
    await _peerConnection!.setRemoteDescription(answer);
  }
}
```

### Pattern 2: HTTP Signaling (matching server /offer endpoint)
**What:** Send SDP offer via HTTP POST, receive SDP answer
**When to use:** Connecting to aiortc server
**Example:**
```dart
// Source: matching server signaling.py interface
Future<RTCSessionDescription> sendOfferToServer(
  String serverUrl,
  RTCSessionDescription offer
) async {
  final response = await http.post(
    Uri.parse('$serverUrl/offer'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'sdp': offer.sdp,
      'type': offer.type,
    }),
  );

  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return RTCSessionDescription(data['sdp'], data['type']);
  }
  throw Exception('Signaling failed: ${response.statusCode}');
}
```

### Pattern 3: VAD with Custom Audio Stream
**What:** Feed audio to VAD from WebRTC or mic_stream
**When to use:** Client-side speech detection
**Example:**
```dart
// Source: vad package documentation
final vadHandler = VadHandler.create(
  mode: VadMode.normal,
  sileroVadModelVersion: SileroVadModelVersion.v5,
  frameSamples: 512,  // 32ms frames for v5
  sampleRate: 16000,
);

vadHandler.onSpeechStart.listen((_) {
  // Send speech_start to server via data channel
  _dataChannel?.send(RTCDataChannelMessage(jsonEncode({
    'type': 'vad_event',
    'event': 'speech_start',
    'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
  })));
});

vadHandler.onSpeechEnd.listen((audioData) {
  // Send speech_end to server
  _dataChannel?.send(RTCDataChannelMessage(jsonEncode({
    'type': 'vad_event',
    'event': 'speech_end',
    'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
  })));
});
```

### Pattern 4: Data Channel Message Handling
**What:** Handle incoming server messages (state changes)
**When to use:** Receiving server state broadcasts
**Example:**
```dart
// Source: flutter-webrtc data channel API
_dataChannel!.onMessage = (RTCDataChannelMessage message) {
  final data = jsonDecode(message.text);
  switch (data['type']) {
    case 'state_change':
      // Update UI with new server state
      onStateChange(data['state'], data['previous']);
      break;
  }
};
```

### Anti-Patterns to Avoid
- **Creating data channel after offer:** Data channel must be created BEFORE createOffer() for server to receive it
- **Not waiting for ICE gathering:** setLocalDescription triggers ICE, wait for gathering complete or trickle ICE
- **Ignoring connection state changes:** Handle failed/disconnected states, implement reconnection
- **Blocking UI thread with audio processing:** VAD should process on separate isolate if heavy
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Voice Activity Detection | Custom audio analysis | vad package (Silero VAD) | ML-based, cross-platform, handles edge cases |
| WebRTC stack | Raw socket audio | flutter_webrtc | Handles ICE, DTLS, Opus codec, platform differences |
| Audio capture/playback | Platform channels | flutter_webrtc getUserMedia | WebRTC handles format conversion, permissions |
| SDP parsing | Manual parsing | RTCSessionDescription | Standard WebRTC format |
| Permission handling | Platform-specific code | permission_handler | Cross-platform, handles all edge cases |

**Key insight:** The flutter_webrtc package wraps GoogleWebRTC and handles all the complexity of WebRTC (ICE, DTLS, Opus codec, NAT traversal). The vad package wraps Silero VAD ONNX models trained on 6000+ languages. Custom implementations will be buggy and incomplete.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Data Channel Created After Offer
**What goes wrong:** Server doesn't see the data channel
**Why it happens:** Data channels must exist before SDP offer is created
**How to avoid:** Always call `createDataChannel()` BEFORE `createOffer()`
**Warning signs:** Data channel works locally but server never receives messages

### Pitfall 2: Missing iOS Podfile Configuration
**What goes wrong:** Build fails or crashes on iOS
**Why it happens:** WebRTC.xframework after m104 needs specific build settings
**How to avoid:** Add to ios/Podfile:
```ruby
post_install do |installer|
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |config|
      config.build_settings['ONLY_ACTIVE_ARCH'] = 'YES'
    end
  end
end
```
**Warning signs:** Xcode build errors mentioning architecture

### Pitfall 3: Android Min SDK Too Low
**What goes wrong:** WebRTC fails to initialize
**Why it happens:** flutter_webrtc requires minSdkVersion 23
**How to avoid:** Set in android/app/build.gradle: `minSdkVersion 23`
**Warning signs:** Runtime crash with "method not found" or similar

### Pitfall 4: Not Handling Permission Denial
**What goes wrong:** App crashes or silently fails
**Why it happens:** iOS/Android require runtime microphone permission
**How to avoid:** Always check and request Permission.microphone before getUserMedia
**Warning signs:** getUserMedia returns error, no audio

### Pitfall 5: Missing Info.plist Usage Descriptions
**What goes wrong:** Permission denied immediately on iOS
**Why it happens:** iOS requires usage description strings
**How to avoid:** Add to ios/Runner/Info.plist:
```xml
<key>NSMicrophoneUsageDescription</key>
<string>Ergos needs microphone access for voice interaction</string>
```
**Warning signs:** Permission.microphone returns permanentlyDenied immediately

### Pitfall 6: Not Handling Connection State Changes
**What goes wrong:** App hangs when connection fails
**Why it happens:** WebRTC connection can fail silently
**How to avoid:** Listen to `onConnectionState` and handle failed/disconnected
**Warning signs:** App appears connected but no audio flows

### Pitfall 7: VAD Frame Size Mismatch
**What goes wrong:** VAD never detects speech or false positives
**Why it happens:** Silero VAD v5 requires exactly 512 samples (32ms at 16kHz)
**How to avoid:** Use `frameSamples: 512` for v5, `frameSamples: 1536` for legacy
**Warning signs:** onSpeechStart never fires or fires constantly
</common_pitfalls>

<code_examples>
## Code Examples

Verified patterns from official sources:

### WebRTC Connection Setup
```dart
// Source: flutter-webrtc API docs + server interface
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class WebRTCClient {
  RTCPeerConnection? _pc;
  RTCDataChannel? _dataChannel;
  MediaStream? _localStream;

  Future<void> connect(String serverUrl) async {
    // Request microphone permission first
    final audioConstraints = {
      'audio': true,
      'video': false,
    };

    _localStream = await navigator.mediaDevices.getUserMedia(audioConstraints);

    // Create peer connection with STUN
    _pc = await createPeerConnection({
      'iceServers': [
        {'urls': 'stun:stun.l.google.com:19302'}
      ],
    });

    // Handle incoming audio track (server TTS)
    _pc!.onTrack = (RTCTrackEvent event) {
      if (event.track.kind == 'audio') {
        // Audio plays automatically through device speaker
        print('Received server audio track');
      }
    };

    // Add local audio track
    for (var track in _localStream!.getAudioTracks()) {
      await _pc!.addTrack(track, _localStream!);
    }

    // Create data channel BEFORE offer (critical!)
    _dataChannel = await _pc!.createDataChannel(
      'data',
      RTCDataChannelInit()..ordered = true,
    );

    // Handle incoming messages
    _dataChannel!.onMessage = (RTCDataChannelMessage msg) {
      final data = jsonDecode(msg.text);
      print('Server message: ${data['type']}');
    };

    // Create and send offer
    RTCSessionDescription offer = await _pc!.createOffer({
      'offerToReceiveAudio': true,
      'offerToReceiveVideo': false,
    });
    await _pc!.setLocalDescription(offer);

    // Exchange SDP with server
    final response = await http.post(
      Uri.parse('$serverUrl/offer'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'sdp': offer.sdp, 'type': offer.type}),
    );

    final answer = jsonDecode(response.body);
    await _pc!.setRemoteDescription(
      RTCSessionDescription(answer['sdp'], answer['type']),
    );
  }

  void sendVADEvent(String event, {double? probability, double? durationMs}) {
    if (_dataChannel?.state == RTCDataChannelState.RTCDataChannelOpen) {
      _dataChannel!.send(RTCDataChannelMessage(jsonEncode({
        'type': 'vad_event',
        'event': event,
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
        if (probability != null) 'probability': probability,
        if (durationMs != null) 'duration_ms': durationMs,
      })));
    }
  }

  Future<void> disconnect() async {
    await _dataChannel?.close();
    await _pc?.close();
    _localStream?.dispose();
  }
}
```

### VAD Integration
```dart
// Source: vad package documentation
import 'package:vad/vad.dart';

class VADService {
  VadHandler? _vadHandler;
  Function(String event)? onVADEvent;

  Future<void> initialize() async {
    _vadHandler = VadHandler.create(
      mode: VadMode.normal,
      sileroVadModelVersion: SileroVadModelVersion.v5,
      frameSamples: 512,  // Required for v5
      sampleRate: 16000,
      preSpeechPadFrames: 10,
      positiveSpeechThreshold: 0.5,
      negativeSpeechThreshold: 0.35,
    );

    _vadHandler!.onSpeechStart.listen((_) {
      onVADEvent?.call('speech_start');
    });

    _vadHandler!.onSpeechEnd.listen((audioSamples) {
      onVADEvent?.call('speech_end');
    });

    _vadHandler!.onVADMisfire.listen((_) {
      // False positive - ignore
    });
  }

  void startListening() {
    _vadHandler?.startListening();
  }

  void stopListening() {
    _vadHandler?.stopListening();
  }

  void dispose() {
    _vadHandler?.dispose();
  }
}
```

### Permission Handling
```dart
// Source: permission_handler docs
import 'package:permission_handler/permission_handler.dart';

Future<bool> requestMicrophonePermission() async {
  final status = await Permission.microphone.status;

  if (status.isGranted) {
    return true;
  }

  if (status.isDenied) {
    final result = await Permission.microphone.request();
    return result.isGranted;
  }

  if (status.isPermanentlyDenied) {
    // Direct user to settings
    await openAppSettings();
    return false;
  }

  return false;
}
```
</code_examples>

<sota_updates>
## State of the Art (2025-2026)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual audio recording + WebRTC | flutter_webrtc getUserMedia | Standard | One library handles both |
| Custom VAD algorithms | Silero VAD ONNX via vad package | 2024 | Cross-platform ML-based VAD |
| WebSocket signaling | HTTP POST signaling | Standard | Simpler for offer/answer pattern |
| Separate audio player | WebRTC remote track playback | Standard | Audio plays automatically |

**New tools/patterns to consider:**
- **vad package v5 model:** Improved accuracy, requires 512 sample frames (32ms)
- **flutter_webrtc 1.3.0:** Audio-only mode support, better iOS compatibility

**Deprecated/outdated:**
- **Manual WebSocket for signaling:** HTTP POST is simpler for one-shot offer/answer
- **flutter_silero_vad:** Less maintained than vad package
- **Custom audio buffering:** WebRTC handles all audio buffering internally
</sota_updates>

<server_integration>
## Server Integration Notes

**Existing Server Interface (from Phase 8):**

The Python aiortc server exposes:
- **POST /offer:** Accepts SDP offer, returns SDP answer
  - Request: `{"sdp": "...", "type": "offer"}`
  - Response: `{"sdp": "...", "type": "answer"}`

- **Data Channel Protocol:**
  - Client sends: `{"type": "vad_event", "event": "speech_start"|"speech_end", "timestamp": float}`
  - Server sends: `{"type": "state_change", "state": "IDLE"|"LISTENING"|"PROCESSING"|"SPEAKING", "previous": "..."}`

- **Audio:**
  - Client → Server: Microphone audio via WebRTC audio track
  - Server → Client: TTS audio via TTSAudioTrack (24kHz Opus)

**No changes needed on server side - Flutter client just needs to implement the client side of this protocol.**
</server_integration>

<open_questions>
## Open Questions

1. **VAD integration with WebRTC audio:**
   - What we know: vad package can use built-in microphone or custom stream
   - What's unclear: Best way to feed WebRTC captured audio to VAD
   - Recommendation: Use vad package built-in microphone capture (separate from WebRTC), send VAD events over data channel

2. **Audio playback from remote track:**
   - What we know: flutter_webrtc plays remote audio automatically
   - What's unclear: Controlling volume, speaker vs earpiece
   - Recommendation: Use `Helper.setSpeakerphoneOn(true)` for loudspeaker output
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- [flutter_webrtc pub.dev](https://pub.dev/packages/flutter_webrtc) - v1.3.0, platform support, features
- [vad pub.dev](https://pub.dev/packages/vad) - Silero VAD wrapper, configuration
- [Flutter WebRTC Community Docs](https://flutter-webrtc.org/docs/flutter-webrtc/api-docs/rtc-data-channel/) - Data channel API
- [permission_handler pub.dev](https://pub.dev/packages/permission_handler) - Permission management

### Secondary (MEDIUM confidence)
- [Flutter-WebRTC Guide (100ms)](https://www.100ms.live/blog/flutter-webrtc) - Verified patterns
- [Flutter-aiortc Demo (GitHub)](https://github.com/jcrisp88/flutter-webrtc_python-aiortc-opencv) - Flutter to aiortc connection
- [Flutter WebRTC Demo](https://github.com/flutter-webrtc/flutter-webrtc-demo) - Official examples

### Tertiary (LOW confidence - validated during implementation)
- [mic_stream pub.dev](https://pub.dev/packages/mic_stream) - Alternative audio capture
- [record pub.dev](https://pub.dev/packages/record) - Alternative recording
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Flutter, WebRTC, audio streaming
- Ecosystem: flutter_webrtc, vad, permission_handler
- Patterns: WebRTC signaling, data channel messaging, VAD integration
- Pitfalls: iOS/Android configuration, permission handling, data channel timing

**Confidence breakdown:**
- Standard stack: HIGH - verified with pub.dev, official docs
- Architecture: HIGH - from official examples and demo repos
- Pitfalls: HIGH - from GitHub issues and official troubleshooting
- Code examples: HIGH - from official sources, adapted for server interface

**Research date:** 2026-01-26
**Valid until:** 2026-02-26 (30 days - Flutter WebRTC ecosystem stable)
</metadata>

---

*Phase: 09-flutter-client-core*
*Research completed: 2026-01-26*
*Ready for planning: yes*
