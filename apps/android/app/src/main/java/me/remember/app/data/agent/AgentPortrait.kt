package me.remember.app.data.agent

import org.json.JSONObject

data class PortraitSource(val id: String, val excerpt: String, val sourceType: String, val episodeId: String?, val recordedAt: String = "")
data class PortraitLink(val id: String, val domain: String, val statement: String, val context: String,
    val evidenceIds: List<String>, val counterEvidenceIds: List<String>)
data class PsychologyPattern(val id: String, val pattern: String, val context: String, val evidenceIds: List<String>,
    val independentEpisodes: Int, val confidence: Double, val modelVersion: String)
data class AgentPortrait(val subjectId: String, val revision: Int, val sources: List<PortraitSource>, val links: List<PortraitLink>,
    val habits: List<PsychologyPattern> = emptyList(), val observations: List<MemoryObservation> = emptyList(),
    val memoryRevision: Int = 0, val status: String = "PENDING", val remote: Boolean = false)

/** Hyperedge = this subject + one contextual claim + all supporting/counter sources. No inferred graph facts. */
internal fun projectPortrait(state: JSONObject): AgentPortrait {
    val withdrawn = state.getJSONArray("withdrawn_evidence").strings().toSet()
    val sources = state.getJSONArray("materials").objects().filter {
        it.getString("evidence_id") !in withdrawn && it.getString("source_type") in setOf("SUBJECT", "CALIBRATION")
    }.map { PortraitSource(it.getString("evidence_id"), it.getString("excerpt"), it.getString("source_type"),
        it.optString("episode_id").takeIf { value -> value.isNotBlank() && value != "null" }, it.optString("observed_at")) }
    val allowed = sources.map { it.id }.toSet()
    val links = state.getJSONArray("traits").objects().filter {
        val support = it.getJSONArray("evidence_ids").strings()
        support.isNotEmpty() && (support + it.getJSONArray("counter_evidence_ids").strings()).all(allowed::contains) && it.optString("status") != "SUPERSEDED"
    }.map { PortraitLink(it.getString("trait_id"), it.getString("domain"), it.getString("statement"), it.getString("context"),
        it.getJSONArray("evidence_ids").strings(), it.getJSONArray("counter_evidence_ids").strings()) }
    val habits = state.optJSONArray("habits")?.objects().orEmpty().filter {
        it.getJSONArray("evidence_ids").strings().all(allowed::contains)
    }.map { PsychologyPattern(it.getString("habit_id"), it.getString("pattern"), it.getString("context"), it.getJSONArray("evidence_ids").strings(),
        it.getInt("independent_episodes"), it.getDouble("confidence"), it.getString("model_version")) }
    val observations = state.optJSONArray("observations")?.objects().orEmpty().filter { it.getString("evidence_id") in allowed }.map(MemoryObservation::from)
    return AgentPortrait(state.getString("subject_id"), state.getInt("revision"), sources, links, habits, observations,
        state.optInt("memory_revision"), state.optString("portrait_status", "PENDING"))
}
