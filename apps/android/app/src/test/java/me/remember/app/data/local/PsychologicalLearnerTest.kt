package me.remember.app.data.local

import kotlinx.coroutines.runBlocking
import me.remember.app.data.repository.AudioRecording
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PsychologicalLearnerTest {
    private val endpoint = ModelEndpoint("https://example.test", "synthetic-model", "test-key")
    private val sources = JSONArray().put(JSONObject().put("evidence_id", "ev_one").put("source_type", "SUBJECT")
        .put("episode_id", "ep_one").put("excerpt", "我压力大时散步。"))
    private fun client(output: JSONObject) = object : LocalModelClient {
        override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings) = error("not used")
        override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint) = output
    }
    @Test fun inventedReferencesRejectTheWholeAnalysis() = runBlocking {
        val output = JSONObject().put("habits", JSONArray().put(JSONObject().put("pattern", "候选").put("context", "情境")
            .put("evidence_ids", JSONArray().put("invented")).put("confidence", .9)))
        try { PsychologicalLearner(client(output)).learn(JSONArray(), sources, JSONArray(), endpoint); fail("invented evidence accepted") }
        catch (e: IllegalArgumentException) { assertTrue(e.message!!.contains("证据")) }
    }
    @Test fun noPsychologicalMaterialCanProduceAnExplicitEmptyResult() = runBlocking {
        assertEquals(0, PsychologicalLearner(client(JSONObject().put("habits", JSONArray()))).learn(JSONArray(), sources, JSONArray(), endpoint).length())
    }
}
