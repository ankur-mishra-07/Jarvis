package com.jarvis.shared.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicBoolean

actual class AudioRecorder {
    private var record: AudioRecord? = null
    private val running = AtomicBoolean(false)

    actual suspend fun start(sampleRate: Int, onFrame: suspend (ByteArray) -> Unit) {
        val minBuf = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        ).coerceAtLeast(2048)

        val rec = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBuf * 2,
        )
        record = rec
        rec.startRecording()
        running.set(true)

        withContext(Dispatchers.IO) {
            val buf = ByteArray(minBuf)
            while (running.get()) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) onFrame(buf.copyOf(n))
            }
        }
    }

    actual fun stop() {
        running.set(false)
        record?.runCatching { stop() }
        record?.runCatching { release() }
        record = null
    }
}
