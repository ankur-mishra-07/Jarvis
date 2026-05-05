package com.jarvis.shared.wake

/**
 * Android wake-word stub. Replace the body with a real Porcupine integration:
 *
 *   1) Add `implementation("ai.picovoice:porcupine-android:3.0.2")`
 *   2) Ship a `Hey Jarvis` keyword (.ppn) in androidApp/src/main/assets/.
 *   3) Build a PorcupineManager with that key + ppn and call onWake() in its
 *      callback.
 *
 * Until then we no-op so the rest of the app compiles and the manual mic
 * button still works.
 */
actual class WakeWordEngine {
    actual suspend fun start(accessKey: String, onWake: () -> Unit) { /* no-op */ }
    actual fun stop() { /* no-op */ }
}
