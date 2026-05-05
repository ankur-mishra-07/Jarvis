package com.jarvis.shared.audio

/** iOS audio player stub. Real impl uses AVAudioPlayer in the Swift layer. */
actual class AudioPlayer {
    actual suspend fun play(bytes: ByteArray, mime: String) { /* TODO */ }
    actual fun stop() { /* TODO */ }
}
