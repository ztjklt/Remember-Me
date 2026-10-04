package me.remember.app.data.repository

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AgentRepositoryTest {
    private fun connection(subject: String = "subject-a", token: String = "actor-a") =
        BackendConnection("http://localhost:8000", token, subject, "recording-consent", true)

    private fun model(subject: String) = JSONObject().put("subject_id",subject).put("revision",1)
        .put("model_version","fixture-ai-v2").put("schema_version","agent-loop-v0.2-experimental").put("traits",org.json.JSONArray())

    @Test fun switchingSubjectOrCredentialClearsAllVisibleState() = runBlocking {
        val gateway = object : AgentGateway {
            override suspend fun request(connection: BackendConnection,path: String,method: String,body: JSONObject?) =
                if (path=="/model") model(connection.subjectId) else JSONObject()
        }
        val repo = AgentRepository(gateway)
        repo.enable(connection())
        assertEquals("subject-a",repo.state.value.snapshot?.subjectId)
        repo.bind(connection("subject-b"))
        assertNull(repo.state.value.snapshot)
        assertNull(repo.state.value.answer)
        assertFalse(repo.state.value.configured)
        repo.enable(connection("subject-b"))
        repo.bind(connection("subject-b","other-actor"))
        assertNull(repo.state.value.snapshot)
    }

    @Test fun oldResponseCannotOverwriteNewSubjectSession() = runBlocking {
        val waiting = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val gateway = object : AgentGateway {
            override suspend fun request(connection: BackendConnection,path: String,method: String,body: JSONObject?): JSONObject {
                if (path=="/model/refresh") { waiting.complete(Unit);release.await() }
                return if (path.startsWith("/model")) model(connection.subjectId)
                    else if (path=="/plan") JSONObject().put("question","q").put("reason","r") else JSONObject()
            }
        }
        val repo=AgentRepository(gateway)
        repo.enable(connection())
        val operation=launch { repo.refresh() }
        waiting.await()
        repo.bind(connection("subject-b"))
        release.complete(Unit)
        operation.join()
        assertNull(repo.state.value.snapshot)
        assertNull(repo.state.value.plan)
        repo.enable(connection("subject-b"))
        assertEquals("subject-b",repo.state.value.snapshot?.subjectId)
    }

    @Test fun revokedConsentClearsCachedAnswersAndModel() = runBlocking {
        val gateway = object : AgentGateway {
            override suspend fun request(connection: BackendConnection,path: String,method: String,body: JSONObject?): JSONObject {
                if (path=="/twin") throw EpisodeGatewayFailure("CONSENT_INVALID","revoked",false)
                return if (path=="/model") model(connection.subjectId) else JSONObject()
            }
        }
        val repo=AgentRepository(gateway)
        repo.enable(connection())
        repo.ask("我喜欢什么？")
        assertFalse(repo.state.value.configured)
        assertNull(repo.state.value.snapshot)
        assertEquals("revoked",repo.state.value.error)
    }

    @Test fun aForeignSubjectResponseIsRefused() = runBlocking {
        val gateway = object : AgentGateway {
            override suspend fun request(connection: BackendConnection,path: String,method: String,body: JSONObject?) =
                if (path=="/model") model("other-subject") else JSONObject()
        }
        val repo=AgentRepository(gateway)
        repo.enable(connection())
        assertNull(repo.state.value.snapshot)
        assertNotNull(repo.state.value.error)
    }
}
