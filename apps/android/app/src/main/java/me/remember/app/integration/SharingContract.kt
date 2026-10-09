package me.remember.app.integration

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI

data class ServiceInfo(val registrationAllowed: Boolean = false, val invitations: Boolean = false, val release: String = "") {
    companion object { fun parse(data: JSONObject) = ServiceInfo(data.optBoolean("registration_allowed", false), data.optBoolean("sharing_invitations", false), data.text("release_id")) }
}

data class ShareSelection(val episodeIds: List<String> = emptyList(), val storyIds: List<String> = emptyList()) {
    fun json() = JSONObject().put("episode_ids", JSONArray(episodeIds)).put("story_ids", JSONArray(storyIds))
    fun invitation(preview: JSONObject, audioConfirmed: Boolean, cloud: Boolean, recipient: String?): JSONObject {
        require(audioConfirmed) { "请先确认完整原音与文字的分享范围。" }
        require(episodeIds.isNotEmpty() || storyIds.isNotEmpty()) { "请选择故事或录音。" }
        return json().put("source_version", preview.getString("source_version")).put("include_audio_confirmed", true)
            .put("cloud_processing_allowed", cloud).apply { recipient?.takeIf { it.isNotBlank() }?.let { put("recipient_actor_id", it) } }
    }
}

fun invitationStatus(value: String): String = when(value) {
    "created" -> "等待亲友领取"; "claimed" -> "等待本人确认"; "approved" -> "已批准分享"
    "rejected" -> "已拒绝"; "cancelled" -> "已取消"; "expired" -> "已过期"; "revoked" -> "已撤销分享"
    else -> "状态待刷新"
}

fun serviceInfoRequest(server: String): ServiceInfo {
    val connection = URI(normalizeServer(server) + "/api/v1/service-info").toURL().openConnection() as HttpURLConnection
    try {
        connection.connectTimeout = 15_000; connection.readTimeout = 15_000
        connection.instanceFollowRedirects = false; connection.useCaches = false
        check(connection.responseCode == 200) { "服务版本信息暂不可用，注册入口保持关闭。" }
        return ServiceInfo.parse(JSONObject(connection.inputStream.bufferedReader().use { it.readText() }))
    } finally { connection.disconnect() }
}
