package me.remember.app.integration

import org.json.JSONObject
import java.io.File

/** Machine text and the user's editable draft remain separate until Save. */
data class CaptureDraft(val episode: String, val initial: String, val text: String,
    val supplement: String = "", val machine: String = "", val highlights: JSONObject? = null,
    val correction: JSONObject? = null) {
    fun json() = JSONObject().put("episode", episode).put("initial", initial).put("text", text)
        .put("supplement", supplement).put("machine", machine).put("highlights", highlights).put("correction", correction)
    companion object {
        fun fromReview(episode: String, result: JSONObject) = CaptureDraft(episode, result.text("transcript"),
            result.text("transcript"), result.text("supplement"), result.text("machine_transcript"),
            result.optJSONObject("recording_highlights"), result.optJSONObject("automatic_correction"))
        fun restore(row: JSONObject) = CaptureDraft(row.text("episode"), row.text("initial"), row.text("text"),
            row.text("supplement"), row.text("machine"), row.optJSONObject("highlights"), row.optJSONObject("correction"))
    }
}

/** Small scoped store; caller serializes writes and runs it off the UI thread. */
internal class CaptureDraftStore(private val root: File) {
    fun read(scope: String): Map<String, CaptureDraft> {
        val file = File(root, "$scope.json")
        val atomic=android.util.AtomicFile(file)
        if(!file.exists() && !File(file.path+".bak").exists()) return emptyMap()
        val json = JSONObject(atomic.openRead().bufferedReader().use { it.readText() })
        return json.keys().asSequence().associateWith { CaptureDraft.restore(json.getJSONObject(it)) }
    }
    fun write(scope: String, drafts: Map<String, CaptureDraft>) {
        root.mkdirs()
        val file = android.util.AtomicFile(File(root, "$scope.json"))
        val data = JSONObject().apply { drafts.forEach { (id, draft) -> put(id, draft.json()) } }
        val stream = file.startWrite()
        try { stream.write(data.toString().toByteArray(Charsets.UTF_8)); file.finishWrite(stream) }
        catch (error: Exception) { file.failWrite(stream); throw error }
    }
}

internal fun LocalCapture.needsAutomaticUpload(): Boolean = autoProcess && !linked && recording.durationMillis > 0
