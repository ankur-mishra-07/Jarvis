package com.jarvis.shared.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ChatRequest(
    val text: String,
    @SerialName("session_id") val sessionId: String,
)

@Serializable
data class ChatResponse(
    val reply: String,
    @SerialName("session_id") val sessionId: String,
)

@Serializable
data class TtsRequest(
    val text: String,
    val voice: String? = null,
)

@Serializable
sealed class WsEvent {
    @Serializable @SerialName("start")
    data class Start(@SerialName("sample_rate") val sampleRate: Int, @SerialName("session_id") val sessionId: String) : WsEvent()

    @Serializable @SerialName("end")
    data object End : WsEvent()

    @Serializable @SerialName("partial")
    data class Partial(val text: String) : WsEvent()

    @Serializable @SerialName("final")
    data class Final(val text: String) : WsEvent()

    @Serializable @SerialName("reply")
    data class Reply(val text: String) : WsEvent()

    @Serializable @SerialName("audio_meta")
    data class AudioMeta(val mime: String) : WsEvent()

    @Serializable @SerialName("done")
    data object Done : WsEvent()

    @Serializable @SerialName("error")
    data class Error(val message: String) : WsEvent()
}
