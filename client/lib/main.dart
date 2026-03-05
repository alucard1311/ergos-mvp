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
  final String _serverUrl = 'http://127.0.0.1:8765';

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

  /// Last transcription received from server.
  String _lastTranscription = '';

  /// Whether meeting recording is active.
  bool _isRecording = false;

  /// Whether LLM endpoint is warming up (cold start).
  bool _isWarmingUp = false;

  /// Active LLM model: "cloud", "local", or empty.
  String _activeModel = '';

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

    _webRTCService.onTranscription = (text) {
      setState(() {
        _lastTranscription = text;
      });
    };

    _webRTCService.onRecordingStatus = (isRecording) {
      setState(() {
        _isRecording = isRecording;
      });
    };

    _webRTCService.onWarmupStatus = (status) {
      setState(() {
        _isWarmingUp = status == 'started';
      });
    };

    _webRTCService.onModelStatus = (model) {
      setState(() {
        _activeModel = model;
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
      print('Sending VAD event: ${event.toJson()}');
      _webRTCService.sendDataChannelMessage(event.toJson());
    };
  }

  /// Connects to the server.
  Future<void> _connect() async {
    try {
      // Initialize VAD service
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

  /// Sends barge-in message to interrupt server speech.
  void _sendBargeIn() {
    if (_serverState == 'SPEAKING' || _serverState == 'SPEAKING_AND_LISTENING') {
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
      _isRecording = false;
      _isWarmingUp = false;
      _activeModel = '';
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
                    // Warm-up indicator
                    if (_isWarmingUp)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16.0),
                        child: _WarmupBadge(),
                      ),
                    // Recording indicator
                    if (_isRecording)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16.0),
                        child: _RecordingBadge(),
                      ),
                    // Animated orb
                    ErgosOrb(
                      serverState: _isWarmingUp ? 'WARMING_UP' : _serverState,
                      onBargeIn: _sendBargeIn,
                      isKitchenMode: isKitchenMode,
                    ),
                    const SizedBox(height: 24),
                    // Tap hint or kitchen mode hint
                    Text(
                      _isWarmingUp
                          ? 'Loading cloud model...'
                          : (_serverState == 'SPEAKING' || _serverState == 'SPEAKING_AND_LISTENING')
                              ? 'Tap to interrupt'
                              : isKitchenMode && _connectionState == ClientConnectionState.connected
                                  ? 'Say "next" to advance steps'
                                  : _isRecording
                                      ? 'Say "save meeting notes" to stop'
                                      : '',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: _isRecording ? Colors.red[300] : Colors.white70,
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
                  if (_activeModel.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: _activeModel == 'cloud'
                                ? Colors.green[400]
                                : Colors.orange[400],
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          _activeModel == 'cloud'
                              ? 'Qwen3-32B (cloud)'
                              : 'Qwen3-8B (local)',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: _activeModel == 'cloud'
                                    ? Colors.green[300]
                                    : Colors.orange[300],
                              ),
                        ),
                      ],
                    ),
                  ],
                  if (_lastTranscription.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      '"$_lastTranscription"',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.white70,
                            fontStyle: FontStyle.italic,
                          ),
                      textAlign: TextAlign.center,
                    ),
                  ],
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

/// Animated warm-up badge with pulsing dot (shown during cloud LLM cold start).
class _WarmupBadge extends StatefulWidget {
  @override
  State<_WarmupBadge> createState() => _WarmupBadgeState();
}

class _WarmupBadgeState extends State<_WarmupBadge>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.orange.withAlpha((140 + 80 * _controller.value).toInt()),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    Colors.white.withAlpha((180 + 75 * _controller.value).toInt()),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                'Warming up...',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Animated red recording badge with pulsing dot.
class _RecordingBadge extends StatefulWidget {
  @override
  State<_RecordingBadge> createState() => _RecordingBadgeState();
}

class _RecordingBadgeState extends State<_RecordingBadge>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.red.withAlpha((180 + 75 * _controller.value).toInt()),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: Colors.white.withAlpha((180 + 75 * _controller.value).toInt()),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 6),
              const Text(
                'REC',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
