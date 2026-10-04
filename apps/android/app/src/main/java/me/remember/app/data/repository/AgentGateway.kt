package me.remember.app.data.repository

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import me.remember.app.BuildConfig
import org.json.JSONObject
import java.io.IOException
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL

interface AgentGateway {
    suspend fun request(connection: BackendConnection, path: String, method: String = "GET", body: JSONObject? = null): JSONObject
}

/** Server adapter only: no STT/LLM vendor or provider credential reaches Android. */
class HttpAgentGateway : AgentGateway {
    override suspend fun request(connection: BackendConnection, path: String, method: String, body: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        val uri = runCatching { URI(connection.baseUrl.trim()) }.getOrNull()
        if (uri == null || uri.host.isNullOrBlank() || uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null ||
            uri.path !in setOf("", "/") || (uri.scheme != "https" && !(uri.scheme == "http" && (BuildConfig.DEBUG || uri.host in setOf("localhost", "127.0.0.1"))))) {
            throw EpisodeGatewayFailure("CONFIG_INVALID", "请填写有效的 Backend 地址。", false)
        }
        if (connection.actorToken.isBlank() || !connection.subjectId.matches(Regex("[A-Za-z0-9._~-]+"))) {
            throw EpisodeGatewayFailure("CONFIG_INVALID", "Actor Token 或 Subject ID 无效。", false)
        }
        val endpoint = uri.toString().trimEnd('/') + "/experimental/agent/v1/subjects/" + connection.subjectId + path
        val http = URL(endpoint).openConnection() as HttpURLConnection
        http.requestMethod = method
        http.connectTimeout = 10_000
        http.readTimeout = 120_000 // compare + persona are two bounded server-side workers
        http.instanceFollowRedirects = false
        http.setRequestProperty("Authorization", "Bearer ${connection.actorToken}")
        http.setRequestProperty("Accept", "application/json")
        try {
            if (body != null) {
                http.doOutput = true
                http.setRequestProperty("Content-Type", "application/json")
                http.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = http.responseCode
            val stream = if (code in 200..299) http.inputStream else http.errorStream
            val bytes = stream?.use { input ->
                val out = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (out.size() + count > 1_048_576) throw EpisodeGatewayFailure("INVALID_RESPONSE", "Backend 响应过大。", false)
                    out.write(buffer, 0, count)
                }
                out.toByteArray()
            } ?: byteArrayOf()
            if (bytes.size > 1_048_576) throw EpisodeGatewayFailure("INVALID_RESPONSE", "Backend 响应过大。", false)
            val text = bytes.toString(Charsets.UTF_8)
            val json = if (code == 204) JSONObject() else runCatching { JSONObject(text) }.getOrNull()
            if (code !in 200..299) throw EpisodeGatewayFailure(json?.optString("error_code") ?: "HTTP_$code",
                json?.optString("error_message") ?: "Backend HTTP $code", code == 408 || code == 429 || code >= 500)
            json ?: throw EpisodeGatewayFailure("INVALID_RESPONSE", "Backend 返回的 JSON 无效。", false)
        } catch (error: IOException) {
            throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "网络中断，可以重试；已锁定的答案仍在服务端。", true)
        } finally { http.disconnect() }
    }
}
