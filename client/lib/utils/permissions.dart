import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:permission_handler/permission_handler.dart';

/// Whether running on desktop (Linux/Windows/macOS).
bool get _isDesktop =>
    !kIsWeb && (Platform.isLinux || Platform.isWindows || Platform.isMacOS);

/// Requests microphone permission from the user.
///
/// Returns true if permission is granted, false otherwise.
/// On desktop platforms, always returns true (no permission system).
Future<bool> requestMicrophonePermission() async {
  // Desktop platforms don't use permission_handler — mic access is implicit
  if (_isDesktop) {
    return true;
  }

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
