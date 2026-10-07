package me.remember.app.data.local

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LocalPortraitTest {
    private fun state() = JSONObject().put("subject_id", "one-subject").put("revision", 2)
        .put("withdrawn_evidence", JSONArray()).put("materials", JSONArray(listOf(
            JSONObject().put("evidence_id", "ev_one").put("source_type", "SUBJECT").put("episode_id", "ep_one").put("excerpt", "我压力大时散步。"),
            JSONObject().put("evidence_id", "cev_two").put("source_type", "CALIBRATION").put("episode_id", JSONObject.NULL).put("excerpt", "散步是为了整理想法。"))))
        .put("traits", JSONArray().put(JSONObject().put("trait_id", "trait_one").put("domain", "DECISION_PATTERNS")
            .put("statement", "通过散步整理压力下的想法").put("context", "压力情境").put("status", "CANDIDATE")
            .put("evidence_ids", JSONArray(listOf("ev_one", "cev_two"))).put("counter_evidence_ids", JSONArray())))
    @Test fun oneHyperedgeConnectsTheSameSubjectAndMultipleOriginalSources() {
        val graph = projectPortrait(state())
        assertEquals("one-subject", graph.subjectId); assertEquals(2, graph.revision)
        assertEquals(listOf("ev_one", "cev_two"), graph.links.single().evidenceIds)
        assertEquals("CALIBRATION", graph.sources.last().sourceType); assertNull(graph.sources.last().episodeId)
    }
    @Test fun withdrawnAndThirdPartyEvidenceCannotKeepAClaimVisible() {
        val withdrawn = state().put("withdrawn_evidence", JSONArray().put("ev_one"))
        assertTrue(projectPortrait(withdrawn).links.isEmpty())
        assertEquals(listOf("cev_two"), projectPortrait(withdrawn).sources.map { it.id })
        val thirdParty = state().apply { getJSONArray("materials").getJSONObject(0).put("source_type", "THIRD_PARTY") }
        assertTrue(projectPortrait(thirdParty).links.isEmpty())
    }
}
