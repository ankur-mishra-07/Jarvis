package com.jarvis.shared.ui

import com.jarvis.shared.audio.AudioPlayer
import com.jarvis.shared.audio.AudioRecorder
import com.jarvis.shared.net.JarvisClient
import com.jarvis.shared.net.JarvisWebSocket
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class AssistantPhase { Idle, Listening, Thinking, Speaking }

data class AssistantState(
    val phase: AssistantPhase = AssistantPhase.Idle,
    val transcript: String = "",
    val reply: String = "",
    val error: String? = null,
)

class AssistantViewModel(
    private val client: JarvisClient,
    private val ws: JarvisWebSocket,
    private val recorder: AudioRecorder,
    private val player: AudioPlayer,
    private val sessionId: String,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val _state = MutableStateFlow(AssistantState())
    val state: StateFlow<AssistantState> = _state.asStateFlow()

    private var streamJob: Job? = null

    /** Text-only path (button or quick test). */
    fun sendText(text: String) {
        scope.launch {
            _state.update { it.copy(phase = AssistantPhase.Thinking, transcript = text, error = null) }
            try {
                val resp = client.chat(text, sessionId)
                _state.update { it.copy(phase = AssistantPhase.Speaking, reply = resp.reply) }
                val audio = client.tts(resp.reply)
                player.play(audio, "audio/wav")
            } catch (t: Throwable) {
                _state.update { it.copy(error = t.message ?: "request failed") }
            } finally {
                _state.update { it.copy(phase = AssistantPhase.Idle) }
            }
        }
    }

    /** Voice path: record + stream over WS, play streamed reply audio. */
    fun startVoiceTurn() {
        if (streamJob?.isActive == true) return
        streamJob = scope.launch {
            _state.update { it.copy(phase = AssistantPhase.Listening, error = null) }
            val audioBuffers = mutableListOf<ByteArray>()
            var mime = "audio/wav"

            try {
                ws.openSession(sessionId) { send, end ->
                    recorder.start(sampleRate = 16000) { frame -> send(frame) }
                    end()
                }.collect { ev ->
                    when (ev) {
                        is JarvisWebSocket.Event.Partial ->
                            _state.update { it.copy(transcript = ev.text) }
                        is JarvisWebSocket.Event.Final ->
                            _state.update { it.copy(transcript = ev.text, phase = AssistantPhase.Thinking) }
                        is JarvisWebSocket.Event.Reply ->
                            _state.update { it.copy(reply = ev.text, phase = AssistantPhase.Speaking) }
                        is JarvisWebSocket.Event.AudioMeta -> mime = ev.mime
                        is JarvisWebSocket.Event.AudioChunk -> audioBuffers.add(ev.bytes)
                        JarvisWebSocket.Event.Done -> {
                            val combined = audioBuffers.fold(ByteArray(0)) { acc, b -> acc + b }
                            if (combined.isNotEmpty()) player.play(combined, mime)
                        }
                        is JarvisWebSocket.Event.Error ->
                            _state.update { it.copy(error = ev.message) }
                    }
                }
            } catch (t: Throwable) {
                _state.update { it.copy(error = t.message ?: "stream failed") }
            } finally {
                recorder.stop()
                _state.update { it.copy(phase = AssistantPhase.Idle) }
            }
        }
    }

    fun stopVoiceTurn() {
        recorder.stop()
        streamJob?.cancel()
    }

    fun dispose() {
        streamJob?.cancel()
        recorder.stop()
        player.stop()
        client.close()
        ws.close()
    }
}
