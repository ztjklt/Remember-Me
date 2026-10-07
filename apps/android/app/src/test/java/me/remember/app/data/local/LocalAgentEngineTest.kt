package me.remember.app.data.local

import kotlinx.coroutines.runBlocking
import me.remember.app.data.repository.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class LocalAgentEngineTest {
    @get:Rule val files = TemporaryFolder()
    private val endpoint = ModelEndpoint("https://example.test", "synthetic-model", "test-key")
    private val settings = LocalModelSettings(endpoint, endpoint, SpeechProtocol.DASHSCOPE)
    private class Store : LocalStateStore {
        var saved: String? = null
        override fun read() = saved?.let(::JSONObject)
        override fun write(state: JSONObject) { saved = state.toString() }
    }
    private class FakeModel : LocalModelClient {
        var transcriptions = 0
        var failUnderstanding = false
        var badCitation = false
        override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings): String {
            transcriptions++; return java.io.File(recording.audioPath).readText()
        }
        override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint): JSONObject {
            val material = input.getJSONArray("materials").objects()
            if (input.has("question")) return JSONObject().put("answerable", true)
                .put("answer", material.last().getString("excerpt"))
                .put("evidence_ids", JSONArray().put(if (badCitation) "invented" else material.last().getString("evidence_id")))
                .put("limitations", JSONArray())
            check(!failUnderstanding) { "Synthetic provider failure" }
            return JSONObject().put("traits", JSONArray(material.map {
                JSONObject().put("domain", "IDENTITY").put("statement", it.getString("excerpt"))
                    .put("context", "合成测试").put("evidence_ids", JSONArray().put(it.getString("evidence_id")))
            }))
        }
    }
    private fun recording(text: String): AudioRecording {
        val file = files.newFile().apply { writeText(text) }
        return AudioRecording(file.path, 1000, "audio/mp4", file.length(), 44100, 1, "2026-01-01T00:00:00Z")
    }
    private fun engine(store: Store, model: FakeModel) = LocalAgentEngine(store, model) { settings }
    private suspend fun grant(engine: LocalAgentEngine) = AgentRepository(engine).also { it.enable(engine.connection()) }

    @Test fun correctionRetainsOriginalAndLockedAnswerAcrossRestart() = runBlocking {
        val store = Store(); val model = FakeModel(); val engine = engine(store, model)
        val repo = grant(engine)
        engine.capture(recording("我是林晨，我研究记忆系统。")); repo.refresh()
        repo.ask("我是谁？")
        val locked = repo.state.value.answer!!
        repo.submit("我是林宸", "我是谁？")
        assertNull(repo.state.value.error)
        assertEquals(2, repo.state.value.snapshot!!.revision)
        assertEquals(locked, repo.state.value.answer)
        assertTrue(repo.state.value.materials.any { it.excerpt.contains("林晨") && it.sourceType == "SUBJECT" })
        val restored = engine(store, model); val next = grant(restored)
        next.resume(restored.latestCalibration()!!)
        assertEquals(locked, next.state.value.answer)
        assertEquals("COMPLETED", next.state.value.calibration!!.state)
        assertEquals("我是林宸", next.state.value.correction)
        next.ask("我是谁？")
        assertEquals("我是林宸", next.state.value.answer!!.answer)
    }

    @Test fun retryAfterRestartReusesTranscriptAndDeduplicatesTheRecording() = runBlocking {
        val store = Store(); val model = FakeModel().apply { failUnderstanding = true }
        val first = engine(store, model); grant(first)
        val recording = recording("合成恢复测试")
        try { first.capture(recording); fail("expected provider failure") } catch (_: IllegalStateException) { }
        assertEquals("合成恢复测试", first.pending()!!.getJSONObject("evidence").getString("excerpt"))
        val restarted = engine(store, model); model.failUnderstanding = false
        restarted.retry(); restarted.capture(recording)
        assertEquals(1, model.transcriptions)
        assertNull(restarted.pending())
        assertEquals(1, store.read()!!.getInt("revision"))
        val repo = grant(restarted); model.badCitation = true
        repo.ask("问题")
        assertNotNull(repo.state.value.error)
        assertNull(repo.state.value.answer)
        assertEquals(0, store.read()!!.getJSONArray("calibrations").length())
    }

    @Test fun withdrawalInvalidatesOnlyDependentViewsAndRetainsOtherRecordsAndHistory() = runBlocking {
        val store = Store(); val engine = engine(store, FakeModel()); val repo = grant(engine)
        engine.capture(recording("材料一")); repo.refresh()
        val first = repo.state.value.materials.single().episodeId!!
        repo.ask("问题一"); repo.submit("第一份材料的校正")
        engine.capture(recording("独立材料二")); repo.refresh()
        val history = store.read()!!.getJSONArray("history").length()
        repo.withdraw(first)
        assertNull(repo.state.value.error)
        assertEquals(listOf("独立材料二"), repo.state.value.materials.map { it.excerpt })
        assertEquals(listOf("独立材料二"), repo.state.value.snapshot!!.traits.map { it.statement })
        assertEquals(history, store.read()!!.getJSONArray("history").length())
        assertEquals(3, store.read()!!.getJSONArray("materials").length())
        assertEquals("INVALIDATED", store.read()!!.getJSONArray("calibrations").getJSONObject(0).getString("state"))
        repo.revoke()
        try { engine.capture(recording("未授权材料")); fail("consent bypassed") } catch (_: IllegalStateException) { }
    }
}
