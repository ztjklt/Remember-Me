package me.remember.app.data.agent

import kotlinx.coroutines.runBlocking
import me.remember.app.data.repository.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ReviewedAgentProcessorTest {
    private val original = AudioRecording("/private/one.m4a", 1000, "audio/mp4", 100, 44100, 1, "2026-10-08T00:00:00Z")
    private class Model : StructuredAgentModel {
        override val modelVersion = "synthetic-model"
        val delegate = TestAgentModel()
        val sent = mutableListOf<String>()
        override suspend fun complete(prompt: String, input: JSONObject): JSONObject {
            sent += input.toString()
            if (input.optString("role") != "memory_observer") return delegate.complete(prompt, input)
            val text = input.getJSONArray("materials").getJSONObject(0).getString("excerpt")
            return JSONObject().put("observations", JSONArray().put(JSONObject().put("dimension", "identity")
                .put("summary", "核对后的姓名信息").put("quote", text).put("event_time", JSONObject.NULL)
                .put("time_text", "").put("certainty", "REPORTED")
                .put("attributes", JSONObject().put("facet", "NAME").put("value", text))))
        }
    }
    @Test fun existingWorkflowUsesConfirmedTextAndKeepsMachineTextLocal() = runBlocking {
        val audio = CoreTestAudio(original); val model = Model(); val store = TestJournal()
        val processor = ReviewedAgentProcessor(AgentMemoryEngine("one", store, model))
        var transcriptions = 0
        val workflow = RecordingWorkflow(audio, object : LocalAsrService {
            override suspend fun transcribe(audioRef: String): String { transcriptions++; return "ASR_WRONG_NAME" }
        }, processor)
        workflow.transcribe(original.audioPath); workflow.confirm(original.audioPath, "名字是林宸")
        workflow.organize(original.audioPath, true); val calls = model.sent.size
        workflow.organize(original.audioPath, true)
        assertEquals(1, transcriptions); assertEquals(calls, model.sent.size)
        assertEquals(ProcessingStage.Complete, audio.current.processingStage)
        assertEquals("ASR_WRONG_NAME", audio.current.transcript)
        assertTrue(store.saved!!.contains("ASR_WRONG_NAME")); assertTrue(model.sent.none { "ASR_WRONG_NAME" in it })
        assertEquals("名字是林宸", audio.current.memories.single().evidence)
        assertEquals("AI_INFERENCE", audio.current.memories.single().sourceType)
        assertTrue(runCatching { processor.organize(audio.current, false) }.isFailure)
    }
    @Test fun editingTheReviewInvalidatesOldAnswersWithoutReplacingMachineText() = runBlocking {
        val audio = CoreTestAudio(original.copy(transcript = "机器原文")); val engine = AgentMemoryEngine("one", TestJournal(), Model())
        val workflow = RecordingWorkflow(audio, null, ReviewedAgentProcessor(engine))
        workflow.confirm(original.audioPath, "名字是林晨"); workflow.organize(original.audioPath, true)
        engine.ask("我是谁？", true)
        workflow.confirm(original.audioPath, "名字是林宸"); workflow.organize(original.audioPath, true)
        assertEquals("INVALIDATED", engine.history().getJSONObject(0).getString("state"))
        assertEquals("名字是林宸", engine.originalMaterials().getJSONObject(0).getString("excerpt"))
        assertEquals("机器原文", audio.current.transcript)
        assertEquals(listOf("superseded", "active"), audio.current.memories.map { it.status })
    }
    @Test fun retryInTheExistingWorkflowReusesCoreCheckpoints() = runBlocking {
        val audio = CoreTestAudio(original.copy(transcript = "机器原文")); val model = Model().apply { delegate.failPsychology = true }
        val engine = AgentMemoryEngine("one", TestJournal(), model)
        val workflow = RecordingWorkflow(audio, null, ReviewedAgentProcessor(engine))
        workflow.confirm(original.audioPath, "名字是林宸")
        assertTrue(runCatching { workflow.organize(original.audioPath, true) }.isFailure)
        assertEquals(ProcessingStage.Failed, audio.current.processingStage)
        model.delegate.failPsychology = false; workflow.organize(original.audioPath, true)
        assertEquals(1, model.delegate.traitCalls); assertEquals(1, engine.originalMaterials().length())
        assertEquals(ProcessingStage.Complete, audio.current.processingStage)
    }
}
internal class CoreTestAudio(var current: AudioRecording) : AudioCaptureService {
    override fun recordings() = listOf(current)
    override fun updateRecording(recording: AudioRecording) { current = recording }
    override suspend fun start() = current
    override suspend fun pause() = Unit
    override suspend fun resume() = Unit
    override suspend fun stop() = current
    override fun elapsedMillis() = current.durationMillis
    override fun latestRecording() = current
    override fun deleteMemory(recording: AudioRecording, memoryId: String) = Unit
    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) = Unit
    override fun stopPlayback() = Unit
}
