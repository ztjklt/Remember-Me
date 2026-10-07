package me.remember.app.data.local

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import me.remember.app.model.Loadable
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
        var backup: String? = null
        override fun preserve(state: JSONObject) { backup = state.toString() }
        override fun read() = saved?.let(::JSONObject)
        override fun write(state: JSONObject) { saved = state.toString() }
    }
    private class FakeModel : LocalModelClient {
        var transcriptions = 0
        var failUnderstanding = false
        var badCitation = false
        var enforceCapacity = false
        override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings): String {
            transcriptions++; return java.io.File(recording.audioPath).readText()
        }
        override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint): JSONObject {
            if (enforceCapacity) requireLocalCapacity(input)
            val material = input.getJSONArray("materials").objects()
            if (input.has("question")) return JSONObject().put("answerable", true)
                .put("answer", material.last().getString("excerpt"))
                .put("evidence_ids", JSONArray().put(if (badCitation) "invented" else material.last().getString("evidence_id")))
                .put("limitations", JSONArray())
            check(!failUnderstanding) { "Synthetic provider failure" }
            return JSONObject().put("traits", JSONArray(material.map {
                JSONObject().put("domain", "IDENTITY").put("statement", it.getString("excerpt").take(2000))
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
    @Test fun archiveAndThreeAnswersSurviveRestartAndRespectWithdrawal() = runBlocking {
        val store = Store(); val model = FakeModel(); val engine = engine(store, model); val repo = grant(engine)
        engine.capture(recording("第一段原文")); engine.capture(recording("第二段原文")); repo.refresh()
        val archive = (engine.memories().first() as Loadable.Content).value
        assertEquals(2, archive.size)
        assertEquals("2026-01-01T00:00:00Z", archive.first().date)
        assertEquals("SUBJECT", archive.first().sourceType)
        repo.ask("问题一"); repo.submit("本人校正")
        val firstId = repo.state.value.calibration!!.id
        repo.ask("问题二"); repo.ask("问题三")
        assertEquals(3, repo.state.value.history.size)
        val last = repo.state.value.answer
        model.badCitation = true; repo.ask("失败问题")
        assertEquals(last, repo.state.value.answer)
        engine.cancelPending()
        val restarted = engine(store, model); val next = grant(restarted)
        assertEquals(3, next.state.value.history.size)
        next.resume(firstId)
        assertEquals("本人校正", next.state.value.correction)
        next.withdraw(archive.first().episodeId!!)
        assertEquals(1, (restarted.memories().first() as Loadable.Content).value.size)
        next.resume(firstId)
        assertEquals("INVALIDATED", next.state.value.calibration!!.state)
        assertTrue(next.state.value.answer!!.evidence.isEmpty())
    }

    @Test fun deletionErasesFilesAndDependentContentButRetainsTombstones() = runBlocking {
        val root = files.newFolder("recordings"); val library = RecordingLibrary(root)
        val audio = java.io.File(root, "one.m4a").apply { writeText("唯一敏感原文") }
        val sidecar = java.io.File(root, "one.json").apply { writeText("{\"durationMillis\":1000,\"created_at\":\"2026-01-01T00:00:00Z\"}") }
        val recording = library.list().single()
        val store = Store(); val engine = engine(store, FakeModel()); val repo = grant(engine)
        engine.capture(recording); repo.refresh(); repo.ask("问题"); repo.submit("敏感校正内容")
        engine.capture(recording("独立材料"))
        engine.deleteRecording(recording) { library.delete(recording) }
        assertFalse(audio.exists()); assertFalse(sidecar.exists())
        assertFalse(store.saved!!.contains("唯一敏感原文")); assertFalse(store.saved!!.contains("敏感校正内容"))
        assertEquals("INVALIDATED", store.read()!!.getJSONArray("calibrations").getJSONObject(0).getString("state"))
        repo.refresh(); repo.ask("问题")
        assertEquals("独立材料", repo.state.value.answer!!.answer)
        assertTrue(engine.recordings(library.list()).any { it.status == "已删除" })
        engine.reset { library.clear() }
        assertFalse(engine.granted()); assertEquals(0, store.read()!!.getJSONArray("materials").length())
    }
    @Test fun recordingDeletionCannotEscapeItsDirectory() {
        val root = files.newFolder("library"); val outside = files.newFile("outside.m4a")
        val recording = AudioRecording(outside.path, 0, "audio/mp4", 0, 44100, 1, "")
        try { RecordingLibrary(root).delete(recording); fail("outside file deleted") } catch (_: IllegalArgumentException) { }
        assertTrue(outside.exists())
    }

    @Test fun cancellingUnderstandingKeepsPaidTranscriptAndReprocessesWithoutAsr() = runBlocking {
        val store = Store(); val model = FakeModel().apply { failUnderstanding = true }; val engine = engine(store, model)
        val repo = grant(engine); val recording = recording("已经转写的原文")
        try { engine.capture(recording); fail("expected failure") } catch (_: IllegalStateException) { }
        engine.cancelPending(); repo.refresh()
        assertEquals("已经转写的原文", repo.state.value.materials.single().excerpt)
        assertEquals("待理解", engine.recordings(emptyList()).single().status)
        repo.ask("说过什么？"); assertEquals("已经转写的原文", repo.state.value.answer!!.answer)
        model.failUnderstanding = false
        engine.capture(recording)
        assertEquals(1, model.transcriptions)
        assertEquals(1, store.read()!!.getJSONArray("materials").length())
        assertEquals(1, store.read()!!.getJSONArray("episodes").length())
    }
    @Test fun capacityFailureResumesAfterDeletingAnOldRecordingWithoutRepeatingAsr() = runBlocking {
        val store = Store(); val model = FakeModel().apply { enforceCapacity = true }; val engine = engine(store, model)
        grant(engine)
        val old = recording("旧".repeat(36000)); val fresh = recording("新".repeat(36000))
        engine.capture(old)
        try { engine.capture(fresh); fail("expected capacity refusal") } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("我录过的"))
        }
        engine.deleteRecording(old) { java.io.File(old.audioPath).delete() }
        engine.retry()
        assertNull(engine.pending()); assertEquals(2, model.transcriptions)
        assertEquals("新".repeat(36000), store.read()!!.getJSONArray("materials").getJSONObject(1).getString("excerpt"))
    }
    @Test fun incompatiblePayloadIsPreservedWithoutReplacingIt() {
        val store = Store(); engine(store, FakeModel())
        val unknown = store.read()!!.put("version", 99).toString(); store.saved = unknown
        try { engine(store, FakeModel()); fail("future payload accepted") } catch (e: LocalRecoveryRequired) {
            assertTrue(e.message!!.contains("导出"))
        }
        assertEquals(unknown, store.saved); assertEquals(unknown, store.backup)
    }

}
