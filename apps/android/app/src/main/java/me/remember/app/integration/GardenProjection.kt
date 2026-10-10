package me.remember.app.integration

import org.json.JSONObject

data class GardenEvidence(val id: String, val excerpt: String, val episodeId: String, val sourceType: String)
data class GardenPetal(val id: String, val title: String, val content: String, val sourceLabel: String,
    val evidence: List<GardenEvidence>) {
    val episodeIds get() = evidence.map { it.episodeId }.distinct()
}
data class GardenCluster(val id: String, val title: String, val organized: Boolean, val recordedAt: String,
    val episodeIds: List<String>, val facets: List<String>, val petals: List<GardenPetal>)

private fun gardenEvidence(row: JSONObject, visible: Set<String>) = row.rows("evidence").mapNotNull { e ->
    val id = e.text("evidence_id"); val episode = e.text("episode_id"); val excerpt = e.text("excerpt")
    if (id.isBlank() || episode !in visible || excerpt.isBlank()) null
    else GardenEvidence(id, excerpt, episode, e.text("source_type"))
}.distinctBy { it.id }

/** Projection only: no inference, permission expansion, mutation or synthetic preview data. */
fun projectGarden(stories: List<JSONObject>, narrative: JSONObject): List<GardenCluster> {
    val available = stories.filter { it.text("episode_id").isNotBlank() && it.text("status") == "ready" &&
        it.optBoolean("reviewed") && !it.optBoolean("waiting_for_review") && !it.optBoolean("unavailable") }
        .distinctBy { it.text("episode_id") }
    val byEpisode = available.associateBy { it.text("episode_id") }
    val visible = byEpisode.keys
    val currentSources = narrative.rows("source_evidence").associateBy { it.text("evidence_id") }
    fun currentEvidence(row: JSONObject): List<GardenEvidence> {
        val raw = row.rows("evidence")
        if(raw.isEmpty() || raw.any { e -> val current = currentSources[e.text("evidence_id")]
            current == null || current.text("episode_id") != e.text("episode_id") ||
                current.text("excerpt") != e.text("excerpt") || e.text("episode_id") !in visible }) return emptyList()
        return gardenEvidence(row, visible)
    }
    val memories = available.flatMap { story -> story.rows("memories").filter {
        it.text("memory_item_id").isNotBlank() && it.text("review_state") == "active" && it.text("content").isNotBlank()
    } }.distinctBy { it.text("memory_item_id") }
    val covered = mutableSetOf<String>()
    fun petal(memory: JSONObject, evidence: List<GardenEvidence>) = GardenPetal(
        memory.text("memory_item_id"), memory.text("content").take(22), memory.text("content"),
        if (memory.text("origin") == "owner_supplement") "本人书面补充 · 不属于录音原话" else when(memory.text("source_type")) {
            "THIRD_PARTY" -> "系统整理 · 第三方转述"
            "AI_INFERENCE" -> "系统归纳 · 请结合依据理解"
            "CALIBRATION" -> "本人确认的修订"
            else -> "系统整理 · 来自讲述"
        }, evidence)
    val organized = narrative.rows("records").filter { it.text("id").isNotBlank() && it.text("kind") == "story" &&
        it.text("status") == "confirmed" && it.optBoolean("source_valid") }.distinctBy { it.text("id") }.mapNotNull { record ->
        val raw = record.rows("evidence")
        // Do not reveal even a title if any required recording is no longer available.
        if (raw.isEmpty() || raw.any { it.text("episode_id") !in visible || it.text("evidence_id").isBlank() }) return@mapNotNull null
        val evidence = currentEvidence(record)
        if (evidence.size != raw.map { it.text("evidence_id") }.distinct().size) return@mapNotNull null
        val refs = evidence.map { it.id }.toSet()
        val matched = memories.mapNotNull { memory ->
            val basis = currentEvidence(memory)
            if (basis.isEmpty() || basis.any { it.id !in refs }) null else petal(memory, basis).also { covered.add(it.id) }
        }
        val petals = matched.ifEmpty { evidence.map { e -> GardenPetal("evidence:${e.id}", "故事依据", e.excerpt,
            "故事依据 · 核对文字", listOf(e)) } }
        val episodes = evidence.map { it.episodeId }.distinct()
        GardenCluster("record:${record.text("id")}", record.text("title").ifBlank { "本人核对的故事" }, true,
            episodes.mapNotNull { byEpisode[it]?.text("recorded_at") }.maxOrNull().orEmpty(), episodes,
            record.optJSONArray("facets")?.let { a -> (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() } }.orEmpty(), petals)
    }
    val ungrouped = available.mapNotNull { story ->
        val petals = story.rows("memories").filter { it.text("memory_item_id") !in covered && it.text("review_state") == "active" }
            .distinctBy { it.text("memory_item_id") }.mapNotNull { memory ->
                val basis = currentEvidence(memory).filter { it.episodeId == story.text("episode_id") }
                if (memory.text("memory_item_id").isBlank() || memory.text("content").isBlank() || basis.isEmpty()) null else petal(memory, basis)
            }
        if (petals.isEmpty() && (story.rows("memories").isNotEmpty() || organized.any { story.text("episode_id") in it.episodeIds })) null else GardenCluster("episode:${story.text("episode_id")}",
            "${recordingDate(story.text("recorded_at"))}的讲述", false, story.text("recorded_at"),
            listOf(story.text("episode_id")), emptyList(), petals)
    }
    return (organized + ungrouped).sortedWith(compareByDescending<GardenCluster> { it.recordedAt }.thenBy { it.id })
}
