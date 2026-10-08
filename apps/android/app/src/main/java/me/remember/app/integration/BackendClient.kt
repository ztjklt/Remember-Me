package me.remember.app.integration

import me.remember.app.data.repository.AudioRecording
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder
import java.util.UUID

data class BackendSession(val server: String, val token: String, val epoch: Long)

/** Request snapshots prevent a response from a former identity repopulating the UI. */
class SessionGate {
    @Volatile private var current: BackendSession? = null
    private var epoch = 0L
    @Synchronized fun connect(server: String, token: String): BackendSession {
        require(token.isNotBlank() && !token.contains('\n') && !token.contains('\r')) { "请输入有效身份凭据。" }
        return BackendSession(normalizeServer(server), token.trim(), ++epoch).also { current = it }
    }
    @Synchronized fun advance(): BackendSession = checkNotNull(current).copy(epoch = ++epoch).also { current = it }
    @Synchronized fun clear() { ++epoch; current = null }
    fun accepts(session: BackendSession): Boolean = current == session
    fun requireCurrent(session: BackendSession) { check(accepts(session)) { "身份或空间已切换，请重新操作。" } }
}

fun normalizeServer(raw: String): String {
    val uri = URI(raw.trim())
    require(uri.scheme in setOf("http", "https") && uri.host != null && uri.userInfo == null &&
        uri.query == null && uri.fragment == null && uri.path in listOf("", "/")) { "请输入服务根地址，例如 http://127.0.0.1:8877。" }
    val host = uri.host.lowercase()
    val privateHost = host in setOf("localhost", "127.0.0.1", "[::1]", "::1") ||
        host.matches(Regex("10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}")) ||
        host.matches(Regex("192\\.168\\.\\d{1,3}\\.\\d{1,3}")) ||
        host.matches(Regex("172\\.(1[6-9]|2[0-9]|3[01])\\.\\d{1,3}\\.\\d{1,3}"))
    require(uri.scheme == "https" || privateHost) { "公网服务需要 HTTPS；HTTP 仅支持本机或私有局域网。" }
    return raw.trim().trimEnd('/')
}

class BackendClient(private val gate: SessionGate) {
    fun json(session: BackendSession, path: String, method: String = "GET", body: JSONObject? = null): JSONObject {
        val text = request(session, path, method, if(body != null) "application/json" else null,
            body?.toString()?.toByteArray(Charsets.UTF_8)).toString(Charsets.UTF_8)
        return if (text.isBlank()) JSONObject() else JSONObject(text)
    }
    fun consent(session: BackendSession, subject: String, scope: String): String {
        val values = JSONArray(request(session, "/api/v1/consents?subject_id=${segment(subject)}").toString(Charsets.UTF_8))
        for (i in 0 until values.length()) {
            val c = values.getJSONObject(i)
            if(c.optString("scope") == scope && c.optString("status") == "granted") return c.getString("consent_id")
        }
        return json(session, "/api/v1/consents", "POST", JSONObject().put("subject_id", subject).put("scope", scope)).getString("consent_id")
    }
    fun upload(session: BackendSession, subject: String, consent: String, audio: AudioRecording, key: String, cloudAsrPolicy: String? = null): String {
        val file = File(audio.audioPath)
        require(file.isFile && file.length() > 0) { "本机原音不存在或为空。" }
        val boundary = "remember-${UUID.randomUUID()}"
        val connection = connection(session, "/api/v1/episodes", "POST", "multipart/form-data; boundary=$boundary")
        try {
            connection.setChunkedStreamingMode(64 * 1024)
            connection.outputStream.use { output ->
                fun write(value: String) { output.write(value.toByteArray(Charsets.UTF_8)) }
                val fields = mapOf("subject_id" to subject, "source" to "ANDROID_MIC", "recorded_at" to audio.createdAt,
                    "audio_ref" to file.name, "duration_ms" to audio.durationMillis.toString(),
                    "idempotency_key" to key, "recording_consent_id" to consent,
                    "metadata" to JSONObject().put("capture_client", "native-android").apply {
                        cloudAsrPolicy?.let { put("cloud_asr_policy", it) }
                    }.toString())
                fields.forEach { (name, value) -> write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n") }
                write("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"recording.m4a\"\r\nContent-Type: audio/mp4\r\n\r\n")
                file.inputStream().use { it.copyTo(output) }
                write("\r\n--$boundary--\r\n")
            }
            val response = readResponse(connection)
            gate.requireCurrent(session)
            return JSONObject(response.toString(Charsets.UTF_8)).getString("episode_id")
        } finally { connection.disconnect() }
    }
    fun audio(session: BackendSession, subject: String, episode: String): ByteArray =
        request(session, "$WORKBENCH/${segment(subject)}/stories/${segment(episode)}/audio")

    private fun request(session: BackendSession, path: String, method: String = "GET", type: String? = null, body: ByteArray? = null): ByteArray {
        val c = connection(session, path, method, type)
        try {
            if (body != null) c.outputStream.use { it.write(body) }
            val result = readResponse(c)
            gate.requireCurrent(session)
            return result
        } finally { c.disconnect() }
    }
    private fun connection(session: BackendSession, path: String, method: String, type: String?): HttpURLConnection {
        gate.requireCurrent(session)
        require(path.startsWith("/api/v1/") && !path.contains("\r") && !path.contains("\n"))
        return (URI(session.server + path).toURL().openConnection() as HttpURLConnection).apply {
            requestMethod = method; connectTimeout = 15_000; readTimeout = 65_000
            instanceFollowRedirects = false; useCaches = false
            setRequestProperty("Authorization", "Bearer ${session.token}")
            setRequestProperty("Cache-Control", "no-store")
            if(type != null) { doOutput = true; setRequestProperty("Content-Type", type) }
        }
    }
    private fun readResponse(c: HttpURLConnection): ByteArray {
        val status = c.responseCode
        val bytes = (if(status in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() } ?: byteArrayOf()
        if(status !in 200..299) {
            val parsed = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }.getOrNull()
            val message = parsed?.optJSONObject("error")?.optString("message")?.takeIf { it.isNotBlank() }
                ?: parsed?.optString("detail")?.takeIf { it.isNotBlank() } ?: "服务请求失败（HTTP $status）。"
            throw IllegalStateException(message.take(500))
        }
        return bytes
    }
    companion object { const val WORKBENCH = "/api/v1/workbench/subjects" }
}
fun segment(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20")
fun JSONObject.rows(key: String = "items"): List<JSONObject> = optJSONArray(key)?.let { a ->
    (0 until a.length()).map { a.getJSONObject(it) }
} ?: emptyList()
fun JSONObject.text(key: String): String = if(isNull(key)) "" else optString(key)
