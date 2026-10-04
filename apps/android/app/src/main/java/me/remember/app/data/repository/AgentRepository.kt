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
            AgentUiState(configured = true, snapshot = snapshot(gateway.request(c, "/model"), c))
        }
    }

    suspend fun refresh() = operation { c ->
        val model = snapshot(gateway.request(c, "/model/refresh", "POST"), c)
        mutableState.value.copy(snapshot = model, plan = parsePlan(gateway.request(c, "/plan")))
    }

    suspend fun ask(question: String) = operation { c ->
        mutableState.value.copy(answer = answer(gateway.request(c, "/twin", "POST", JSONObject().put("question", question)), c))
    }

    suspend fun lock(question: String) = operation { c ->
        val calibration = calibration(gateway.request(c, "/calibrations", "POST", JSONObject().put("question", question)), c)
        mutableState.value.copy(calibration = calibration)
    }

    suspend fun resume(calibrationId: String) = operation { c ->
        require(calibrationId.matches(Regex("[A-Za-z0-9._~-]+")))
        mutableState.value.copy(calibration = calibration(gateway.request(c, "/calibrations/$calibrationId"), c))
    }

    suspend fun submit(humanAnswer: String) = operation { c ->
        val current = checkNotNull(mutableState.value.calibration) { "请先锁定 Twin 答案。" }
        val latest = snapshot(gateway.request(c, "/model"), c)
        val completed = calibration(gateway.request(c, "/calibrations/${current.id}/submit", "POST", JSONObject()
            .put("human_answer", humanAnswer).put("expected_revision", latest.revision)), c)
        mutableState.value.copy(calibration = completed, snapshot = snapshot(gateway.request(c, "/model"), c),
            plan = parsePlan(gateway.request(c, "/plan")), answer = null)
    }

    suspend fun plan() = operation { c -> mutableState.value.copy(plan = parsePlan(gateway.request(c, "/plan"))) }

    suspend fun inspect(evidenceId: String) = operation { c ->
        require(evidenceId.matches(Regex("[A-Za-z0-9._~-]+")))
        val e = gateway.request(c, "/evidence/$evidenceId")
        mutableState.value.copy(inspectedEvidence = AgentEvidence(e.getString("evidence_id"),
            e.getString("excerpt"), e.getString("source_type"), e.getString("source_ref"), e.nullableString("episode_id")))
    }

    suspend fun revoke() = operation { c ->
        gateway.request(c, "/grant", "DELETE")
        AgentUiState(configured = false)
    }

    suspend fun withdraw(episodeId: String) = operation { c ->
        require(episodeId.matches(Regex("[A-Za-z0-9._~-]+")))
        mutableState.value.copy(snapshot = snapshot(gateway.request(c, "/episodes/$episodeId/use", "DELETE"), c),
            answer = null, calibration = null, inspectedEvidence = null)
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
        val evidence = json.getJSONArray("evidence").objects().map { e -> AgentEvidence(e.getString("evidence_id"),
            e.getString("excerpt"),e.getString("source_type"),e.getString("source_ref"),e.nullableString("episode_id")) }
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
            if (json.isNull("resulting_revision")) null else json.getInt("resulting_revision"))
    }
    private fun parsePlan(json: JSONObject) = AgentPlan(json.getString("question"),json.getString("reason"))
}
private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
private fun JSONObject.nullableString(key: String): String? = if (isNull(key)) null else getString(key)
