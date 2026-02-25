package com.ergos.client

import android.content.Context
import android.media.AudioManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private val CHANNEL = "com.ergos.client/audio"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "setSpeakerOn" -> {
                    val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                    // Use NORMAL mode instead of IN_COMMUNICATION for better mic gain
                    audioManager.mode = AudioManager.MODE_NORMAL
                    audioManager.isSpeakerphoneOn = true
                    // Boost microphone gain to max
                    audioManager.isMicrophoneMute = false
                    // Set stream volumes to max
                    val maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_VOICE_CALL)
                    audioManager.setStreamVolume(AudioManager.STREAM_VOICE_CALL, maxVol, 0)
                    result.success(true)
                }
                "setSpeakerOff" -> {
                    val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                    audioManager.isSpeakerphoneOn = false
                    result.success(true)
                }
                "boostMic" -> {
                    val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
                    audioManager.isMicrophoneMute = false
                    // Try to set communication device to speaker for better mic
                    audioManager.mode = AudioManager.MODE_NORMAL
                    result.success(true)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
    }
}
