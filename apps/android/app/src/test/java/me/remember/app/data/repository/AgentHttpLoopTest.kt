package me.remember.app.data.repository

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.TimeUnit

/** Actual Backend/AI fixture-run payloads consumed through Android's real HTTP adapter. */
class AgentHttpLoopTest {
    @Test fun serverPayloadsCompleteAndroidAskLockCompareRefreshAndProvenance() = runBlocking {
        val text = checkNotNull(javaClass.getResource("/agent-loop-http.json")).readText()
        val data = JSONObject(text)
        val initial = data.getJSONObject("initial_model")
        val subject = initial.getString("subject_id")
        val server = MockWebServer()
        fun enqueue(json: Any) { server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(json.toString())) }
        server.start()
        try {
            val repo = AgentRepository(HttpAgentGateway())
            val connection = BackendConnection(server.url("/").toString(), "test-actor-token", subject, "recording-consent", true)
            enqueue(JSONObject())
            enqueue(initial)
            val materials = data.getJSONObject("twin").getJSONArray("evidence")
            enqueue(materials)
            repo.enable(connection)
            assertEquals(1, repo.state.value.snapshot?.revision)
            assertEquals(materials.getJSONObject(0).getString("excerpt"), repo.state.value.materials.single().excerpt)
            enqueue(data.getJSONObject("locked_calibration"))
            repo.ask("工作日下班后喜欢怎么度过？")
            assertNull(repo.state.value.error)
            assertEquals("ORIGINAL", repo.state.value.answer?.type)
            assertEquals(repo.state.value.answer?.answer, repo.state.value.answer?.evidence?.single()?.excerpt)
            val locked = checkNotNull(repo.state.value.calibration)
            assertEquals("LOCKED", locked.state)
            assertEquals(locked.lockedAnswer, repo.state.value.answer)
            assertTrue(repo.state.value.canCorrect(locked.question))
            assertFalse(repo.state.value.canCorrect("不同的问题"))
            enqueue(data.getJSONObject("completed_calibration"))
            enqueue(data.getJSONObject("corrected_model"))
            enqueue(materials)
            repo.submit("我现在喜欢先和家人聊聊天，再自己待一会儿。")
            assertNull(repo.state.value.error)
            assertEquals(2, repo.state.value.snapshot?.revision)
            assertEquals(5, repo.state.value.calibration?.diffs?.size)
            assertEquals(locked.digest, repo.state.value.calibration?.digest)
            assertEquals(locked.lockedAnswer, repo.state.value.calibration?.lockedAnswer)
            assertEquals(locked.lockedAnswer, repo.state.value.answer)
            assertEquals("我现在喜欢先和家人聊聊天，再自己待一会儿。", repo.state.value.correction)
            assertFalse(repo.state.value.canCorrect(locked.question))
            enqueue(data.getJSONObject("plan"))
            repo.plan()
            assertNotNull(repo.state.value.plan)
            val evidence = data.getJSONObject("twin").getJSONArray("evidence").getJSONObject(0)
            enqueue(evidence)
            repo.inspect(evidence.getString("evidence_id"))
            assertEquals(evidence.getString("excerpt"),repo.state.value.inspectedEvidence?.excerpt)
            val requests = (0 until 9).map { checkNotNull(server.takeRequest(1, TimeUnit.SECONDS)) }
            assertTrue(requests.all { it.getHeader("Authorization") == "Bearer test-actor-token" })
            assertTrue(requests.all { it.path!!.startsWith("/experimental/agent/v1/subjects/$subject/") })
            val lockBody = JSONObject(requests[3].body.readUtf8())
            assertEquals(setOf("question"),lockBody.keys().asSequence().toSet())
            assertEquals("/experimental/agent/v1/subjects/$subject/calibrations", requests[3].path)
            val humanBody = JSONObject(requests[4].body.readUtf8())
            assertEquals(1,humanBody.getInt("expected_revision"))
            assertTrue(humanBody.has("human_answer"))
        } finally { server.shutdown() }
    }

    @Test fun failedModelReadPreservesTheSavedCorrectionAndAllowsReadRetry() = runBlocking {
        val data = JSONObject(checkNotNull(javaClass.getResource("/agent-loop-http.json")).readText())
        val initial = data.getJSONObject("initial_model")
        val subject = initial.getString("subject_id")
        val server = MockWebServer()
        fun enqueue(json: Any) { server.enqueue(MockResponse().setBody(json.toString())) }
        server.start()
        try {
            val repo = AgentRepository(HttpAgentGateway())
            enqueue(JSONObject()); enqueue(initial); enqueue(JSONArray())
            repo.enable(BackendConnection(server.url("/").toString(), "test-token", subject, "consent", true))
            enqueue(data.getJSONObject("locked_calibration"))
            repo.ask("工作日下班后喜欢怎么度过？")
            enqueue(data.getJSONObject("completed_calibration"))
            server.enqueue(MockResponse().setResponseCode(503).setBody("{}"))
            repo.submit("本人校正")
            assertEquals("COMPLETED", repo.state.value.calibration?.state)
            assertEquals("本人校正", repo.state.value.correction)
            assertNotNull(repo.state.value.answer)
            assertNotNull(repo.state.value.error)
            enqueue(data.getJSONObject("corrected_model")); enqueue(JSONArray())
            repo.refresh()
            assertEquals(2, repo.state.value.snapshot?.revision)
            assertNull(repo.state.value.error)
            enqueue(data.getJSONObject("locked_calibration"))
            repo.ask("工作日下班后喜欢怎么度过？")
            assertNull(repo.state.value.correction)
            assertFalse(repo.state.value.canCorrect("工作日下班后喜欢怎么度过？"))
            repo.submit("新的校正")
            assertTrue(repo.state.value.error!!.contains("理解已变化"))
        } finally { server.shutdown() }
    }

    @Test fun withdrawnMaterialsStayHiddenWhenTheSubsequentEvidenceReadFails() = runBlocking {
        val data = JSONObject(checkNotNull(javaClass.getResource("/agent-loop-http.json")).readText())
        val initial = data.getJSONObject("initial_model")
        val server = MockWebServer()
        fun enqueue(json: Any) { server.enqueue(MockResponse().setBody(json.toString())) }
        server.start()
        try {
            val repo = AgentRepository(HttpAgentGateway())
            enqueue(JSONObject()); enqueue(initial); enqueue(data.getJSONObject("twin").getJSONArray("evidence"))
            repo.enable(BackendConnection(server.url("/").toString(), "test-token", initial.getString("subject_id"), "consent", true))
            enqueue(data.getJSONObject("locked_calibration"))
            repo.ask("工作日下班后喜欢怎么度过？")
            enqueue(data.getJSONObject("corrected_model"))
            server.enqueue(MockResponse().setResponseCode(503).setBody("{}"))
            repo.withdraw(repo.state.value.materials.single().episodeId!!)
            assertNotNull(repo.state.value.error)
            assertTrue(repo.state.value.materials.isEmpty())
            assertNull(repo.state.value.snapshot)
            assertNull(repo.state.value.answer)
            assertNull(repo.state.value.calibration)
        } finally { server.shutdown() }
    }
}
