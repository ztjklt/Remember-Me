package me.remember.app.integration

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

data class CompanionAudioDraft(val purpose: String, val file: File, val mime: String = "audio/mp4",
    val key: String = UUID.randomUUID().toString(), val remote: JSONObject? = null)

fun CompanionAudioDraft.saved(): JSONObject = JSONObject().put("purpose",purpose).put("path",file.absolutePath)
    .put("mime",mime).put("key",key).apply {remote?.let{put("remote",it)}}
fun restoredCompanionAudio(value: JSONObject): CompanionAudioDraft? {
    val file=File(value.text("path"));val purpose=value.text("purpose");val key=value.text("key")
    if(!file.isFile||file.length()==0L||purpose !in setOf("letter","contribution")||key.isBlank()) return null
    return CompanionAudioDraft(purpose,file,value.text("mime"),key,value.optJSONObject("remote"))
}

fun companionPayload(text: String, audio: CompanionAudioDraft?, narrativeIds: List<String> = emptyList()): JSONObject {
    require(text.isNotBlank()) { "请填写正文。" }
    require(audio == null || audio.remote?.text("status") == "confirmed") { "请先上传声音并核对文字，或取消附加声音。" }
    return JSONObject().put("text", text.trim()).put("audio_id", audio?.remote?.text("audio_id") ?: JSONObject.NULL)
        .put("narrative_ids", JSONArray(narrativeIds.distinct()))
}

fun mergeCompanionSpaces(regular: List<JSONObject>, companion: List<JSONObject>): List<JSONObject> =
    (companion + regular).associateBy { it.text("subject_id") }.values.toList()

fun contributionModelUseAllowed(note: JSONObject) = note.optBoolean("model_use_author_allowed") && note.optBoolean("model_use_owner_allowed")

fun contributionModelUseEditable(note: JSONObject) = note.text("status") in setOf("accepted", "disagreement")

/** Reading permission is independent of model-use permission; changed or withdrawn content closes. */
fun retainedContributionOriginal(original: JSONObject?, available: List<JSONObject>): JSONObject? =
    original?.takeIf { detail -> available.any { row ->
        row.text("id")==detail.text("id") && row.optInt("revision")==detail.optInt("revision") && row.text("status")!="withdrawn"
    } }

fun personaCoverageHint(answer: JSONObject): String? =
    "已回答有依据的部分".takeIf { answer.text("coverage")=="partial" &&
        !answer.text("answer").contains(it) && !answer.text("answer").contains("部分问题尚未回答。") }

fun confirmedUnderstandings(data: JSONObject): List<JSONObject> = data.rows("understandings").filter { it.text("status") == "confirmed" }
