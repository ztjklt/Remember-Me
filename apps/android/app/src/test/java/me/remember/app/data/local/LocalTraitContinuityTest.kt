package me.remember.app.data.local

import kotlinx.coroutines.runBlocking
import me.remember.app.data.repository.AudioRecording
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LocalTraitContinuityTest {
    private fun trait(id: String, text: String) = JSONObject().put("trait_id", id).put("domain", "IDENTITY")
        .put("statement", text).put("context", "本人自述").put("status", "CANDIDATE").put("evidence_ids", JSONArray().put("ev_old"))
        .put("counter_evidence_ids", JSONArray()).put("valid_from", "2026-01-01T00:00:00Z").put("valid_to", JSONObject.NULL)
    private val current = JSONObject().put("subject_id", "subject_one").put("traits", JSONArray(listOf(trait("name", "名字是林晨"), trait("school", "在大学读研"))))
    private fun update(change: String = "CORRECT") = JSONObject().put("trait_id", "name").put("change", change)
        .put("domain", "IDENTITY").put("statement", "名字是林宸").put("context", "本人自述")
        .put("evidence_ids", JSONArray().put("cev_name")).put("counter_evidence_ids", JSONArray())
    private suspend fun merge(update: JSONObject): JSONArray {
        val worker = LocalInference(object : LocalModelClient {
            override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings) = error("unused")
            override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint) = JSONObject().put("traits", JSONArray().put(update))
        })
        return worker.understand(current, JSONArray().put(JSONObject().put("evidence_id", "cev_name").put("source_type", "CALIBRATION")),
            ModelEndpoint("https://example.test", "synthetic", "synthetic-key"))
    }
    @Test fun correctingOnlyNameRetainsOtherFactsAndStableTraitId() = runBlocking {
        val merged = merge(update()).objects().associateBy { it.getString("trait_id") }
        assertEquals("名字是林宸", merged.getValue("name").getString("statement"))
        assertEquals("在大学读研", merged.getValue("school").getString("statement"))
        assertEquals("SUPPORTED", merged.getValue("name").getString("status"))
        assertEquals("2026-01-01T00:00:00Z", merged.getValue("name").getString("valid_from"))
    }
    @Test fun supportPreservesIdAndAddsEvidenceWithoutReplacingTheOtherDomain() = runBlocking {
        val merged = merge(update("SUPPORT").put("statement", "名字是林晨")).objects()
        assertEquals(listOf("ev_old", "cev_name"), merged.first { it.getString("trait_id") == "name" }.getJSONArray("evidence_ids").strings())
        assertEquals(2, merged.size)
    }
    @Test fun inventedExistingTraitCannotOverwriteAnotherFact() = runBlocking {
        try { merge(update().put("trait_id", "invented")); fail("invented identity accepted") } catch (_: IllegalArgumentException) {}
    }
}
