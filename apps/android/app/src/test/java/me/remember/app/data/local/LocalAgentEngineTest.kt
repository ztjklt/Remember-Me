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
        var failPsychology = false
        var learnHabits = false
        var understandingCalls = 0
        var psychologyCalls = 0
        var lastHypotheses = JSONArray()
        override suspend fun transcribe(recording: AudioRecording, settings: LocalModelSettings): String {
            transcriptions++; return java.io.File(recording.audioPath).readText()
        }
        override suspend fun complete(prompt: String, input: JSONObject, endpoint: ModelEndpoint): JSONObject {
            if (enforceCapacity) requireLocalCapacity(input)
            val material = input.getJSONArray("materials").objects()
            if (input.optString("role") == "memory_observer") return JSONObject().put("observations", JSONArray())
            if (input.optString("role") == "psychological_learner") {
                psychologyCalls++
                check(!failPsychology) { "Synthetic psychology failure" }
                val last = material.lastOrNull()
                return JSONObject().put("habits", if (!learnHabits || last == null) JSONArray() else JSONArray().put(JSONObject()
                    .put("pattern", if (last.getString("source_type") == "CALIBRATION") last.getString("excerpt") else "在压力下散步整理想法")
                    .put("context", "压力情境，仅为候选").put("confidence", .9)
                    .put("evidence_ids", JSONArray(material.takeLast(2).map { it.getString("evidence_id") }))))
            }
            if (input.has("question")) {
                lastHypotheses = input.getJSONArray("psychological_hypotheses")
                return JSONObject().put("answerable", true)
                .put("answer", material.last().getString("excerpt"))
                .put("evidence_ids", JSONArray().put(if (badCitation) "invented" else material.last().getString("evidence_id")))
                .put("limitations", JSONArray())
            }
            understandingCalls++
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
        val store = Store(); val model = FakeModel().apply { learnHabits = true }; val engine = engine(store, model); val repo = grant(engine)
        engine.capture(recording("材料一")); repo.refresh()
        val first = repo.state.value.materials.single().episodeId!!
        repo.ask("问题一"); repo.submit("第一份材料的校正")
        engine.capture(recording("独立材料二")); repo.refresh()
        assertEquals(1, engine.portrait()!!.habits.size)
        val history = store.read()!!.getJSONArray("history").length()
        repo.withdraw(first)
        assertNull(repo.state.value.error)
        assertEquals(listOf("独立材料二"), repo.state.value.materials.map { it.excerpt })
        assertEquals(listOf("独立材料二"), repo.state.value.snapshot!!.traits.map { it.statement })
        assertEquals(history, store.read()!!.getJSONArray("history").length())
        assertEquals(3, store.read()!!.getJSONArray("materials").length())
        assertEquals("INVALIDATED", store.read()!!.getJSONArray("calibrations").getJSONObject(0).getString("state"))
        assertTrue(engine.portrait()!!.habits.isEmpty())
        repo.ask("撤除后的问题"); assertEquals(0, model.lastHypotheses.length())
        repo.revoke()
        assertNull(engine.portrait())
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
        sidecar.writeText("corrupted metadata")
        val recovered = library.list().single()
        assertNotEquals(recording.createdAt, recovered.createdAt)
        assertEquals(recording.createdAt, engine.recordings(library.list()).first { it.recording.audioPath == audio.path }.recording.createdAt)
        engine.deleteRecording(recovered) { library.delete(recovered) }
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
    @Test fun longUnrelatedHistoryDoesNotBlockNewRecordingOrRepeatAsr() = runBlocking {
        val store = Store(); val model = FakeModel().apply { enforceCapacity = true }; val engine = engine(store, model)
        grant(engine)
        val old = recording("旧".repeat(36000)); val fresh = recording("新".repeat(36000))
        engine.capture(old)
        engine.capture(fresh)
        assertNull(engine.pending()); assertEquals(2, model.transcriptions)
        assertEquals("新".repeat(36000), store.read()!!.getJSONArray("materials").getJSONObject(1).getString("excerpt"))
        assertEquals(2, store.read()!!.getJSONArray("episodes").length())
    }
    @Test fun incompatiblePayloadIsPreservedWithoutReplacingIt() {
        val store = Store(); engine(store, FakeModel())
        val unknown = store.read()!!.put("version", 99).toString(); store.saved = unknown
        try { engine(store, FakeModel()); fail("future payload accepted") } catch (e: LocalRecoveryRequired) {
            assertTrue(e.message!!.contains("导出"))
        }
        assertEquals(unknown, store.saved); assertEquals(unknown, store.backup)
    }

    @Test fun psychologyFailureResumesSavedAsrAndPortraitThenPublishesOneRevision() = runBlocking {
        val store = Store(); val model = FakeModel().apply { failPsychology = true }; val engine = engine(store, model)
        val repo = grant(engine)
        try { engine.capture(recording("压力时我喜欢散步。")); fail("expected psychology failure") } catch (_: IllegalStateException) {}
        repo.refresh(); assertEquals(0, repo.state.value.snapshot!!.revision)
        assertTrue(engine.pending()!!.has("traits")); assertEquals("压力时我喜欢散步。", repo.state.value.materials.single().excerpt)
        assertEquals("FAILED", store.read()!!.getString("portrait_status"))
        repo.ask("说过什么？"); assertEquals("压力时我喜欢散步。", repo.state.value.answer!!.answer)
        model.failPsychology = false; engine.retry(); repo.refresh()
        assertEquals(1, model.transcriptions); assertEquals(1, model.understandingCalls); assertEquals(2, model.psychologyCalls)
        assertEquals(1, repo.state.value.snapshot!!.revision)
        assertFalse(store.read()!!.getJSONArray("episodes").getJSONObject(0).has("traits"))
    }

    @Test fun failedPortraitCannotAcceptACorrectionAgainstNewerRawMaterials() = runBlocking {
        val store = Store(); val model = FakeModel(); val engine = engine(store, model); val repo = grant(engine)
        engine.capture(recording("第一段资料")); repo.refresh(); repo.ask("我说过什么？")
        model.failUnderstanding = true
        try { engine.capture(recording("新资料")); fail("expected failure") } catch (_: IllegalStateException) {}
        repo.submit("旧问题的校正")
        assertNotNull(repo.state.value.error)
        assertFalse(store.saved!!.contains("旧问题的校正"))
    }
    @Test fun repeatedHabitsUseDistinctRecordingsAndCorrectionFeedsAnswersThenDeletionErasesThem() = runBlocking {
        val store = Store(); val model = FakeModel().apply { learnHabits = true }; val engine = engine(store, model); val repo = grant(engine)
        val first = recording("昨天压力大，我通过散步整理想法。"); val second = recording("今天考试紧张，散步让我安静下来。")
        engine.capture(first)
        assertEquals(1, engine.portrait()!!.habits.single().independentEpisodes)
        assertEquals(.5, engine.portrait()!!.habits.single().confidence, .001)
        engine.capture(second); repo.refresh()
        assertEquals(2, engine.portrait()!!.habits.single().independentEpisodes)
        repo.ask("压力下我会怎么办？"); assertEquals(1, model.lastHypotheses.length())
        repo.submit("更准确说，压力时我跑步，而不是散步。", "压力下我会怎么办？")
        assertTrue(engine.portrait()!!.habits.single().pattern.contains("跑步"))
        val restored = engine(store, model); assertTrue(restored.portrait()!!.habits.single().pattern.contains("跑步"))
        restored.deleteRecording(second) { java.io.File(second.audioPath).delete() }
        assertTrue(restored.portrait()!!.habits.isEmpty()); assertFalse(store.saved!!.contains("更准确说"))
    }
    @Test fun duplicateTranscriptsDoNotTurnOneObservationIntoARepeatedHabit() = runBlocking {
        val store = Store(); val model = FakeModel().apply { learnHabits = true }; val engine = engine(store, model)
        grant(engine); engine.capture(recording("压力时散步。")); engine.capture(recording("压力时散步。"))
        assertEquals(1, engine.portrait()!!.habits.single().independentEpisodes)
        assertEquals(.5, engine.portrait()!!.habits.single().confidence, .001)
    }
    @Test fun deletionDuringPsychologyFailureDropsStaleDraftsButKeepsFreshAsr() = runBlocking {
        val store = Store(); val model = FakeModel(); val engine = engine(store, model); grant(engine)
        val old = recording("旧的敏感心理原文"); engine.capture(old)
        model.failPsychology = true
        try { engine.capture(recording("新的独立原文")); fail("expected failure") } catch (_: IllegalStateException) {}
        engine.deleteRecording(old) { java.io.File(old.audioPath).delete() }
        assertFalse(engine.pending()!!.has("traits")); assertFalse(store.saved!!.contains("旧的敏感心理原文"))
        model.failPsychology = false; engine.retry()
        assertEquals(2, model.transcriptions); assertEquals(listOf("新的独立原文"), engine.portrait()!!.sources.map { it.excerpt })
    }

}
