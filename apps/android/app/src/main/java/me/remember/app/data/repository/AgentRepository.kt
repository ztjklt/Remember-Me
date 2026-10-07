package me.remember.app.data.repository

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import me.remember.app.model.*
import org.json.JSONArray
import org.json.JSONObject

/** Subject + credential scoped state. Backend remains the durable source of truth. */
class AgentRepository(private val gateway: AgentGateway) : UnderstandingRepository {
    private var connection: BackendConnection? = null
    private var epoch = 0L
    private val mutex = Mutex()
    private val mutableState = MutableStateFlow(AgentUiState())
    val state: StateFlow<AgentUiState> = mutableState

    fun currentConnection(): BackendConnection? = connection

    fun bind(value: BackendConnection) {
        if (connection != value) {
            connection = value
            epoch++
            mutableState.value = AgentUiState()
        }
    }

    suspend fun enable(value: BackendConnection) {
        bind(value)
        operation { c ->
            check(c.subjectSingleSpeaker) { "请明确同意 Cloud Twin 并声明是本人单人录音。" }
            gateway.request(c, "/grant", "POST", JSONObject()
                .put("recording_consent_id", c.recordingConsentId)
                .put("cloud_twin_consent", true).put("subject_single_speaker", true))
            AgentUiState(configured = true, snapshot = snapshot(gateway.request(c, "/model"), c), materials = materials(c))
        }
    }

    suspend fun refresh() = operation { c ->
        val model = snapshot(gateway.request(c, "/model"), c)
        mutableState.value.copy(snapshot = model, materials = materials(c))
    }

    suspend fun ask(question: String) = operation { c ->
        val text = question.trim()
        require(text.isNotEmpty()) { "请先填写问题。" }
        mutableState.value = mutableState.value.copy(answer = null, calibration = null, correction = null)
        val locked = calibration(gateway.request(c, "/calibrations", "POST", JSONObject().put("question", text)), c)
        mutableState.value.copy(answer = locked.lockedAnswer, calibration = locked)
    }

    suspend fun lock(question: String) = ask(question)

    suspend fun resume(calibrationId: String) = operation { c ->
        require(calibrationId.matches(Regex("[A-Za-z0-9._~-]+")))
        val restored = calibration(gateway.request(c, "/calibrations/$calibrationId"), c)
        mutableState.value.copy(calibration = restored, answer = restored.lockedAnswer, correction = restored.humanAnswer)
    }

    suspend fun submit(humanAnswer: String, question: String? = null) {
        var completedId: String? = null
        operation { c ->
            val current = checkNotNull(mutableState.value.calibration) { "请先提问，再校正这次回答。" }
            check(current.state == "LOCKED" && (question == null || question.trim() == current.question)) {
                "问题已改变或校正已完成，请重新提问。"
            }
            check(mutableState.value.snapshot?.revision == current.lockedAnswer.revision) {
                "理解已变化，请重新提问后再校正。"
            }
            val text = humanAnswer.trim()
            require(text.isNotEmpty()) { "请填写本人的校正。" }
            val completed = calibration(gateway.request(c, "/calibrations/${current.id}/submit", "POST", JSONObject()
                .put("human_answer", text).put("expected_revision", current.lockedAnswer.revision)), c)
            completedId = completed.id
            mutableState.value.copy(calibration = completed, answer = completed.lockedAnswer, correction = text)
        }
        // Preserve the saved correction if reading the updated model fails.
        if (completedId != null && mutableState.value.calibration?.id == completedId) refresh()
    }

    suspend fun plan() = operation { c -> mutableState.value.copy(plan = parsePlan(gateway.request(c, "/plan"))) }

    suspend fun inspect(evidenceId: String) = operation { c ->
        require(evidenceId.matches(Regex("[A-Za-z0-9._~-]+")))
        val e = gateway.request(c, "/evidence/$evidenceId")
        mutableState.value.copy(inspectedEvidence = evidence(e))
    }

    suspend fun revoke() = operation { c ->
        gateway.request(c, "/grant", "DELETE")
        AgentUiState(configured = false)
    }

    suspend fun withdraw(episodeId: String) = operation { c ->
        require(episodeId.matches(Regex("[A-Za-z0-9._~-]+")))
        mutableState.value = mutableState.value.copy(snapshot = null, materials = emptyList(),
            answer = null, calibration = null, inspectedEvidence = null, correction = null)
        mutableState.value.copy(snapshot = snapshot(gateway.request(c, "/episodes/$episodeId/use", "DELETE"), c),
            materials = materials(c), answer = null, calibration = null, inspectedEvidence = null, correction = null)
    }

    private suspend fun operation(block: suspend (BackendConnection) -> AgentUiState) = mutex.withLock {
        val capturedEpoch = epoch
        val c = connection ?: return@withLock
        mutableState.value = mutableState.value.copy(busy = true, error = null)
        try {
            val next = block(c)
            if (epoch == capturedEpoch) mutableState.value = next.copy(busy = false, error = null)
        } catch (error: CancellationException) {
            if (epoch == capturedEpoch) mutableState.value = mutableState.value.copy(busy = false)
            throw error
        } catch (error: Exception) {
            if (epoch == capturedEpoch) {
                val failure = error as? EpisodeGatewayFailure
                mutableState.value = if (failure?.code in setOf("AUTH_INVALID", "AUTH_REQUIRED", "CONSENT_INVALID", "CONSENT_NOT_FOUND"))
                    AgentUiState(error = error.message)
                else mutableState.value.copy(busy = false, error = error.message ?: "Agent 请求失败。")
            }
        }
    }

    override fun understanding(): Flow<Loadable<PersonModelView>> = state.map { s ->
        when {
            s.error != null -> Loadable.Error(s.error)
            s.busy && s.snapshot == null -> Loadable.Loading
            s.snapshot == null -> Loadable.Empty
            else -> {
                val model = s.snapshot
                val domains = PersonDomain.entries.map { domain -> PersonDomainView(domain,
                    model.traits.filter { domainOf(it.domain) == domain && it.status != "SUPERSEDED" }.map { t ->
                        PersonTrait(t.id,t.statement,null,"AI_INFERENCE",null,t.evidenceIds,null,
                            context = t.context, status = t.status, counterEvidenceIds = t.counterEvidenceIds)
                    }) }
                Loadable.Content(PersonModelView(domains,emptyList(),emptyList(),null,model.revision,model.modelVersion))
            }
        }
    }

    private fun domainOf(domain: String): PersonDomain = when (domain) {
        "EPISODIC_MEMORY" -> PersonDomain.EPISODIC
        "DECISION_PATTERNS" -> PersonDomain.DECISIONS
        else -> PersonDomain.valueOf(domain)
    }

    private fun schema(json: JSONObject, c: BackendConnection) {
        check(json.getString("schema_version") == "agent-loop-v0.2-experimental") { "Agent schema 不兼容。" }
        check(json.getString("subject_id") == c.subjectId) { "Backend 返回了不同 Subject。" }
        check(json.getInt("revision") >= 0)
    }

    private fun snapshot(json: JSONObject, c: BackendConnection): AgentSnapshot {
        schema(json, c)
        return AgentSnapshot(c.subjectId,json.getInt("revision"),json.getString("model_version"),json.getJSONArray("traits").objects().map { t ->
            domainOf(t.getString("domain")) // reject unregistered domains
            AgentTrait(t.getString("trait_id"),t.getString("domain"),t.getString("statement"),t.getString("context"),
                t.getString("status"),t.getJSONArray("evidence_ids").strings(),t.getJSONArray("counter_evidence_ids").strings(),
                t.getString("valid_from"),t.nullableString("valid_to"))
        })
    }

    private fun answer(json: JSONObject, c: BackendConnection): AgentAnswer {
        schema(json,c)
        val type = json.getString("response_type")
        check(type in setOf("ORIGINAL","SIMULATION","INSUFFICIENT"))
        val evidence = json.getJSONArray("evidence").objects().map { evidence(it) }
        check(evidence.map { it.id } == json.getJSONArray("evidence_ids").strings())
        if (type == "ORIGINAL") check(evidence.size == 1 && json.getString("answer") == evidence.single().excerpt)
        return AgentAnswer(c.subjectId,json.getInt("revision"),type,json.getString("answer"),evidence,
            json.getJSONArray("limitations").strings(),json.getString("model_version"))
    }

    private fun calibration(json: JSONObject, c: BackendConnection): AgentCalibration {
        val comparison = json.optJSONObject("comparison")
        return AgentCalibration(json.getString("calibration_id"),json.getString("question"),answer(json.getJSONObject("locked_answer"),c),
            json.getString("locked_at"),json.getString("lock_digest"),json.getString("state"),
            comparison?.getJSONArray("dimension_diffs")?.objects()?.map { d -> AgentDiff(d.getString("dimension"),d.getString("assessment"),d.getString("reason")) }.orEmpty(),
            if (json.isNull("resulting_revision")) null else json.getInt("resulting_revision"), json.nullableString("human_answer"))
    }
    private fun parsePlan(json: JSONObject) = AgentPlan(json.getString("question"),json.getString("reason"))
    private suspend fun materials(c: BackendConnection) = gateway.request(c, "/evidence")
        .getJSONArray("materials").objects().map { evidence(it) }
    private fun evidence(json: JSONObject) = AgentEvidence(json.getString("evidence_id"), json.getString("excerpt"),
        json.getString("source_type"), json.getString("source_ref"), json.nullableString("episode_id"), json.optString("observed_at"))
}
private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
private fun JSONObject.nullableString(key: String): String? = if (isNull(key)) null else getString(key)
