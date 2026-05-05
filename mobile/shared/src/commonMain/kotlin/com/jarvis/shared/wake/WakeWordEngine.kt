package com.jarvis.shared.wake

/** On-device wake word detector ("Hey Jarvis"). Backed by Porcupine. */
expect class WakeWordEngine() {
    /** Begin listening; [onWake] fires whenever the keyword is detected. */
    suspend fun start(accessKey: String, onWake: () -> Unit)
    fun stop()
}
