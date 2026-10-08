package me.remember.app.data.agent

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PsychologicalLearnerTest {
    private val sources = JSONArray().put(JSONObject().put("evidence_id", "ev_one").put("source_type", "SUBJECT")
        .put("episode_id", "ep_one").put("excerpt", "我压力大时散步。"))
    private fun client(output: JSONObject) = object : StructuredAgentModel {
        override val modelVersion = "synthetic-model"
        override suspend fun complete(prompt: String, input: JSONObject) = output
    }
    @Test fun inventedReferencesRejectTheWholeAnalysis() = runBlocking {
        val output = JSONObject().put("habits", JSONArray().put(JSONObject().put("pattern", "候选").put("context", "情境")
            .put("evidence_ids", JSONArray().put("invented")).put("confidence", .9)))
        try { PsychologicalLearner(client(output)).learn(JSONArray(), sources, JSONArray()); fail("invented evidence accepted") }
        catch (e: IllegalArgumentException) { assertTrue(e.message!!.contains("证据")) }
    }
    @Test fun noPsychologicalMaterialCanProduceAnExplicitEmptyResult() = runBlocking {
        assertEquals(0, PsychologicalLearner(client(JSONObject().put("habits", JSONArray()))).learn(JSONArray(), sources, JSONArray()).length())
    }
}
