package me.remember.app.data.repository

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** DeepSeek adapter used only for short title generation. No chain-of-thought is requested. */
class DeepSeekTitleGenerator(
    private val apiKey: String,
    private val model: String = "deepseek-flash"
) : TitleGenerator {
    override suspend fun generateTitle(transcript: String): String = withContext(Dispatchers.IO) {
        val text = transcript.replace(Regex("\\s+"), " ").trim()
        if (text.isBlank()) return@withContext "未命名录音"
        require(apiKey.isNotBlank()) { "DeepSeek title model is not configured." }
        val request = JSONObject().apply {
            put("model", model)
            put("temperature", 0.0)
            put("max_tokens", 32)
            put("thinking", JSONObject().put("type", "disabled"))
            put("messages", JSONArray().apply {
                put(JSONObject().put("role", "system").put("content", "你是录音标题生成器。只输出一个简洁、准确、自然的中文标题，不要解释，不要引号，不要编号，不超过24个汉字。"))
                put(JSONObject().put("role", "user").put("content", "请根据下面的录音转写生成标题：\\n$text"))
            })
        }
        val connection = (URL("https://api.deepseek.com/v1/chat/completions").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("Authorization", "Bearer $apiKey")
            setRequestProperty("Content-Type", "application/json")
        }
        connection.outputStream.use { it.write(request.toString().toByteArray(Charsets.UTF_8)) }
        val body = (if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (connection.responseCode !in 200..299) error("DeepSeek title request failed (${connection.responseCode}).")
        val content = JSONObject(body).getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").optString("content")
        content.replace(Regex("^[\\\"'“”‘’]+|[\\\"'“”‘’]+$"), "")
            .replace(Regex("\\s+"), " ").trim().take(24).ifBlank { "未命名录音" }
    }
}
