package com.jarvis.shared.net

import com.jarvis.shared.model.ChatRequest
import com.jarvis.shared.model.ChatResponse
import com.jarvis.shared.model.TtsRequest
import io.ktor.client.HttpClient
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.readBytes
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import io.ktor.client.call.body
import kotlinx.serialization.json.Json

class JarvisClient(
    private val baseUrl: String,
    private val apiKey: String,
    httpEngineFactory: () -> HttpClient = { defaultHttpClient() },
) {
    private val http: HttpClient = httpEngineFactory()

    suspend fun chat(text: String, sessionId: String): ChatResponse {
        val resp: HttpResponse = http.post("$baseUrl/chat") {
            header("X-API-Key", apiKey)
            contentType(ContentType.Application.Json)
            setBody(ChatRequest(text, sessionId))
        }
        return resp.body()
    }

    suspend fun tts(text: String, voice: String? = null): ByteArray {
        val resp: HttpResponse = http.post("$baseUrl/tts") {
            header("X-API-Key", apiKey)
            contentType(ContentType.Application.Json)
            setBody(TtsRequest(text, voice))
        }
        return resp.readBytes()
    }

    fun close() {
        http.close()
    }
}

internal fun defaultHttpClient(): HttpClient = HttpClient {
    install(ContentNegotiation) {
        json(Json {
            ignoreUnknownKeys = true
            classDiscriminator = "type"
        })
    }
    install(WebSockets)
}
