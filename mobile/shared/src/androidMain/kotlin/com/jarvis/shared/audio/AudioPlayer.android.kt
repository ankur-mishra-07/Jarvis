package com.jarvis.shared.audio

import android.media.MediaPlayer
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.resume

actual class AudioPlayer {
    private var player: MediaPlayer? = null

    actual suspend fun play(bytes: ByteArray, mime: String) {
        val ext = if ("mpeg" in mime) ".mp3" else ".wav"
        val tmp = File.createTempFile("jarvis_tts", ext)
        FileOutputStream(tmp).use { it.write(bytes) }
        suspendCancellableCoroutine<Unit> { cont ->
            val mp = MediaPlayer().apply {
                setDataSource(tmp.absolutePath)
                setOnCompletionListener {
                    runCatching { release() }
                    tmp.delete()
                    if (cont.isActive) cont.resume(Unit)
                }
                setOnErrorListener { _, _, _ ->
                    runCatching { release() }
                    tmp.delete()
                    if (cont.isActive) cont.resume(Unit)
                    true
                }
                prepare()
                start()
            }
            player = mp
            cont.invokeOnCancellation { runCatching { mp.release() }; tmp.delete() }
        }
    }

    actual fun stop() {
        player?.runCatching { stop() }
        player?.runCatching { release() }
        player = null
    }
}
