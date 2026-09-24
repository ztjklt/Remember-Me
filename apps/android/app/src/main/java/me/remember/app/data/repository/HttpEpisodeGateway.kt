package me.remember.app.data.repository

import me.remember.app.BuildConfig
import me.remember.app.model.Memory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.UUID

/** The only Android transport for the Phase 1 Backend boundary. */
class HttpEpisodeGateway : EpisodeGateway {
    override suspend fun upload(
        recording: AudioRecording,
        connection: BackendConnection,
        onProgress: (Int) -> Unit
    ): EpisodeCreated = withContext(Dispatchers.IO) {
        val file = File(recording.audioPath)
        if (!file.isFile || file.length() == 0L || !recording.mimeType.startsWith("audio/")) {
            throw EpisodeGatewayFailure("AUDIO_INVALID", "保存的音频不可读取或格式不受支持。", false)
        }
        val boundary = "remember-${UUID.randomUUID()}"
        val request = open(connection, "/api/v1/episodes", "POST")
        request.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        request.doOutput = true
        request.setChunkedStreamingMode(64 * 1024)
        try {
            onProgress(0)
            request.outputStream.use { output ->
                val fields = linkedMapOf(
                    "subject_id" to connection.subjectId,
                    "recording_consent_id" to connection.recordingConsentId,
                    "idempotency_key" to idempotencyKeyFor(recording),
                    "source" to "ANDROID_MIC",
                    "recorded_at" to recording.createdAt,
                    "audio_ref" to file.name,
                    "duration_ms" to recording.durationMillis.toString(),
                    "metadata" to JSONObject()
                        .put("sample_rate", recording.sampleRate)
                        .put("channel_count", recording.channelCount)
                        .put("byte_size", file.length())
                        .toString()
                )
                fields.forEach { (name, value) ->
                    output.writeText("--$boundary\r\n")
                    output.writeText("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
                    output.writeText(value)
                    output.writeText("\r\n")
                }
                val safeName = file.name.replace(Regex("[^A-Za-z0-9._-]"), "_")
                output.writeText("--$boundary\r\n")
                output.writeText("Content-Disposition: form-data; name=\"file\"; filename=\"$safeName\"\r\n")
                output.writeText("Content-Type: ${recording.mimeType}\r\n\r\n")
                val total = file.length()
                var sent = 0L
                file.inputStream().use { input ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        sent += count
                        onProgress((sent * 100 / total).toInt().coerceIn(0, 100))
                    }
                }
                output.writeText("\r\n--$boundary--\r\n")
            }
            val body = readResponse(request, setOf(200, 201))
            body.allowOnly("episode_id", "upload_status")
            val uploadStatus = body.requiredString("upload_status")
            if (uploadStatus !in setOf("pending", "uploading", "uploaded", "failed")) {
                invalidResponse("Unknown upload_status")
            }
            EpisodeCreated(body.requiredString("episode_id"), uploadStatus)
        } catch (error: IOException) {
            throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "上传连接中断，请检查网络后重试。", true)
        } finally {
            request.disconnect()
        }
    }

    override suspend fun status(
        episodeId: String,
        connection: BackendConnection
    ): EpisodeStatus = withContext(Dispatchers.IO) {
        val request = open(connection, "/api/v1/episodes/${episodeId.pathSegment()}", "GET")
        try {
            val body = readResponse(request, setOf(200))
            body.allowOnly("episode_id", "trace_id", "status", "progress", "error_code", "error_message")
            if (body.requiredString("episode_id") != episodeId) invalidResponse("Episode id changed")
            val stage = try {
                EpisodeStage.valueOf(body.requiredString("status").uppercase())
            } catch (_: IllegalArgumentException) {
                invalidResponse("Unknown processing status")
            }
            EpisodeStatus(
                episodeId,
                stage,
                body.optionalString("error_code"),
                body.optionalString("error_message")
            )
        } catch (error: IOException) {
            throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "无法获取处理状态，请检查网络后重试。", true)
        } finally {
            request.disconnect()
        }
    }

    override suspend fun result(
        episodeId: String,
        connection: BackendConnection
    ): EpisodeResult = withContext(Dispatchers.IO) {
        val request = open(connection, "/api/v1/episodes/${episodeId.pathSegment()}/result", "GET")
        try {
            val body = readResponse(request, setOf(200))
            body.allowOnly("episode_id", "status", "memory_items", "model_version", "trace_id")
            if (body.requiredString("episode_id") != episodeId || body.requiredString("status") != "ready") {
                invalidResponse("Result is not for the ready Episode")
            }
            val modelVersion = body.requiredString("model_version")
            val items = body.requiredArray("memory_items")
            val memories = (0 until items.length()).map { index ->
                val item = items.optJSONObject(index) ?: invalidResponse("Memory item is not an object")
                item.allowOnly(
                    "memory_type", "content", "source_type", "evidence_ids", "confidence",
                    "model_version", "prompt_version", "schema_version", "effective_at", "metadata"
                )
                val memoryType = item.requiredString("memory_type")
                if (memoryType !in setOf("EVENT", "PERSON", "RELATIONSHIP", "PREFERENCE", "VALUE", "EMOTION")) {
                    invalidResponse("Unknown memory_type")
                }
                val sourceType = item.requiredString("source_type")
                if (sourceType !in setOf("SUBJECT", "THIRD_PARTY", "AI_INFERENCE", "OBJECTIVE", "CALIBRATION")) {
                    invalidResponse("Unknown source_type")
                }
                val evidence = item.requiredArray("evidence_ids").strings()
                if (evidence.isEmpty() || evidence.distinct().size != evidence.size) {
                    invalidResponse("Memory evidence_ids are missing or duplicated")
                }
                val confidence = item.requiredNumber("confidence")
                if (confidence !in 0.0..1.0) invalidResponse("Memory confidence is out of range")
                Memory(
                    id = "$episodeId:$index",
                    date = item.optionalString("effective_at")?.take(10).orEmpty(),
                    place = "",
                    story = item.requiredString("content"),
                    people = emptyList(),
                    tags = emptyList(),
                    duration = "",
                    episodeId = episodeId,
                    memoryType = memoryType,
                    sourceType = sourceType,
                    evidenceIds = evidence,
                    confidence = confidence,
                    modelVersion = item.requiredString("model_version"),
                    promptVersion = item.requiredString("prompt_version"),
                    schemaVersion = item.requiredString("schema_version"),
                    hasPlayableAudio = false
                )
            }
            EpisodeResult(episodeId, modelVersion, memories)
        } catch (error: IOException) {
            throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "无法读取处理结果，请检查网络后重试。", true)
        } finally {
            request.disconnect()
        }
    }

    private fun open(connection: BackendConnection, path: String, method: String): HttpURLConnection {
        val endpoint = validatedBaseUrl(connection.baseUrl) + path
        if (connection.actorToken.isBlank() || connection.subjectId.isBlank() || connection.recordingConsentId.isBlank()) {
            throw EpisodeGatewayFailure("CONFIG_REQUIRED", "请填写 Actor Token、Subject ID 和录音同意 ID。", false)
        }
        return (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = 30_000
            setRequestProperty("Authorization", "Bearer ${connection.actorToken.trim()}")
            setRequestProperty("Accept", "application/json")
        }
    }

    private fun readResponse(request: HttpURLConnection, successCodes: Set<Int>): JSONObject {
        val code = request.responseCode
        val stream = if (code in successCodes) request.inputStream else request.errorStream
        val text = stream?.use { it.readBoundedText() }.orEmpty()
        if (code !in successCodes) {
            val error = runCatching { JSONObject(text) }.getOrNull()
            val errorCode = error?.optString("error_code")?.takeIf { it.isNotBlank() } ?: "HTTP_$code"
            val message = error?.optString("error_message")?.takeIf { it.isNotBlank() }
                ?: "Backend returned HTTP $code"
            throw EpisodeGatewayFailure(errorCode, message, code == 408 || code == 429 || code >= 500)
        }
        return try {
            JSONObject(text)
        } catch (_: JSONException) {
            invalidResponse("Backend response is not JSON")
        }
    }
}

internal fun idempotencyKeyFor(recording: AudioRecording): String {
    val digest = MessageDigest.getInstance("SHA-256")
        .digest(File(recording.audioPath).absolutePath.toByteArray(StandardCharsets.UTF_8))
    return "android-" + digest.joinToString("") { "%02x".format(it) }
}

private fun validatedBaseUrl(raw: String): String {
    val uri = try { URI(raw.trim()) } catch (_: Exception) { null }
    val local = uri?.host in setOf("localhost", "127.0.0.1")
    if (uri == null || uri.host.isNullOrBlank() || uri.rawUserInfo != null ||
        uri.rawQuery != null || uri.rawFragment != null || uri.path !in setOf("", "/") ||
        (uri.scheme != "https" && !(uri.scheme == "http" && (BuildConfig.DEBUG || local)))
    ) {
        throw EpisodeGatewayFailure("CONFIG_INVALID", "Backend 地址需是有效的 HTTPS 地址；Debug 构建可用 HTTP。", false)
    }
    return uri.toString().trimEnd('/')
}

private fun String.pathSegment(): String {
    if (isBlank() || !matches(Regex("[A-Za-z0-9._~-]+"))) {
        throw EpisodeGatewayFailure("EPISODE_INVALID", "Episode ID 格式无效。", false)
    }
    return this
}

private fun java.io.OutputStream.writeText(value: String) {
    write(value.toByteArray(StandardCharsets.UTF_8))
}

private fun InputStream.readBoundedText(): String {
    val output = ByteArrayOutputStream()
    val buffer = ByteArray(8 * 1024)
    while (true) {
        val count = read(buffer)
        if (count < 0) break
        if (output.size() + count > 1024 * 1024) invalidResponse("Backend response is too large")
        output.write(buffer, 0, count)
    }
    return output.toString(StandardCharsets.UTF_8.name())
}

private fun invalidResponse(problem: String): Nothing =
    throw EpisodeGatewayFailure("INVALID_RESPONSE", problem, false)

private fun JSONObject.allowOnly(vararg names: String) {
    val allowed = names.toSet()
    if (keys().asSequence().any { it !in allowed }) invalidResponse("Backend response has unknown fields")
}

private fun JSONObject.requiredString(name: String): String {
    val value = opt(name)
    if (value !is String || value.isBlank()) invalidResponse("Missing or invalid $name")
    return value
}

private fun JSONObject.optionalString(name: String): String? {
    if (!has(name)) return null
    return requiredString(name)
}

private fun JSONObject.requiredArray(name: String): JSONArray =
    optJSONArray(name) ?: invalidResponse("Missing or invalid $name")

private fun JSONObject.requiredNumber(name: String): Double {
    val value = opt(name)
    if (value !is Number) invalidResponse("Missing or invalid $name")
    return value.toDouble()
}

private fun JSONArray.strings(): List<String> = (0 until length()).map { index ->
    val value = opt(index)
    if (value !is String || value.isBlank()) invalidResponse("Invalid evidence ID")
    value
}
