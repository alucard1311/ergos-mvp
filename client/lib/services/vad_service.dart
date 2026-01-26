import 'dart:async';
import 'package:vad/vad.dart';

import '../models/vad_event.dart';

/// Service for Voice Activity Detection using Silero VAD v5.
///
/// Detects when the user starts and stops speaking, emitting VADEvents
/// that can be sent to the server via WebRTC data channel.
class VADService {
  /// The VAD handler from the vad package.
  VadHandlerBase? _vadHandler;

  /// Callback invoked when a VAD event occurs (speech_start or speech_end).
  void Function(VADEvent)? onVADEvent;

  /// Tracks when speech started for duration calculation.
  DateTime? _speechStartTime;

  /// Subscription for speech start events.
  StreamSubscription<void>? _speechStartSub;

  /// Subscription for speech end events.
  StreamSubscription<List<double>>? _speechEndSub;

  /// Subscription for VAD misfire events.
  StreamSubscription<void>? _misfireSub;

  /// Whether the service has been initialized.
  bool _isInitialized = false;

  /// Initializes the VAD service with Silero VAD v5 configuration.
  ///
  /// Creates the VAD handler and sets up event listeners.
  Future<void> initialize() async {
    if (_isInitialized) return;

    _vadHandler = VadHandler.create(
      isDebug: false,
    );

    // Set up onSpeechStart listener
    _speechStartSub = _vadHandler!.onSpeechStart.listen((_) {
      _speechStartTime = DateTime.now();
      final event = VADEvent.speechStart();
      onVADEvent?.call(event);
      print('VAD: Speech started');
    });

    // Set up onSpeechEnd listener
    _speechEndSub = _vadHandler!.onSpeechEnd.listen((_) {
      double? durationMs;
      if (_speechStartTime != null) {
        durationMs = DateTime.now()
            .difference(_speechStartTime!)
            .inMilliseconds
            .toDouble();
        _speechStartTime = null;
      }
      final event = VADEvent.speechEnd(durationMs: durationMs);
      onVADEvent?.call(event);
      print('VAD: Speech ended (duration: ${durationMs?.toStringAsFixed(0)}ms)');
    });

    // Set up onVADMisfire listener (ignore false positives)
    _misfireSub = _vadHandler!.onVADMisfire.listen((_) {
      _speechStartTime = null;
      print('VAD: Misfire (false positive ignored)');
    });

    _isInitialized = true;
  }

  /// Starts listening for speech via the device microphone.
  ///
  /// CRITICAL: Uses frameSamples: 512 which is required for Silero VAD v5.
  /// Using the wrong frame size will cause VAD to not detect speech properly.
  Future<void> startListening() async {
    if (_vadHandler == null) {
      print('VAD: Handler not initialized, call initialize() first');
      return;
    }
    await _vadHandler!.startListening(
      model: 'v5',
      frameSamples: 512, // CRITICAL: Required for v5 (32ms frames at 16kHz)
      positiveSpeechThreshold: 0.5,
      negativeSpeechThreshold: 0.35,
      preSpeechPadFrames: 10,
    );
    print('VAD: Started listening');
  }

  /// Stops listening for speech.
  Future<void> stopListening() async {
    await _vadHandler?.stopListening();
    _speechStartTime = null;
    print('VAD: Stopped listening');
  }

  /// Disposes the VAD handler and releases resources.
  Future<void> dispose() async {
    await _speechStartSub?.cancel();
    await _speechEndSub?.cancel();
    await _misfireSub?.cancel();
    _speechStartSub = null;
    _speechEndSub = null;
    _misfireSub = null;
    await _vadHandler?.dispose();
    _vadHandler = null;
    _speechStartTime = null;
    _isInitialized = false;
  }
}
