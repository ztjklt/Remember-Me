package me.remember.app.data.local

import kotlinx.coroutines.runBlocking
import me.remember.app.data.repository.AudioRecording
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class LocalModelClientTest {
    @get:Rule val files = TemporaryFolder()
    @Test fun nativeAsrUsesAudioAndParsesTheConfiguredProviderEnvelope() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"output":{"output":{"sentence":{"text":"合成测试原文"}}}}"""))
            val config = ModelEndpoint(server.url("/").toString(), "test-asr", "test-key")
            val recording = files.newFile("clip.m4a").apply { writeBytes(byteArrayOf(1, 2, 3)) }
            val audio = AudioRecording(recording.path, 1000, "audio/mp4", 3, 44100, 1, "2026-01-01T00:00:00Z")
            assertEquals("合成测试原文", HttpLocalModelClient().transcribe(audio, LocalModelSettings(config, config, SpeechProtocol.DASHSCOPE)))
            val request = server.takeRequest()
            assertEquals("/api/v1/services/aigc/multimodal-generation/generation", request.path)
            assertTrue(request.body.readUtf8().contains("data:audio/mp4;base64,AQID"))
        }
    }
    @Test fun languageCallsUseJsonAndDoNotFollowRedirectsOrExposeErrorBodies() = runBlocking {
        MockWebServer().use { server ->
            val config = ModelEndpoint(server.url("/v1").toString(), "test-llm", "private-key")
            server.enqueue(MockResponse().setBody("""{"choices":[{"finish_reason":"stop","message":{"content":"{\"ok\":true}"}}]}"""))
            assertTrue(HttpLocalModelClient().complete("test", JSONObject(), config).getBoolean("ok"))
            assertEquals("/v1/chat/completions", server.takeRequest().path)
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://example.invalid").setBody("private-key"))
            try { HttpLocalModelClient().complete("test", JSONObject(), config); fail("redirect accepted") }
            catch (e: IllegalStateException) { assertFalse(e.message!!.contains("private-key")); assertTrue(e.message!!.contains("302")) }
            server.takeRequest()
            assertEquals(2, server.requestCount)
        }
    }
    @Test fun truncatedModelOutputIsActionableAndNeverAcceptedAsMemory() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"choices":[{"finish_reason":"length","message":{"content":""}}]}"""))
            val config = ModelEndpoint(server.url("/").toString(), "synthetic", "synthetic-key", "none")
            try { HttpLocalModelClient().complete("JSON test", JSONObject(), config); fail("truncated response accepted") }
            catch (e: IllegalStateException) { assertTrue(e.message!!.contains("输出超限")); assertFalse(e.message!!.contains(config.apiKey)) }
            val request = JSONObject(server.takeRequest().body.readUtf8())
            assertEquals("none", request.getString("reasoning_effort"))
        }
    }
}
