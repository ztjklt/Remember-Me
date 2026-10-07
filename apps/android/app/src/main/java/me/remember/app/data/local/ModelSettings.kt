package me.remember.app.data.local

import org.json.JSONObject
import java.net.URI

enum class SpeechProtocol { DASHSCOPE, CHAT_COMPLETIONS }

data class ModelEndpoint(val baseUrl: String, val model: String, val apiKey: String) {
    override fun toString() = "ModelEndpoint(credentials=redacted)"
    fun validate() {
        val uri = runCatching { URI(baseUrl) }.getOrNull()
        require(uri != null && !uri.host.isNullOrBlank() && uri.userInfo == null && uri.query == null && uri.fragment == null &&
            (uri.scheme == "https" || (uri.scheme == "http" && uri.host in setOf("127.0.0.1", "localhost")))) {
            "模型地址必须是 HTTPS Base URL。"
        }
        require(model.isNotBlank() && model.length <= 200 && apiKey.isNotBlank() && !apiKey.any { it == '\r' || it == '\n' }) {
            "请填写模型名称和有效 API Key。"
        }
    }
    fun json() = JSONObject().put("base_url", baseUrl).put("model", model).put("api_key", apiKey)
    companion object {
        fun from(json: JSONObject) = ModelEndpoint(json.getString("base_url"), json.getString("model"), json.getString("api_key"))
    }
}

data class LocalModelSettings(val speech: ModelEndpoint, val language: ModelEndpoint, val protocol: SpeechProtocol) {
    override fun toString() = "LocalModelSettings(credentials=redacted)"
    fun validate() { speech.validate(); language.validate() }
    fun json() = JSONObject().put("speech", speech.json()).put("language", language.json()).put("speech_protocol", protocol.name)
    companion object {
        fun from(json: JSONObject) = LocalModelSettings(ModelEndpoint.from(json.getJSONObject("speech")),
            ModelEndpoint.from(json.getJSONObject("language")), SpeechProtocol.valueOf(json.getString("speech_protocol")))
    }
}
