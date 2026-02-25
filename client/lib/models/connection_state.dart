/// Connection states for the WebRTC client.
enum ClientConnectionState {
  disconnected,
  connecting,
  connected,
  failed,
}

/// Application modes for different assistant experiences.
enum AppMode {
  /// Normal voice assistant mode.
  normal,

  /// Kitchen cooking assistant mode.
  kitchen,
}

/// Extension to get display names for app modes.
extension AppModeExtension on AppMode {
  String get displayName {
    switch (this) {
      case AppMode.normal:
        return 'Assistant';
      case AppMode.kitchen:
        return 'Kitchen';
    }
  }

  String get description {
    switch (this) {
      case AppMode.normal:
        return 'General voice assistant';
      case AppMode.kitchen:
        return 'Step-by-step cooking guide';
    }
  }
}

/// Represents a state change message from the server.
class ServerState {
  /// The current server state (e.g., "IDLE", "LISTENING", "PROCESSING", "SPEAKING").
  final String state;

  /// The previous server state.
  final String previous;

  /// Timestamp when the state change occurred.
  final DateTime timestamp;

  ServerState({
    required this.state,
    required this.previous,
    required this.timestamp,
  });

  /// Creates a ServerState from a JSON map.
  ///
  /// Expected format:
  /// ```json
  /// {
  ///   "type": "state_change",
  ///   "state": "LISTENING",
  ///   "previous": "IDLE"
  /// }
  /// ```
  factory ServerState.fromJson(Map<String, dynamic> json) {
    return ServerState(
      state: (json['state'] as String).toUpperCase(),
      previous: (json['previous'] as String).toUpperCase(),
      timestamp: DateTime.now(),
    );
  }

  @override
  String toString() => 'ServerState(state: $state, previous: $previous)';
}
