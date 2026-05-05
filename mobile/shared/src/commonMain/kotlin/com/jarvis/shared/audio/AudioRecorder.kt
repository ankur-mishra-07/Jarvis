package com.jarvis.shared.audio

/** PCM 16-bit mono mic capture. Each platform supplies an actual class. */
expect class AudioRecorder() {
    /** Begin capturing. Frames are delivered via [onFrame] until [stop] is called. */
    suspend fun start(sampleRate: Int = 16000, onFrame: suspend (ByteArray) -> Unit)
    fun stop()
}
