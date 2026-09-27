package me.remember.app.data.repository

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class DeepSeekMemoryExtractor(
    private val apiKey: String,
    private val model: String = "deepseek-v4-flash"
) : MemoryExtractor {
    override suspend fun extract(transcript: String, existingModelVersion: String): MemoryExtractionResult = withContext(Dispatchers.IO) {
        require(apiKey.isNotBlank()) { "DeepSeek memory model is not configured." }
        val request = JSONObject().apply {
            put("model", model)
            put("temperature", 0.0)
            put("max_tokens", 1200)
            put("thinking", JSONObject().put("type", "disabled"))
            put("response_format", JSONObject().put("type", "json_object"))
            put("messages", JSONArray().apply {
                put(JSONObject().put("role", "system").put("content", EXTRACTION_PROMPT))
                put(JSONObject().put("role", "user").put("content", "existing_model_version=$existingModelVersion\\ntranscript=\\n$transcript"))
            })
        }
        val connection = (URL("https://api.deepseek.com/v1/chat/completions").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 45_000
            setRequestProperty("Authorization", "Bearer $apiKey")
            setRequestProperty("Content-Type", "application/json")
        }
        connection.outputStream.use { it.write(request.toString().toByteArray(Charsets.UTF_8)) }
        val body = (if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (connection.responseCode !in 200..299) error("Memory extraction failed (${connection.responseCode}).")
        val content = JSONObject(body).getJSONArray("choices").getJSONObject(0).getJSONObject("message").optString("content")
        val result = JSONObject(content)
        val version = result.optString("model_version", "memory-extractor-$model")
        val items = result.optJSONArray("memories") ?: JSONArray()
        val memories = buildList {
            for (i in 0 until items.length()) {
                val item = items.optJSONObject(i) ?: continue
                val text = item.optString("content").trim()
                if (text.isBlank()) continue
                add(ExtractedMemory(UUID.randomUUID().toString(), item.optString("kind", "fact"), text, item.optString("evidence"), item.optDouble("confidence", 0.5).toFloat().coerceIn(0f, 1f), item.optString("source_type", "SUBJECT"), item.optString("status", "active")))
            }
        }
        MemoryExtractionResult(memories, version)
    }

    companion object {
        private const val EXTRACTION_PROMPT = """
You are the Memory Extractor worker for a consent-first personal memory system.
Return JSON only: {\"model_version\":\"...\",\"memories\":[{\"kind\":\"event|person|relationship|preference|value|emotion|decision|expression|fact\",\"content\":\"...\",\"evidence\":\"exact excerpt or empty\",\"confidence\":0.0,\"source_type\":\"SUBJECT|THIRD_PARTY|AI_INFERENCE\",\"status\":\"active\"}]}.
Extract only supported claims. Keep self-report separate from AI inference. Do not invent dates, people, or facts. One item per meaningful claim. Confidence must be between 0 and 1.
"""
    }
}
