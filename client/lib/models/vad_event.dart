/// Event emitted when Voice Activity Detection detects speech start or end.
class VADEvent {
  /// Event type: "speech_start" or "speech_end"
  final String event;

  /// Timestamp when the event occurred (seconds since epoch).
  final double timestamp;

  /// Optional duration in milliseconds (only for speech_end events).
  final double? durationMs;

  VADEvent({
    required this.event,
    required this.timestamp,
    this.durationMs,
  });

  /// Creates a speech_start event with current timestamp.
  factory VADEvent.speechStart() {
    return VADEvent(
      event: 'speech_start',
      timestamp: DateTime.now().millisecondsSinceEpoch / 1000,
    );
  }

  /// Creates a speech_end event with current timestamp and optional duration.
  factory VADEvent.speechEnd({double? durationMs}) {
    return VADEvent(
      event: 'speech_end',
      timestamp: DateTime.now().millisecondsSinceEpoch / 1000,
      durationMs: durationMs,
    );
  }

  /// Converts this event to a JSON map for data channel transmission.
  ///
  /// Returns:
  /// ```json
  /// {
  ///   "type": "vad_event",
  ///   "event": "speech_start"|"speech_end",
  ///   "timestamp": 1234567890.123
  /// }
  /// ```
  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{
      'type': 'vad_event',
      'event': event,
      'timestamp': timestamp,
    };
    if (durationMs != null) {
      json['duration_ms'] = durationMs;
    }
    return json;
  }

  @override
  String toString() => 'VADEvent(event: $event, timestamp: $timestamp)';
}
