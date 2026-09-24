package me.remember.app.data.repository

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class HttpEpisodeGatewayTest {
    @get:Rule val files = TemporaryFolder()

    @Test
    fun retrySendsTheSameKeyAndParsesRealBackendShapes() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(201)
            .setBody("""{"episode_id":"episode-1","upload_status":"uploaded"}"""))
        server.enqueue(MockResponse().setResponseCode(200)
            .setBody("""{"episode_id":"episode-1","upload_status":"uploaded"}"""))
        server.enqueue(MockResponse().setResponseCode(200)
            .setBody("""{"episode_id":"episode-1","status":"ready","trace_id":"trace-1"}"""))
        server.enqueue(MockResponse().setResponseCode(200)
            .setBody("""{"episode_id":"episode-1","status":"ready","model_version":"fixture-ai-v2","memory_items":[{"memory_type":"EVENT","content":"A walk by the river.","source_type":"AI_INFERENCE","evidence_ids":["ev-1"],"confidence":0.75,"model_version":"fixture-ai-v2","prompt_version":"extract-v2","schema_version":"integration-contract-v0.1.2"}]}"""))
        server.start()
        try {
            val audio = files.newFile("recording.m4a").apply { writeBytes(byteArrayOf(1, 2, 3, 4)) }
            val recording = AudioRecording(audio.absolutePath, 2_000, "audio/mp4", 4, 44_100, 1, "2026-09-25T01:00:00Z")
            val connection = BackendConnection(server.url("/").toString(), "actor-token", "subject-1", "consent-1")
            val gateway = HttpEpisodeGateway()
            val progress = mutableListOf<Int>()

            val first = gateway.upload(recording, connection, progress::add)
            val replay = gateway.upload(recording, connection, progress::add)
            val status = gateway.status(first.episodeId, connection)
            val result = gateway.result(first.episodeId, connection)

            val requests = List(4) { server.takeRequest() }
            val uploads = requests.take(2).map { it.body.readUtf8() }
            assertEquals("episode-1", first.episodeId)
            assertEquals(first, replay)
            assertTrue(uploads.all { it.contains("name=\"idempotency_key\"\r\n\r\n${idempotencyKeyFor(recording)}") })
            assertTrue(uploads.all { it.contains("name=\"recording_consent_id\"\r\n\r\nconsent-1") })
            assertTrue(uploads.all { it.contains("name=\"file\"; filename=\"recording.m4a\"") })
            assertTrue(requests.all { it.getHeader("Authorization") == "Bearer actor-token" })
            assertEquals(100, progress.last())
            assertEquals(EpisodeStage.READY, status.stage)
            assertEquals("episode-1", result.episodeId)
            assertEquals("A walk by the river.", result.memories.single().story)
            assertEquals("AI_INFERENCE", result.memories.single().sourceType)
            assertEquals(listOf("ev-1"), result.memories.single().evidenceIds)
            assertFalse(result.memories.single().hasPlayableAudio)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun failedUploadKeepsServerErrorAndRetryDecision() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(409)
            .setBody("""{"error_code":"IDEMPOTENCY_CONFLICT","error_message":"Different audio"}"""))
        server.start()
        try {
            val audio = files.newFile("recording.m4a").apply { writeBytes(byteArrayOf(1, 2, 3)) }
            val recording = AudioRecording(audio.absolutePath, 1_000, "audio/mp4", 3, 44_100, 1, "2026-09-25T01:00:00Z")
            val connection = BackendConnection(server.url("/").toString(), "token", "subject", "consent")
            val error = try {
                HttpEpisodeGateway().upload(recording, connection) {}
                error("Expected an idempotency conflict")
            } catch (failure: EpisodeGatewayFailure) {
                failure
            }
            assertEquals("IDEMPOTENCY_CONFLICT", error.code)
            assertFalse(error.retryable)
        } finally {
            server.shutdown()
        }
    }
}
