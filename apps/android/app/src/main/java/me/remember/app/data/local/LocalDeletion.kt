package me.remember.app.data.local

import org.json.JSONArray
import org.json.JSONObject

/** Erase content along provenance edges while retaining identifiers and invalidation tombstones. */
internal fun eraseRecording(state: JSONObject, episodeId: String): JSONObject = state.copyJson().apply {
    val materials = getJSONArray("materials").objects()
    val removed = materials.filter { it.optString("episode_id") == episodeId }.map { it.getString("evidence_id") }.toMutableSet()
    val records = getJSONArray("calibrations").objects()
    var changed: Boolean
    do {
        changed = false
        records.filter { answerRoots(it.getJSONObject("locked_answer")).any(removed::contains) }.forEach { cal ->
            cal.put("state", "INVALIDATED")
            materials.filter { it.getString("source_ref") == "calibration:${cal.getString("calibration_id")}" }.forEach {
                if (removed.add(it.getString("evidence_id"))) changed = true
            }
        }
    } while (changed)
    materials.filter { it.getString("evidence_id") in removed }.forEach { it.put("excerpt", "[已删除]").put("context", "") }
    val affected = records.filter { answerRoots(it.getJSONObject("locked_answer")).any(removed::contains) }
    affected.forEach {
        it.put("question", "对应录音已删除").remove("human_answer")
        it.remove("comparison")
        it.getJSONObject("locked_answer").put("answer", "[已删除]").put("evidence", JSONArray()).put("limitations", JSONArray())
    }
    fun cleanTraits(snapshot: JSONObject) {
        snapshot.put("traits", JSONArray(snapshot.getJSONArray("traits").objects().filter {
            (it.getJSONArray("evidence_ids").strings() + it.getJSONArray("counter_evidence_ids").strings()).none(removed::contains)
        }))
    }
    cleanTraits(this)
    put("observations", JSONArray(optJSONArray("observations")?.objects().orEmpty().filter { it.getString("evidence_id") !in removed }))
    put("memory_revision", optInt("memory_revision") + 1).put("portrait_status", "PENDING")
    optJSONObject("job")?.apply { remove("traits"); remove("habits"); remove("trait_chunks") }
    optJSONObject("job")?.optJSONObject("evidence")?.getString("evidence_id")?.let { if (it in removed) remove("job") }
    put("backfill_ids", JSONArray(optJSONArray("backfill_ids")?.strings().orEmpty().filter { it !in removed }))
    put("habits", JSONArray(optJSONArray("habits")?.objects().orEmpty().filter {
        it.getJSONArray("evidence_ids").strings().none(removed::contains)
    }))
    getJSONArray("history").objects().forEach(::cleanTraits)
    val affectedJobs = affected.map { it.getString("calibration_id") }.toSet() + episodeId
    put("cancelled_jobs", JSONArray(optJSONArray("cancelled_jobs")?.objects().orEmpty().map {
        if (it.optString("id") in affectedJobs) JSONObject().put("id", it.getString("id")).put("status", "DELETED") else it
    }))
    put("withdrawn_evidence", JSONArray(getJSONArray("withdrawn_evidence").strings().toSet() + removed))
    put("revision", getInt("revision") + 1)
}
