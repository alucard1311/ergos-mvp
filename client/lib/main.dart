import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import 'models/connection_state.dart';
import 'services/signaling_service.dart';
import 'services/vad_service.dart';
import 'services/webrtc_service.dart';
import 'widgets/ergos_orb.dart';

void main() {
  runApp(const ErgosApp());
}

/// Main application widget for Ergos voice assistant.
class ErgosApp extends StatelessWidget {
  const ErgosApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ergos',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const ErgosHomePage(),
    );
  }
}

/// Home page with connection logic.
class ErgosHomePage extends StatefulWidget {
  const ErgosHomePage({super.key});

  @override
  State<ErgosHomePage> createState() => _ErgosHomePageState();
}

class _ErgosHomePageState extends State<ErgosHomePage> {
  /// Server URL for signaling (configurable later).
  /// Use 10.0.2.2 for Android emulator, or your server's IP for real devices.
  final String _serverUrl = 'http://10.0.0.190:8765';

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

  /// Current application mode (normal assistant or kitchen).
  AppMode _appMode = AppMode.normal;

  /// Whether running on desktop (no VAD support).
  bool get _isDesktop =>
      !kIsWeb && (Platform.isLinux || Platform.isWindows || Platform.isMacOS);

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
      if (isReady && !_isDesktop) {
        // Start VAD listening when data channel is ready (mobile only)
        unawaited(_vadService.startListening());
      }
    };

    // Set up VAD callback to send events via WebRTC data channel
    _vadService.onVADEvent = (event) {
      print('Sending VAD event: ${event.toJson()}');
      _webRTCService.sendDataChannelMessage(event.toJson());
    };
  }

  /// Connects to the server.
  Future<void> _connect() async {
    try {
      // Initialize VAD service (skip on desktop - no permission_handler support)
      if (!_isDesktop) {
        await _vadService.initialize();
      } else {
        print('Desktop mode: VAD disabled (use mobile for voice input)');
      }

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

  /// Sends barge-in message to interrupt server speech.
  void _sendBargeIn() {
    if (_serverState == 'SPEAKING') {
      _webRTCService.sendDataChannelMessage({
        'type': 'barge_in',
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
      });
    }
  }

  /// Changes the application mode.
  void _setAppMode(AppMode mode) {
    if (_appMode == mode) return;

    setState(() {
      _appMode = mode;
    });

    // Send mode activation message to server if connected
    if (_connectionState == ClientConnectionState.connected && _dataChannelReady) {
      _webRTCService.sendDataChannelMessage({
        'type': 'mode_change',
        'mode': mode.name,
        'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
      });

      // If switching to kitchen mode, send activation phrase to trigger plugin
      if (mode == AppMode.kitchen) {
        _webRTCService.sendDataChannelMessage({
          'type': 'text_input',
          'text': 'kitchen mode',
          'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
        });
      } else {
        // Exiting kitchen mode
        _webRTCService.sendDataChannelMessage({
          'type': 'text_input',
          'text': 'exit kitchen',
          'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
        });
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
    // Colors for kitchen mode
    final isKitchenMode = _appMode == AppMode.kitchen;
    final backgroundColor = isKitchenMode
        ? const Color(0xFF1A2E1A) // Greenish dark for kitchen
        : const Color(0xFF1A1A2E); // Blueish dark for normal

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        title: Text(isKitchenMode ? 'Ergos Kitchen' : 'Ergos'),
        actions: [
          // Mode indicator icon
          Padding(
            padding: const EdgeInsets.only(right: 16.0),
            child: Icon(
              isKitchenMode ? Icons.restaurant : Icons.assistant,
              color: isKitchenMode ? Colors.green[300] : Colors.blue[300],
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Desktop warning banner
            if (_isDesktop)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                color: Colors.orange.withAlpha(51),
                child: const Text(
                  'Desktop mode: Voice input requires mobile app',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.orange),
                ),
              ),

            // Mode selector
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
              child: SegmentedButton<AppMode>(
                segments: const [
                  ButtonSegment<AppMode>(
                    value: AppMode.normal,
                    label: Text('Assistant'),
                    icon: Icon(Icons.assistant),
                  ),
                  ButtonSegment<AppMode>(
                    value: AppMode.kitchen,
                    label: Text('Kitchen'),
                    icon: Icon(Icons.restaurant),
                  ),
                ],
                selected: {_appMode},
                onSelectionChanged: (Set<AppMode> newSelection) {
                  _setAppMode(newSelection.first);
                },
                style: ButtonStyle(
                  backgroundColor: WidgetStateProperty.resolveWith<Color?>(
                    (Set<WidgetState> states) {
                      if (states.contains(WidgetState.selected)) {
                        return isKitchenMode
                            ? Colors.green.withAlpha(77)
                            : Colors.blue.withAlpha(77);
                      }
                      return null;
                    },
                  ),
                ),
              ),
            ),

            // Mode description
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              child: Text(
                _appMode.description,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.white54,
                    ),
              ),
            ),

            // Main content area with orb
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Animated orb
                    ErgosOrb(
                      serverState: _serverState,
                      onBargeIn: _sendBargeIn,
                      isKitchenMode: isKitchenMode,
                    ),
                    const SizedBox(height: 24),
                    // Tap hint or kitchen mode hint
                    Text(
                      _serverState == 'SPEAKING'
                          ? 'Tap to interrupt'
                          : isKitchenMode && _connectionState == ClientConnectionState.connected
                              ? 'Say "next" to advance steps'
                              : '',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Colors.white70,
                          ),
                    ),
                  ],
                ),
              ),
            ),

            // Status info section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              child: Column(
                children: [
                  Text(
                    'Connection: ${_connectionState.name}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.white54,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Server: $_serverState',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.white54,
                        ),
                  ),
                ],
              ),
            ),

            // Connect/Disconnect button
            Padding(
              padding: const EdgeInsets.all(24.0),
              child: ElevatedButton(
                onPressed: _connectionState == ClientConnectionState.connecting
                    ? null
                    : () {
                        if (_connectionState == ClientConnectionState.connected) {
                          _disconnect();
                        } else {
                          _connect();
                        }
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: isKitchenMode ? Colors.green[700] : null,
                ),
                child: Text(
                  _connectionState == ClientConnectionState.connecting
                      ? 'Connecting...'
                      : _connectionState == ClientConnectionState.connected
                          ? 'Disconnect'
                          : 'Connect',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
