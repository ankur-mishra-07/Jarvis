package com.jarvis.shared.wake

/** iOS wake-word stub. Replace with `ai.picovoice:porcupine-ios` integration. */
actual class WakeWordEngine {
    actual suspend fun start(accessKey: String, onWake: () -> Unit) { /* TODO */ }
    actual fun stop() { /* TODO */ }
}
