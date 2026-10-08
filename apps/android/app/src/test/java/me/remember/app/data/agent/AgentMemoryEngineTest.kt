package me.remember.app.data.agent

import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

internal class TestJournal : AgentJournalStore {
    var saved: String? = null
    override fun read() = saved?.let(::JSONObject)
    override fun write(state: JSONObject) { saved = state.toString() }
}
internal class TestAgentModel : StructuredAgentModel {
    override val modelVersion = "synthetic-model"
    var failPsychology = false
    var traitCalls = 0
    var calls = 0
    override suspend fun complete(prompt: String, input: JSONObject): JSONObject {
        calls++
        val sources = input.getJSONArray("materials").objects()
        if (input.optString("role") == "memory_observer") return JSONObject().put("observations", JSONArray())
        if (input.optString("role") == "psychological_learner") {
            check(!failPsychology) { "Synthetic worker failure" }
            return JSONObject().put("habits", JSONArray())
        }
        val last = sources.last()
        if (input.has("question")) return JSONObject().put("answerable", true).put("answer", last.getString("excerpt"))
            .put("evidence_ids", JSONArray().put(last.getString("evidence_id"))).put("limitations", JSONArray())
        traitCalls++
        return JSONObject().put("traits", JSONArray().put(JSONObject().put("domain", "IDENTITY")
            .put("statement", last.getString("excerpt")).put("context", "合成测试")
            .put("evidence_ids", JSONArray().put(last.getString("evidence_id")))))
    }
}
class AgentMemoryEngineTest {
    private val time = "2026-10-08T00:00:00Z"
    @Test fun failedWorkerKeepsRawMaterialAndRestartResumesItsCheckpoint() = runBlocking {
        val store = TestJournal(); val model = TestAgentModel().apply { failPsychology = true }
        val first = AgentMemoryEngine("one", store, model)
        try { first.addEpisode("ep_one", "本人原文", time, true); fail("worker succeeded") } catch (_: IllegalStateException) {}
        assertEquals("本人原文", first.originalMaterials().getJSONObject(0).getString("excerpt"))
        assertEquals(0, first.snapshot().getInt("revision")); assertTrue(first.pending()!!.has("traits"))
        assertEquals("本人原文", first.ask("说过什么？", true).getJSONObject("locked_answer").getString("answer"))
        model.failPsychology = false
        val restarted = AgentMemoryEngine("one", store, model); restarted.retry(true)
        assertEquals(1, model.traitCalls); assertEquals(1, restarted.snapshot().getInt("revision"))
        restarted.addEpisode("ep_one", "本人原文", time, true)
        assertEquals(1, restarted.originalMaterials().length()); assertNull(restarted.pending())
    }
    @Test fun correctionKeepsLockedAnswerAndDeletionInvalidatesDependentHistory() = runBlocking {
        val store = TestJournal(); val model = TestAgentModel(); val engine = AgentMemoryEngine("one", store, model)
        engine.addEpisode("ep_one", "名字是林晨", time, true, rawTranscript = "ASR 原文")
        val locked = engine.ask("我是谁？", true); val answer = locked.getJSONObject("locked_answer").toString()
        engine.correct(locked.getString("calibration_id"), "名字是林宸", 1, true)
        assertEquals(answer, engine.history().getJSONObject(0).getJSONObject("locked_answer").toString())
        val restarted = AgentMemoryEngine("one", store, model)
        assertEquals("名字是林宸", restarted.ask("我是谁？", true).getJSONObject("locked_answer").getString("answer"))
        restarted.deleteEpisode("ep_one")
        assertEquals(0, restarted.originalMaterials().length())
        assertTrue(restarted.history().objects().all { it.getString("state") == "INVALIDATED" })
        assertFalse(store.saved!!.contains("林晨")); assertFalse(store.saved!!.contains("林宸")); assertFalse(store.saved!!.contains("ASR 原文"))
    }
    @Test fun newerRevisionCannotBeUsedToSubmitAnOlderLockedAnswer() = runBlocking {
        val engine = AgentMemoryEngine("one", TestJournal(), TestAgentModel())
        engine.addEpisode("ep_one", "第一段", time, true); val locked = engine.ask("问题", true)
        engine.addEpisode("ep_two", "第二段", time, true)
        try { engine.correct(locked.getString("calibration_id"), "校正", 2, true); fail("stale lock accepted") } catch (_: IllegalStateException) {}
        assertFalse(engine.originalMaterials().objects().any { it.getString("excerpt") == "校正" })
    }
    @Test fun consentAndSubjectChecksPreventModelCallsAndCrossSubjectReads() = runBlocking {
        val store = TestJournal(); val model = TestAgentModel(); val engine = AgentMemoryEngine("one", store, model)
        try { engine.addEpisode("ep_one", "不发送", time, false); fail("consent bypassed") } catch (_: IllegalArgumentException) {}
        assertEquals(0, model.calls); assertNull(store.saved)
        engine.addEpisode("ep_one", "已同意", time, true)
        try { AgentMemoryEngine("other", store, model); fail("subject bypassed") } catch (_: IllegalArgumentException) {}
        val original = store.saved!!; store.saved = store.read()!!.put("version", 99).toString()
        try { AgentMemoryEngine("one", store, model); fail("version reset") } catch (_: IllegalStateException) {}
        assertEquals(99, store.read()!!.getInt("version")); assertNotEquals(original, store.saved)
    }
}
