import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../models/connection_state.dart';
import '../utils/permissions.dart';
import 'signaling_service.dart';

// Platform channel for native audio control
const _audioChannel = MethodChannel('com.ergos.client/audio');

/// Callback type for connection state changes.
typedef ConnectionStateCallback = void Function(ClientConnectionState state);

/// Callback type for server state changes (received via data channel).
typedef ServerStateCallback = void Function(ServerState state);

/// Callback type for data channel ready state.
typedef DataChannelReadyCallback = void Function(bool isReady);

/// Service for managing WebRTC connections to the server.
///
/// Handles:
/// - Microphone permission and audio capture
/// - Peer connection lifecycle
/// - Data channel messaging
/// - Audio track management
class WebRTCService {
  /// The signaling service for SDP exchange.
  final SignalingService _signalingService;

  /// The WebRTC peer connection.
  RTCPeerConnection? _pc;

  /// The data channel for messaging.
  RTCDataChannel? _dataChannel;

  /// The local audio stream from the microphone.
  MediaStream? _localStream;

  /// The remote audio stream from the server.
  MediaStream? _remoteStream;

  /// Callback for connection state changes.
  ConnectionStateCallback? onConnectionStateChanged;

  /// Callback for server state changes.
  ServerStateCallback? onServerStateChanged;

  /// Callback for data channel ready state.
  DataChannelReadyCallback? onDataChannelReady;

  /// Creates a WebRTCService with the given signaling service.
  WebRTCService(this._signalingService);

  /// Connects to the WebRTC server.
  ///
  /// This method:
  /// 1. Requests microphone permission
  /// 2. Gets local audio stream
  /// 3. Creates peer connection with STUN
  /// 4. Sets up callbacks for connection state and incoming audio
  /// 5. Adds local audio tracks
  /// 6. Creates data channel (BEFORE offer - critical!)
  /// 7. Creates and sends offer
  /// 8. Sets remote description with answer
  ///
  /// Throws an exception if microphone permission is denied.
  Future<void> connect() async {
    onConnectionStateChanged?.call(ClientConnectionState.connecting);

    // 1. Request microphone permission
    final hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
      onConnectionStateChanged?.call(ClientConnectionState.failed);
      throw Exception('Microphone permission denied');
    }

    // 2. Get local audio stream
    // Enable ALL audio processing to maximize microphone gain
    _localStream = await navigator.mediaDevices.getUserMedia({
      'audio': {
        'echoCancellation': true,
        'noiseSuppression': true,
        'autoGainControl': true,
        'channelCount': 1,
      },
      'video': false,
    });

    // Enable speakerphone using native Android AudioManager
    try {
      await _audioChannel.invokeMethod('setSpeakerOn');
      print('Native audio: Speaker enabled via AudioManager');
    } catch (e) {
      print('Native audio error: $e');
    }
    // Also try flutter_webrtc helper
    await Helper.setSpeakerphoneOn(true);
    print('Audio output configured: speaker mode enabled');

    // 3. Create peer connection with STUN
    _pc = await createPeerConnection({
      'iceServers': [
        {'urls': 'stun:stun.l.google.com:19302'}
      ],
    });

    // 4. Set up onConnectionState callback
    _pc!.onConnectionState = (RTCPeerConnectionState state) {
      switch (state) {
        case RTCPeerConnectionState.RTCPeerConnectionStateConnected:
          onConnectionStateChanged?.call(ClientConnectionState.connected);
          break;
        case RTCPeerConnectionState.RTCPeerConnectionStateFailed:
          onConnectionStateChanged?.call(ClientConnectionState.failed);
          break;
        case RTCPeerConnectionState.RTCPeerConnectionStateDisconnected:
        case RTCPeerConnectionState.RTCPeerConnectionStateClosed:
          onConnectionStateChanged?.call(ClientConnectionState.disconnected);
          break;
        default:
          break;
      }
    };

    // 5. Set up onTrack callback for incoming server audio
    _pc!.onTrack = (RTCTrackEvent event) async {
      if (event.track.kind == 'audio') {
        print('Received server audio track: ${event.track.id}');
        print('Track enabled: ${event.track.enabled}, muted: ${event.track.muted}');

        // Add the remote track to a stream for playback
        if (event.streams.isNotEmpty) {
          _remoteStream = event.streams[0];
          print('Remote stream has ${_remoteStream!.getAudioTracks().length} audio tracks');

          // Ensure all audio tracks are enabled
          for (var track in _remoteStream!.getAudioTracks()) {
            track.enabled = true;
            print('Enabled audio track: ${track.id}');
          }
        }

        // Ensure the track is enabled
        event.track.enabled = true;

        // Configure audio session for playback - route to speaker
        await Helper.setSpeakerphoneOn(true);
        print('Audio configured: speakerphone ON');
      }
    };

    // 6. Add local audio tracks to peer connection
    for (var track in _localStream!.getAudioTracks()) {
      await _pc!.addTrack(track, _localStream!);
    }

    // 7. Create data channel BEFORE offer (CRITICAL!)
    // This must happen before createOffer() or the server won't see it
    _dataChannel = await _pc!.createDataChannel(
      'data',
      RTCDataChannelInit()..ordered = true,
    );

    // 8. Set up data channel onMessage handler
    _dataChannel!.onMessage = (RTCDataChannelMessage message) {
      try {
        print('Received data channel message: ${message.text}');
        final data = jsonDecode(message.text) as Map<String, dynamic>;
        if (data['type'] == 'state_change') {
          final serverState = ServerState.fromJson(data);
          print('State change: ${serverState.state}');
          onServerStateChanged?.call(serverState);
        }
      } catch (e) {
        print('Error parsing data channel message: $e');
      }
    };

    // 9. Set up data channel onDataChannelState
    _dataChannel!.onDataChannelState = (RTCDataChannelState state) {
      final isReady = state == RTCDataChannelState.RTCDataChannelOpen;
      onDataChannelReady?.call(isReady);
    };

    // 10. Create offer with offerToReceiveAudio
    final offer = await _pc!.createOffer({
      'offerToReceiveAudio': true,
      'offerToReceiveVideo': false,
    });

    // 11. Set local description
    await _pc!.setLocalDescription(offer);

    // 12. Send offer via SignalingService, get answer
    final answer = await _signalingService.sendOffer(offer);

    // 13. Set remote description with answer
    await _pc!.setRemoteDescription(answer);
  }

  /// Sends a message over the data channel.
  ///
  /// The message is JSON-encoded before sending.
  /// Does nothing if the data channel is not open.
  void sendDataChannelMessage(Map<String, dynamic> message) {
    if (_dataChannel?.state != RTCDataChannelState.RTCDataChannelOpen) {
      print('Data channel not open, cannot send message');
      return;
    }
    _dataChannel!.send(RTCDataChannelMessage(jsonEncode(message)));
  }

  /// Disconnects from the WebRTC server.
  ///
  /// Closes the data channel, peer connection, and disposes streams.
  Future<void> disconnect() async {
    // Close data channel
    await _dataChannel?.close();
    _dataChannel = null;

    // Close peer connection
    await _pc?.close();
    _pc = null;

    // Dispose streams
    _localStream?.dispose();
    _localStream = null;
    _remoteStream?.dispose();
    _remoteStream = null;

    onConnectionStateChanged?.call(ClientConnectionState.disconnected);
  }
}
