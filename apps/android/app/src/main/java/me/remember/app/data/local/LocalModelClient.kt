package me.remember.app.data.local

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import me.remember.app.data.repository.AudioRecording
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import kotlin.coroutines.coroutineContext

interface LocalModelClient {
    suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings): String
    suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint): JSONObject
}

/** No Backend dependency. Provider error bodies and credentials are never surfaced or logged. */
class HttpLocalModelClient : LocalModelClient {
    override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings): String = withContext(Dispatchers.IO) {
        val file = File(recording.audioPath)
        require(file.isFile && file.length() in 1..7_500_000 && recording.durationMillis <= 300_000) {
            "请使用不超过 5 分钟、7.5 MB 的录音。原文件仍保留在手机。"
        }
        val format = when (recording.mimeType) {
            "audio/mp4" -> "mp4"; "audio/wav" -> "wav"; "audio/mpeg" -> "mp3"
            else -> error("当前语音适配器不支持此录音格式。")
        }
        val encoded = "data:${recording.mimeType};base64," + Base64.getEncoder().encodeToString(file.readBytes())
        val audio = JSONObject().put("type", "input_audio").put("input_audio", JSONObject().put("data", encoded))
        val messages = JSONArray().put(JSONObject().put("role", "user").put("content", JSONArray().put(audio)))
        val native = settings.protocol == SpeechProtocol.DASHSCOPE
        val body = JSONObject().put("model", settings.speech.model)
        if (native) body.put("input", JSONObject().put("messages", messages)).put("parameters", JSONObject().put("format", format))
        else body.put("messages", messages).put("stream", false)
        val response = post(settings.speech, if (native) "/api/v1/services/aigc/multimodal-generation/generation" else "/chat/completions", body)
        val text = if (native) {
            val output = response.optJSONObject("output")
            output?.opt("text") as? String ?: output?.optJSONObject("output")?.optJSONObject("sentence")?.opt("text") as? String
        } else response.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")?.opt("content") as? String
        require(!text.isNullOrBlank()) { "语音服务没有返回有效原文，请重试。" }
        require(text.length <= 60_000) { "转写超过当前原型容量；原文未被截断。" }
        text.trim()
    }

    override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint): JSONObject {
        require(input.toString().length <= 60_000) { "授权材料超过当前单次容量；请缩小材料范围。系统没有压缩或截断原文。" }
        val messages = JSONArray().put(JSONObject().put("role", "system").put("content", prompt))
            .put(JSONObject().put("role", "user").put("content", input.toString()))
        val result = post(endpoint, "/chat/completions", JSONObject().put("model", endpoint.model)
            .put("messages", messages).put("temperature", 0).put("max_tokens", 4096)
            .put("response_format", JSONObject().put("type", "json_object")))
        return try {
            val choice = result.getJSONArray("choices").getJSONObject(0)
            check(choice.optString("finish_reason") != "length")
            JSONObject(choice.getJSONObject("message").getString("content"))
        } catch (_: Exception) { error("文字模型返回了不完整或无效的 JSON，请重试。") }
    }

    private suspend fun post(endpoint: ModelEndpoint, suffix: String, body: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        endpoint.validate()
        coroutineContext.ensureActive()
        val connection = URL(endpoint.baseUrl.trimEnd('/') + suffix).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 15_000
            connection.readTimeout = 120_000
            connection.doOutput = true
            connection.setRequestProperty("Authorization", "Bearer ${endpoint.apiKey}")
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("X-DashScope-SSE", "disable")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            check(code in 200..299) {
                when (code) {
                    401, 403 -> "模型认证失败（HTTP $code），请检查 Key 和使用权限。"
                    429 -> "模型请求受限（HTTP 429），稍后可重试。"
                    else -> "模型请求失败（HTTP $code），请检查协议、地址和模型。"
                }
            }
            val bytes = connection.inputStream.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    require(output.size() + count <= 2_000_000) { "模型响应超过容量限制。" }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            coroutineContext.ensureActive()
            try { JSONObject(String(bytes, Charsets.UTF_8)) }
            catch (_: Exception) { error("模型服务返回了无效 JSON。") }
        } catch (_: java.io.IOException) { error("模型连接失败或超时，已保存的本地材料不受影响，可重试。") }
        finally { connection.disconnect() }
    }
}
