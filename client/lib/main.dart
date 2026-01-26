import 'dart:async';

import 'package:flutter/material.dart';

import 'models/connection_state.dart';
import 'services/signaling_service.dart';
import 'services/vad_service.dart';
import 'services/webrtc_service.dart';

void main() {
  runApp(const ErgosApp());
}

/// Main application widget for Ergos voice assistant.
class ErgosApp extends StatefulWidget {
  const ErgosApp({super.key});

  @override
  State<ErgosApp> createState() => _ErgosAppState();
}

class _ErgosAppState extends State<ErgosApp> {
  /// Server URL for signaling (configurable later).
  final String _serverUrl = 'http://localhost:8080';

  /// WebRTC service for peer connection and data channel.
  late final WebRTCService _webRTCService;

  /// Signaling service for SDP exchange.
  late final SignalingService _signalingService;

  /// VAD service for speech detection.
  late final VADService _vadService;

  /// Current connection state.
  ClientConnectionState _connectionState = ClientConnectionState.disconnected;

  /// Current server state (e.g., "IDLE", "LISTENING").
  String _serverState = 'IDLE';

  /// Whether data channel is ready.
  bool _dataChannelReady = false;

  @override
  void initState() {
    super.initState();

    // Create services
    _signalingService = SignalingService(serverUrl: _serverUrl);
    _webRTCService = WebRTCService(_signalingService);
    _vadService = VADService();

    // Set up WebRTC callbacks
    _webRTCService.onConnectionStateChanged = (state) {
      setState(() {
        _connectionState = state;
      });
      if (state == ClientConnectionState.disconnected ||
          state == ClientConnectionState.failed) {
        unawaited(_vadService.stopListening());
      }
    };

    _webRTCService.onServerStateChanged = (serverState) {
      setState(() {
        _serverState = serverState.state;
      });
    };

    _webRTCService.onDataChannelReady = (isReady) {
      setState(() {
        _dataChannelReady = isReady;
      });
      if (isReady) {
        // Start VAD listening when data channel is ready
        unawaited(_vadService.startListening());
      }
    };

    // Set up VAD callback to send events via WebRTC data channel
    _vadService.onVADEvent = (event) {
      _webRTCService.sendDataChannelMessage(event.toJson());
    };
  }

  /// Connects to the server.
  Future<void> _connect() async {
    try {
      // Initialize VAD service first
      await _vadService.initialize();

      // Connect WebRTC (this triggers the full connection flow)
      await _webRTCService.connect();
    } catch (e) {
      print('Connection error: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Connection failed: $e')),
        );
      }
    }
  }

  /// Disconnects from the server.
  Future<void> _disconnect() async {
    await _vadService.stopListening();
    await _webRTCService.disconnect();
    await _vadService.dispose();
    setState(() {
      _dataChannelReady = false;
      _serverState = 'IDLE';
    });
  }

  @override
  void dispose() {
    unawaited(_vadService.dispose());
    unawaited(_webRTCService.disconnect());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ergos',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: Scaffold(
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.inversePrimary,
          title: const Text('Ergos'),
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Connection state
                Text(
                  'Connection: ${_connectionState.name}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),

                // Data channel state
                Text(
                  'Data Channel: ${_dataChannelReady ? "Ready" : "Not Ready"}',
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 8),

                // Server state
                Text(
                  'Server: $_serverState',
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 24),

                // Server URL
                Text(
                  'Server: $_serverUrl',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Colors.grey,
                      ),
                ),
                const SizedBox(height: 24),

                // Connect/Disconnect button
                ElevatedButton(
                  onPressed: _connectionState == ClientConnectionState.connecting
                      ? null
                      : () {
                          if (_connectionState == ClientConnectionState.connected) {
                            _disconnect();
                          } else {
                            _connect();
                          }
                        },
                  child: Text(
                    _connectionState == ClientConnectionState.connecting
                        ? 'Connecting...'
                        : _connectionState == ClientConnectionState.connected
                            ? 'Disconnect'
                            : 'Connect',
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
