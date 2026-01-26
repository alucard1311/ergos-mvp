import 'package:permission_handler/permission_handler.dart';

/// Requests microphone permission from the user.
///
/// Returns true if permission is granted, false otherwise.
/// If permission is permanently denied, opens app settings.
Future<bool> requestMicrophonePermission() async {
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
