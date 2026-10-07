package me.remember.app.data.local

import org.json.JSONObject

data class PortraitSource(val id: String, val excerpt: String, val sourceType: String, val episodeId: String?)
data class PortraitLink(val id: String, val domain: String, val statement: String, val context: String,
    val evidenceIds: List<String>, val counterEvidenceIds: List<String>)
data class LocalPortrait(val subjectId: String, val revision: Int, val sources: List<PortraitSource>, val links: List<PortraitLink>)

/** Hyperedge = this subject + one contextual claim + all supporting/counter sources. No inferred graph facts. */
internal fun projectPortrait(state: JSONObject): LocalPortrait {
    val withdrawn = state.getJSONArray("withdrawn_evidence").strings().toSet()
    val sources = state.getJSONArray("materials").objects().filter {
        it.getString("evidence_id") !in withdrawn && it.getString("source_type") in setOf("SUBJECT", "CALIBRATION")
    }.map { PortraitSource(it.getString("evidence_id"), it.getString("excerpt"), it.getString("source_type"),
        it.optString("episode_id").takeIf { value -> value.isNotBlank() && value != "null" }) }
    val allowed = sources.map { it.id }.toSet()
    val links = state.getJSONArray("traits").objects().filter {
        val support = it.getJSONArray("evidence_ids").strings()
        support.isNotEmpty() && (support + it.getJSONArray("counter_evidence_ids").strings()).all(allowed::contains) && it.optString("status") != "SUPERSEDED"
    }.map { PortraitLink(it.getString("trait_id"), it.getString("domain"), it.getString("statement"), it.getString("context"),
        it.getJSONArray("evidence_ids").strings(), it.getJSONArray("counter_evidence_ids").strings()) }
    return LocalPortrait(state.getString("subject_id"), state.getInt("revision"), sources, links)
}
