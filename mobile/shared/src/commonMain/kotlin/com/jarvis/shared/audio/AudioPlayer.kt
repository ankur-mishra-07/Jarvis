package com.jarvis.shared.audio

/** Plays back encoded audio bytes (e.g., WAV/MP3) returned by the server. */
expect class AudioPlayer() {
    suspend fun play(bytes: ByteArray, mime: String)
    fun stop()
}
