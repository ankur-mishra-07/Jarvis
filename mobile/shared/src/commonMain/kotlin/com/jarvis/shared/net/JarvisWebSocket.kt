package com.jarvis.shared.net

import io.ktor.client.HttpClient
import io.ktor.client.plugins.websocket.DefaultClientWebSocketSession
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.http.HttpMethod
import io.ktor.websocket.Frame
import io.ktor.websocket.readBytes
import io.ktor.websocket.readText
import io.ktor.websocket.send
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Streaming voice session over a single WebSocket. */
class JarvisWebSocket(
    private val baseUrl: String,
    private val apiKey: String,
    httpEngineFactory: () -> HttpClient = { defaultHttpClient() },
) {
    private val http: HttpClient = httpEngineFactory()
    private val json = Json { ignoreUnknownKeys = true }

    sealed class Event {
        data class Partial(val text: String) : Event()
        data class Final(val text: String) : Event()
        data class Reply(val text: String) : Event()
        data class AudioMeta(val mime: String) : Event()
        data class AudioChunk(val bytes: ByteArray) : Event()
        data object Done : Event()
        data class Error(val message: String) : Event()
    }

    /** Open a session, push PCM via [pcmFrames], collect events from the returned flow. */
    suspend fun openSession(
        sessionId: String,
        sampleRate: Int = 16000,
        pcmFrames: suspend (sender: suspend (ByteArray) -> Unit, end: suspend () -> Unit) -> Unit,
    ): Flow<Event> = flow {
        val ws = wsUrl()
        val session: DefaultClientWebSocketSession = http.webSocketSession {
            method = HttpMethod.Get
            url.takeFrom(ws)
            url.parameters.append("api_key", apiKey)
        }

        session.send("""{"type":"start","sample_rate":$sampleRate,"session_id":"$sessionId"}""")

        // Producer fills audio frames; runs concurrently with the consumer below.
        kotlinx.coroutines.coroutineScope {
            val sendJob = kotlinx.coroutines.launch {
                pcmFrames(
                    { bytes -> session.send(Frame.Binary(true, bytes)) },
                    { session.send("""{"type":"end"}""") },
                )
            }

            for (frame in session.incoming) {
                when (frame) {
                    is Frame.Text -> {
                        val obj: JsonObject = json.parseToJsonElement(frame.readText()).jsonObject
                        when (obj["type"]?.jsonPrimitive?.content) {
                            "partial" -> emit(Event.Partial(obj["text"]!!.jsonPrimitive.content))
                            "final" -> emit(Event.Final(obj["text"]!!.jsonPrimitive.content))
                            "reply" -> emit(Event.Reply(obj["text"]!!.jsonPrimitive.content))
                            "audio_meta" -> emit(Event.AudioMeta(obj["mime"]!!.jsonPrimitive.content))
                            "done" -> { emit(Event.Done); break }
                            "error" -> emit(Event.Error(obj["message"]?.jsonPrimitive?.content ?: "unknown"))
                        }
                    }
                    is Frame.Binary -> emit(Event.AudioChunk(frame.readBytes()))
                    else -> Unit
                }
            }
            sendJob.cancel()
            session.close()
        }
    }

    private fun wsUrl(): String = baseUrl
        .replaceFirst("http://", "ws://")
        .replaceFirst("https://", "wss://")
        .trimEnd('/') + "/ws/session"

    fun close() = http.close()
}

private fun io.ktor.http.URLBuilder.takeFrom(s: String) {
    val parsed = io.ktor.http.Url(s)
    protocol = parsed.protocol
    host = parsed.host
    port = parsed.port
    encodedPath = parsed.encodedPath
}
