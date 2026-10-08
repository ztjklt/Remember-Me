package me.remember.app.data.agent

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/** Inject transport outside the core. Neither keys nor a vendor SDK belong to this interface. */
interface StructuredAgentModel {
    val modelVersion: String
    suspend fun complete(prompt: String, input: JSONObject): JSONObject
}

internal suspend fun StructuredAgentModel.checkedComplete(prompt: String, input: JSONObject): JSONObject {
    requireAgentCapacity(input)
    return complete(prompt, input)
}

internal fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
internal fun JSONArray.strings() = (0 until length()).map { getString(it) }
internal fun JSONObject.copyJson() = JSONObject(toString())
internal fun now() = Instant.now().toString()
internal fun newId(prefix: String) = prefix + UUID.randomUUID().toString().replace("-", "")

internal fun requireAgentCapacity(input: JSONObject) {
    require(input.toString().length <= 60_000) {
        "相关材料超过 60,000 字符。请撤除不再需要的旧录音，再重试；原文未压缩或截断。"
    }
}
