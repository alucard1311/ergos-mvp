/// Connection states for the WebRTC client.
enum ClientConnectionState {
  disconnected,
  connecting,
  connected,
  failed,
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
      state: json['state'] as String,
      previous: json['previous'] as String,
      timestamp: DateTime.now(),
    );
  }

  @override
  String toString() => 'ServerState(state: $state, previous: $previous)';
}
