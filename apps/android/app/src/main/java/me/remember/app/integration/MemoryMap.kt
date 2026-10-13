package me.remember.app.integration

import org.json.JSONObject

val narrativeViewFacets = listOf(
    setOf("EXPERIENCE", "IDENTITY", "FEELINGS"), setOf("RELATIONSHIPS"),
    setOf("PRACTICES", "VALUES", "WISHES"), setOf("EXPRESSION")
)

val memorySideTitles = linkedMapOf("EXPERIENCE" to "人生经历", "RELATIONSHIPS" to "人物关系",
    "IDENTITY" to "身份角色", "PRACTICES" to "偏好习惯", "VALUES" to "在意选择",
    "FEELINGS" to "感受状态", "WISHES" to "愿望牵挂", "EXPRESSION" to "原话寄语")
val personViewTitles = listOf("人生足迹", "重要的人", "在意选择", "声音表达")

private fun hasFacet(row: JSONObject, id: String): Boolean = row.optJSONArray("facets")?.let {
    a -> (0 until a.length()).any { a.optString(it) == id }
} ?: false

fun memoryFacetCounts(rows: List<JSONObject>, facet: String, owner: Boolean): Pair<Int, Int> {
    val valid = rows.filter { it.optBoolean("source_valid") && hasFacet(it, facet) }
    return valid.count { it.optString("status") == "confirmed" } to
        if (owner) valid.count { it.optString("status") == "pending" } else 0
}

fun selectNarrativeRecords(rows: List<JSONObject>, owner: Boolean, review: Boolean,
                           view: Int, facet: String, query: String): List<JSONObject> = rows.filter { row ->
    val visible = if (review) owner && row.optString("status") in setOf("pending", "stale")
        else row.optString("status") == "confirmed" && row.optBoolean("source_valid")
    visible && (view == -1 || narrativeViewFacets.getOrElse(view) { emptySet() }.any { hasFacet(row, it) }) &&
        (facet.isBlank() || hasFacet(row, facet)) && (query.isBlank() ||
        (listOf("title", "text", "place_text", "aliases").joinToString(" ") { row.optString(it) } + " " +
            row.rows("evidence").joinToString(" ") { it.text("excerpt") }).contains(query.trim(), true))
}.sortedBy { row ->
    val order=listOf(listOf("story","observation","person"),listOf("person","story","observation"),
        listOf("observation","story","person"),listOf("letter","style","observation","story","person"))
        .getOrElse(view){emptyList()}
    order.indexOf(row.optString("kind")).let { if(it<0) order.size else it }
}
