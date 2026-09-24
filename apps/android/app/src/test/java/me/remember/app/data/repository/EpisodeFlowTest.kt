package me.remember.app.data.repository

import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import me.remember.app.model.Loadable
import me.remember.app.model.Memory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EpisodeFlowTest {
    private val recording = AudioRecording("/tmp/recording.m4a", 1_000, "audio/mp4", 12, 44_100, 1, "2026-09-25T01:00:00Z")
    private val connection = BackendConnection("https://backend.example", "token", "subject-1", "consent-1")

    @Test
    fun readyStatusShowsOnlyThePersistedResult() = runBlocking {
        val gateway = FakeGateway().apply {
            statuses += EpisodeStatus("episode-1", EpisodeStage.TRANSCRIBING)
            statuses += EpisodeStatus("episode-1", EpisodeStage.READY)
        }
        val memories = EpisodeMemoryRepository()
        val flow = EpisodeFlow(gateway, memories, pollIntervalMillis = 0)

        flow.submit(recording, connection)

        assertEquals(EpisodeUiState.Ready("episode-1", 1), flow.state.value)
        assertEquals(1, gateway.uploadCalls)
        val stored = memories.memories().first() as Loadable.Content
        assertEquals("An actual result", stored.value.single().story)
        assertEquals("episode-1", stored.value.single().episodeId)
    }

    @Test
    fun uncertainUploadRetryUsesTheSameRecordingAndDoesNotShowMockMemory() = runBlocking {
        val gateway = FakeGateway().apply {
            failFirstUpload = true
            statuses += EpisodeStatus("episode-1", EpisodeStage.READY)
        }
        val memories = EpisodeMemoryRepository()
        val flow = EpisodeFlow(gateway, memories, pollIntervalMillis = 0)

        flow.submit(recording, connection)
        assertTrue(flow.state.value is EpisodeUiState.Error)
        assertEquals(Loadable.Empty, memories.memories().value)

        flow.retry()
        assertEquals(2, gateway.uploadCalls)
        assertEquals(listOf(recording, recording), gateway.uploadedRecordings)
        assertEquals(EpisodeUiState.Ready("episode-1", 1), flow.state.value)
    }

    @Test
    fun statusRetryKeepsEpisodeIdAndDoesNotReupload() = runBlocking {
        val gateway = FakeGateway().apply {
            failFirstStatus = true
            statuses += EpisodeStatus("episode-1", EpisodeStage.READY)
        }
        val flow = EpisodeFlow(gateway, EpisodeMemoryRepository(), pollIntervalMillis = 0)

        flow.submit(recording, connection)
        val error = flow.state.value as EpisodeUiState.Error
        assertEquals("episode-1", error.episodeId)
        assertTrue(error.retryable)

        flow.retry()
        assertEquals(1, gateway.uploadCalls)
        assertEquals(EpisodeUiState.Ready("episode-1", 1), flow.state.value)
    }

    @Test
    fun failedProcessingIsTerminalAndKeepsTheOriginalEpisodeReference() = runBlocking {
        val gateway = FakeGateway().apply {
            statuses += EpisodeStatus("episode-1", EpisodeStage.FAILED, "AI_FAILED", "AI Core refused")
        }
        val flow = EpisodeFlow(gateway, EpisodeMemoryRepository(), pollIntervalMillis = 0)

        flow.submit(recording, connection)

        val error = flow.state.value as EpisodeUiState.Error
        assertEquals("episode-1", error.episodeId)
        assertEquals("AI_FAILED", error.code)
        assertFalse(error.retryable)
        flow.retry()
        assertEquals(1, gateway.uploadCalls)
    }

    private class FakeGateway : EpisodeGateway {
        var uploadCalls = 0
        var failFirstUpload = false
        var failFirstStatus = false
        val uploadedRecordings = mutableListOf<AudioRecording>()
        val statuses = ArrayDeque<EpisodeStatus>()

        override suspend fun upload(
            recording: AudioRecording,
            connection: BackendConnection,
            onProgress: (Int) -> Unit
        ): EpisodeCreated {
            uploadCalls++
            uploadedRecordings += recording
            if (failFirstUpload && uploadCalls == 1) {
                throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "connection closed", true)
            }
            onProgress(100)
            return EpisodeCreated("episode-1", "uploaded")
        }

        override suspend fun status(episodeId: String, connection: BackendConnection): EpisodeStatus {
            if (failFirstStatus) {
                failFirstStatus = false
                throw EpisodeGatewayFailure("NETWORK_UNAVAILABLE", "connection closed", true)
            }
            return statuses.removeFirst()
        }

        override suspend fun result(episodeId: String, connection: BackendConnection): EpisodeResult =
            EpisodeResult(
                episodeId,
                "model-v1",
                listOf(Memory("$episodeId:0", "", "", "An actual result", emptyList(), emptyList(), "", episodeId = episodeId))
            )
    }
}
