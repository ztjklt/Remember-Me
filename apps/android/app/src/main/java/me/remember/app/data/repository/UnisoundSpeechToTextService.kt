package me.remember.app.data.repository

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Provider adapter. The token is injected at runtime; it is never committed to the app. */
class UnisoundSpeechToTextService(private val apiKey: String) : SpeechToTextService {
    override suspend fun transcribe(audioRef: String): AsrResult = withContext(Dispatchers.IO) {
        require(apiKey.isNotBlank()) { "ASR provider is not configured." }
        val file = File(audioRef)
        require(file.isFile) { "Audio file does not exist." }
        val request = JSONObject().apply {
            put("file_id", file.nameWithoutExtension.hashCode().toLong() and 0x7fffffff)
            put("model", "u2-asr")
            put("format", "mp3")
            put("sample_rate", 16000)
            put("enable_itn", true)
            put("channel", 1)
            put("enable_speaker", false)
            put("word_info", true)
        }
        val connection = (URL("https://maas-api.unisound.com/v1/audio/asr/tasks").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("Authorization", "Bearer $apiKey")
            setRequestProperty("Content-Type", "application/json")
        }
        connection.outputStream.use { it.write(request.toString().toByteArray()) }
        val body = (if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()?.use { it.readText() }.orEmpty()
        if (connection.responseCode !in 200..299) error("ASR request failed (${connection.responseCode}).")
        val json = JSONObject(body)
        val transcript = json.optString("text", json.optString("transcript"))
        AsrResult(transcript, json.optString("summary"), "")
    }
}
