package me.remember.app.integration

import org.json.JSONObject

/** Browsing links only: shared evidence does not imply identity or closeness. */
fun relatedNarrativeStories(record: JSONObject, visibleRecords: List<JSONObject>): List<JSONObject> {
    if(record.optString("kind") !in setOf("person","observation") || record.optString("status") != "confirmed" || !record.optBoolean("source_valid")) return emptyList()
    val sourceIds = record.optJSONArray("evidence_ids")?.let { a -> (0 until a.length()).map { a.getString(it) }.toSet() } ?: emptySet()
    return visibleRecords.filter { story ->
        val refs = story.optJSONArray("evidence_ids")
        story.optString("kind") == "story" && story.optString("status") == "confirmed" && story.optBoolean("source_valid") &&
            refs != null && (0 until refs.length()).any { refs.getString(it) in sourceIds }
    }
}
