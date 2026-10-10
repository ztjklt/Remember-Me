package me.remember.app.integration

import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

internal fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
    val output = java.io.ByteArrayOutputStream()
    val buffer = ByteArray(8192)
    while(true) {
        val size = read(buffer); if(size < 0) break
        require(output.size() + size <= limit) { "转写文件过大。" }
        output.write(buffer, 0, size)
    }
    return output.toByteArray()
}

/** Unreviewed, client-reported machine output. Never an authoritative memory. */
@ConsistentCopyVisibility
data class ClientTranscript private constructor(val text: String, val audioSha256: String) {
    fun toJson(): JSONObject = JSONObject().put("text", text).put("audio_sha256", audioSha256)
        .put("provider", "groq").put("model", "whisper-large-v3").put("audio_export_confirmed", true)

    fun requireMatches(file: File) {
        require(file.isFile && file.length() > 0) { "本机原音不存在或为空。" }
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while(true) { val size = input.read(buffer); if(size < 0) break; digest.update(buffer, 0, size) }
        }
        val actual = digest.digest().joinToString("") { "%02x".format(it) }
        require(actual == audioSha256) { "机器稿与这段原音不匹配，请选择对应录音的转写结果。" }
    }

    companion object {
        const val MAX_DOCUMENT_BYTES = 1_000_000
        fun parse(document: String): ClientTranscript {
            require(document.toByteArray(Charsets.UTF_8).size <= MAX_DOCUMENT_BYTES) { "转写文件过大。" }
            try {
                val envelope = JSONObject(document)
                val value = if(envelope.has("client_transcript")) envelope.getJSONObject("client_transcript") else envelope
                require(value.keys().asSequence().toSet() == setOf("text", "audio_sha256", "provider", "model", "audio_export_confirmed"))
                val text = value.get("text") as? String ?: throw IllegalArgumentException()
                val hash = value.get("audio_sha256") as? String ?: throw IllegalArgumentException()
                require(text.isNotBlank() && text.length <= 100_000 && hash.matches(Regex("[0-9a-f]{64}")))
                require(value.get("provider") == "groq" && value.get("model") == "whisper-large-v3")
                require(value.get("audio_export_confirmed") == true)
                return ClientTranscript(text, hash)
            } catch(error: Exception) {
                throw IllegalArgumentException("机器稿格式无效，需要对应原音、Groq模型信息与已授权转写声明。")
            }
        }
    }
}
