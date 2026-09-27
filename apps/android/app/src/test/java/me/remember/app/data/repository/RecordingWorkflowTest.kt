package me.remember.app.data.repository

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.test.runTest
import me.remember.app.model.Loadable
import org.junit.Assert.*
import org.junit.Test

class RecordingWorkflowTest {
    private val original = AudioRecording("/private/voice.m4a", 2500, "audio/mp4", 12345, 44100, 1, "2026-09-27T00:00:00Z")
    private val quote = "外婆家有桂花树。"
    private val memory = ExtractedMemory("m1", "episodic", "外婆家的桂花树", quote, .9f)
    @Test fun reviewNeverInvokesProcessorAndKeepsMachineText() = runTest {
        val audio = TestAudio(original)
        val processor = TestProcessor(memory)
        val workflow = RecordingWorkflow(audio, object : LocalAsrService {
            override suspend fun transcribe(audioRef: String) = "外婆家有贵花树。"
        }, processor)
        workflow.transcribe(original.audioPath)
        assertEquals(ProcessingStage.NeedsReview, audio.current.processingStage)
        assertNull(audio.current.reviewedAt)
        workflow.confirm(original.audioPath, quote)
        assertEquals("外婆家有贵花树。", audio.current.transcript)
        assertEquals(quote, audio.current.reviewedTranscript)
        assertNotNull(audio.current.reviewedAt)
        assertEquals(0, processor.calls)
        workflow.organize(original.audioPath, true)
        assertEquals(quote, processor.received)
        assertEquals(ProcessingStage.Complete, audio.current.processingStage)
    }
    @Test fun consentAndConfirmationRequiredBeforeRemoteCall() = runTest {
        val audio = TestAudio(original.copy(transcript = quote))
        val processor = TestProcessor(memory)
        val workflow = RecordingWorkflow(audio, null, processor)
        assertTrue(runCatching { workflow.organize(original.audioPath, true) }.isFailure)
        workflow.confirm(original.audioPath, quote)
        assertTrue(runCatching { workflow.organize(original.audioPath, false) }.isFailure)
        assertEquals(0, processor.calls)
    }
    @Test fun failurePreservesAudioAndBothTextsAndRetryIsIdempotent() = runTest {
        val audio = TestAudio(original.copy(transcript = "机器原文"))
        val processor = TestProcessor(memory).apply { fail = true }
        val workflow = RecordingWorkflow(audio, null, processor)
        workflow.confirm(original.audioPath, quote)
        assertTrue(runCatching { workflow.organize(original.audioPath, true) }.isFailure)
        assertEquals(ProcessingStage.Failed, audio.current.processingStage)
        assertEquals(original.audioPath, audio.current.audioPath)
        assertEquals("机器原文", audio.current.transcript)
        assertEquals(quote, audio.current.reviewedTranscript)
        processor.fail = false
        workflow.organize(original.audioPath, true)
        workflow.organize(original.audioPath, true)
        assertEquals(2, processor.calls)
        assertEquals(listOf(memory), audio.current.memories)
    }
    @Test fun unavailableServicesPreserveRecording() = runTest {
        val audio = TestAudio(original)
        val workflow = RecordingWorkflow(audio, null)
        assertTrue(runCatching { workflow.transcribe(original.audioPath) }.isFailure)
        assertEquals(original.byteSize, audio.current.byteSize)
        assertTrue(audio.current.processingError!!.contains("本机转写暂不可用"))
        audio.updateRecording(audio.current.copy(transcript = quote))
        workflow.confirm(original.audioPath, quote)
        assertTrue(runCatching { workflow.organize(original.audioPath, true) }.isFailure)
        assertEquals(quote, audio.current.reviewedTranscript)
        assertTrue(audio.current.processingError!!.contains("尚未连接"))
    }
    @Test fun inventedEvidenceRejected() = runTest {
        val audio = TestAudio(original.copy(transcript = quote))
        val workflow = RecordingWorkflow(audio, null, TestProcessor(memory.copy(evidence = "不存在的引文")))
        workflow.confirm(original.audioPath, quote)
        assertTrue(runCatching { workflow.organize(original.audioPath, true) }.isFailure)
        assertTrue(audio.current.memories.isEmpty())
    }
    @Test fun correctedReviewInvalidatesOldResultsButKeepsHistory() = runTest {
        val audio = TestAudio(original.copy(transcript = quote, reviewedTranscript = quote, reviewedAt = "then",
            processingStage = ProcessingStage.Complete, memories = listOf(memory)))
        RecordingWorkflow(audio, null).confirm(original.audioPath, "院子里有桂花树。")
        assertEquals("superseded", audio.current.memories.single().status)
        assertEquals(quote, audio.current.memories.single().evidence)
        assertEquals(quote, audio.current.transcript)
        assertEquals(ProcessingStage.NeedsReview, audio.current.processingStage)
    }
    @Test fun cancellationPersistsInterruptedStateAndRethrows() = runTest {
        val audio = TestAudio(original)
        val workflow = RecordingWorkflow(audio, object : LocalAsrService {
            override suspend fun transcribe(audioRef: String): String = throw CancellationException("stopped")
        })
        assertTrue(runCatching { workflow.transcribe(original.audioPath) }.exceptionOrNull() is CancellationException)
        assertEquals(ProcessingStage.Failed, audio.current.processingStage)
        assertTrue(audio.current.processingError!!.contains("中断"))
    }
    @Test fun oldSidecarsDoNotInventConsentNewSidecarsRoundTripAndInterruptsRecover() {
        val old = """{"audioPath":"/old.m4a","durationMillis":2000,"mimeType":"audio/mp4","byteSize":100,"sampleRate":44100,"channelCount":1,"transcript":"机器旧文"}"""
        val legacy = RecordingMetadata.decode(old)
        assertNull(legacy.reviewedAt)
        assertNull(legacy.reviewedTranscript)
        assertEquals(ProcessingStage.NeedsReview, legacy.processingStage)
        val reviewed = original.copy(transcript = "原文", reviewedTranscript = quote, reviewedAt = "now",
            memories = listOf(memory.copy(sourceType = "THIRD_PARTY")), processingStage = ProcessingStage.Organizing)
        assertEquals(reviewed, RecordingMetadata.decode(RecordingMetadata.encode(reviewed)))
        val recovered = RecordingMetadata.recoverInterrupted(reviewed)
        assertEquals(ProcessingStage.Failed, recovered.processingStage)
        assertEquals(quote, recovered.reviewedTranscript)
        assertEquals(reviewed.memories, recovered.memories)
        assertEquals(recovered, RecordingMetadata.recoverInterrupted(recovered))
    }
    @Test fun archiveEmissionPreservesSourcesAndDeletionRemovesOnlyMemory() = runTest {
        val audio=TestAudio(original.copy(transcript=quote,memories=listOf(memory)))
        val emissions=mutableListOf<Loadable<List<me.remember.app.model.Memory>>>()
        val collection=launch(start=CoroutineStart.UNDISPATCHED) { LocalMemoryRepository(audio).memories().take(2).toList(emissions) }
        audio.updateRecording(audio.current.copy(memories=listOf(memory.copy(status="deleted"))))
        collection.join()
        val visible=(emissions.first() as Loadable.Content).value.single()
        assertEquals(original.audioPath,visible.sourceRecordingPath)
        assertEquals(quote,visible.evidence)
        assertEquals("SUBJECT",visible.sourceType)
        assertEquals(Loadable.Empty,emissions.last())
        assertEquals(quote,audio.current.transcript)
        assertEquals(original.audioPath,audio.current.audioPath)
    }
}
private class TestProcessor(private val result: ExtractedMemory) : ReviewedMemoryProcessor {
    override val dataUseDescription = "Test adapter only"
    var calls = 0; var fail = false; var received: String? = null
    override suspend fun organize(confirmedText: String): MemoryExtractionResult {
        calls++; received = confirmedText
        check(!fail) { "测试服务暂不可用" }
        return MemoryExtractionResult(listOf(result, result), "test-v1")
    }
}
private class TestAudio(initial: AudioRecording) : AudioCaptureService {
    val archive = MutableStateFlow(listOf(initial))
    val current get() = archive.value.single()
    override fun observeRecordings() = archive
    override fun recordings() = archive.value
    override fun updateRecording(recording: AudioRecording) { archive.value = listOf(recording) }
    override fun deleteMemory(recording: AudioRecording, memoryId: String) = Unit
    override suspend fun start() = current
    override suspend fun pause() = Unit
    override suspend fun resume() = Unit
    override suspend fun stop() = current
    override fun elapsedMillis() = current.durationMillis
    override fun latestRecording() = current
    override fun play(recording: AudioRecording, onComplete: () -> Unit, onError: (String) -> Unit) = Unit
    override fun stopPlayback() = Unit
}
