package me.remember.app.data.repository

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
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
        fun enqueue(json: JSONObject) { server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(json.toString())) }
        server.start()
        try {
            val repo = AgentRepository(HttpAgentGateway())
            val connection = BackendConnection(server.url("/").toString(), "test-actor-token", subject, "recording-consent", true)
            enqueue(JSONObject())
            enqueue(initial)
            repo.enable(connection)
            assertEquals(1, repo.state.value.snapshot?.revision)
            enqueue(data.getJSONObject("twin"))
            repo.ask("工作日下班后喜欢怎么度过？")
            assertNull(repo.state.value.error)
            assertEquals("ORIGINAL", repo.state.value.answer?.type)
            assertEquals(repo.state.value.answer?.answer, repo.state.value.answer?.evidence?.single()?.excerpt)
            enqueue(data.getJSONObject("locked_calibration"))
            repo.lock("工作日下班后喜欢怎么度过？")
            val locked = checkNotNull(repo.state.value.calibration)
            assertEquals("LOCKED", locked.state)
            enqueue(initial)
            enqueue(data.getJSONObject("completed_calibration"))
            enqueue(data.getJSONObject("corrected_model"))
            enqueue(data.getJSONObject("plan"))
            repo.submit("我现在喜欢先和家人聊聊天，再自己待一会儿。")
            assertNull(repo.state.value.error)
            assertEquals(2, repo.state.value.snapshot?.revision)
            assertEquals(5, repo.state.value.calibration?.diffs?.size)
            assertEquals(locked.digest, repo.state.value.calibration?.digest)
            assertEquals(locked.lockedAnswer, repo.state.value.calibration?.lockedAnswer)
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
            val humanBody = JSONObject(requests[5].body.readUtf8())
            assertEquals(1,humanBody.getInt("expected_revision"))
            assertTrue(humanBody.has("human_answer"))
        } finally { server.shutdown() }
    }
}
