import 'dart:convert';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

/// Service for HTTP-based signaling with the WebRTC server.
///
/// Handles SDP offer/answer exchange via POST /offer endpoint.
class SignalingService {
  /// The base URL of the signaling server (e.g., "http://192.168.1.100:8080").
  final String serverUrl;

  SignalingService({required this.serverUrl});

  /// Sends an SDP offer to the server and returns the SDP answer.
  ///
  /// Throws an exception if the server returns a non-200 status code.
  Future<RTCSessionDescription> sendOffer(RTCSessionDescription offer) async {
    final response = await http.post(
      Uri.parse('$serverUrl/offer'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'sdp': offer.sdp,
        'type': offer.type,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Signaling failed: ${response.statusCode} - ${response.body}');
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return RTCSessionDescription(
      data['sdp'] as String,
      data['type'] as String,
    );
  }
}
