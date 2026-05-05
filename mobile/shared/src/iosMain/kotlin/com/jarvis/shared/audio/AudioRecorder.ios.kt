package com.jarvis.shared.audio

/**
 * iOS recorder stub. Hook up `AVAudioEngine` taps in the Swift layer or via
 * Kotlin/Native cinterop. Kept as a no-op so the shared module compiles for
 * both targets without dragging AVFoundation into commonMain.
 */
actual class AudioRecorder {
    actual suspend fun start(sampleRate: Int, onFrame: suspend (ByteArray) -> Unit) { /* TODO */ }
    actual fun stop() { /* TODO */ }
}
