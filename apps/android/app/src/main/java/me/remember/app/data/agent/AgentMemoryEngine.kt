package me.remember.app.data.agent

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** One owner per subject/store. New material is durable before derived workers run. */
class AgentMemoryEngine(private val subjectId: String, private val store: AgentJournalStore,
    private val client: StructuredAgentModel) {
    private val mutex = Mutex()
    private val inference = AgentInference(client)
    private val psychology = PsychologicalLearner(client)
    private val observer = MemoryObservationExtractor(client)
    @Volatile private var state = store.read() ?: JSONObject().put("version", 1).put("subject_id", subjectId)
        .put("revision", 0).put("memory_revision", 0).put("model_version", "unconfigured")
        .put("materials", JSONArray()).put("traits", JSONArray()).put("history", JSONArray())
        .put("calibrations", JSONArray()).put("episodes", JSONArray()).put("withdrawn_evidence", JSONArray())
    init {
        require(subjectId.isNotBlank() && state.getString("subject_id") == subjectId) { "记忆库所属人物不匹配。" }
        check(state.getInt("version") == 1) { "记忆库版本不兼容，请使用兼容版本；原始数据未被覆盖。" }
    }
    private fun persist(next: JSONObject) { store.write(next); state = next.copyJson() }
    private fun withdrawn() = state.getJSONArray("withdrawn_evidence").strings().toSet()
    private fun materials() = JSONArray(state.getJSONArray("materials").objects().filter { it.getString("evidence_id") !in withdrawn() })
    private fun activeHabits() = JSONArray(state.optJSONArray("habits")?.objects().orEmpty().filter { h ->
        val allowed = materials().objects().map { it.getString("evidence_id") }.toSet()
        h.getJSONArray("evidence_ids").strings().all(allowed::contains)
    })
    private fun model() = JSONObject().put("subject_id", subjectId).put("revision", state.getInt("revision"))
        .put("memory_revision", state.optInt("memory_revision")).put("model_version", state.getString("model_version"))
        .put("schema_version", "agent-loop-v0.2-experimental")
        .put("traits", JSONArray(state.getJSONArray("traits").objects().filter { t -> t.getJSONArray("evidence_ids").strings().none { it in withdrawn() } }))
    fun pending() = state.optJSONObject("job")?.copyJson()
    fun portrait() = projectPortrait(state)
    fun snapshot() = model().copyJson()
    fun originalMaterials() = JSONArray(materials().toString())
    private fun dimensions() = MemoryDimensionRegistry.dimensions.map { it.id }.toSet()
    private fun requireConsent(granted: Boolean) { require(granted) { "需要明确同意后才会调用模型。" } }

    suspend fun addEpisode(id: String, confirmedText: String, recordedAt: String, consent: Boolean,
        rawTranscript: String = confirmedText, recordingRef: String = id) = withContext(Dispatchers.IO) { mutex.withLock {
        requireConsent(consent)
        require(id.isNotBlank() && id.length <= 200 && recordingRef.length <= 200 &&
            confirmedText.isNotBlank() && confirmedText.length <= 100_000 && rawTranscript.length <= 100_000)
        java.time.Instant.parse(recordedAt)
        val episode = state.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }
        if (episode != null) {
            check(!episode.optBoolean("withdrawn")) { "原材料已撤除，不能重新引用。" }
            check(materials().objects().first { it.optString("episode_id") == id }.getString("excerpt") == confirmedText) { "原文不可覆盖，请使用新的来源版本。" }
            if (episode.optString("understanding_status") == "READY") return@withLock
        }
        if (pending() != null) {
            check(pending()?.optString("id") == id) { "请先继续或取消待处理任务。" }
        } else {
            // A re-reviewed recording replaces its earlier source, without overwriting machine ASR.
            state.getJSONArray("episodes").objects().filter { it.optString("recording_ref") == recordingRef &&
                it.getString("id") != id && !it.optBoolean("withdrawn") }.forEach { withdrawInternal(it.getString("id")) }
            begin(JSONObject().put("kind", "CAPTURE").put("id", id).put("recording_ref", recordingRef).put("recorded_at", recordedAt)
                .put("asr_transcript", rawTranscript)
                .put("evidence", evidence("ev_$id", confirmedText, "SUBJECT", id, "").put("observed_at", recordedAt)))
        }
        execute()
    } }

    suspend fun ask(question: String, consent: Boolean) = withContext(Dispatchers.IO) { mutex.withLock {
        requireConsent(consent); require(question.isNotBlank() && question.length <= 4000)
        lockAnswer(question.trim(), newId("cal_"))
    } }
    fun history() = JSONArray(state.getJSONArray("calibrations").objects().map { record -> record.copyJson().apply {
        if (getString("state") == "INVALIDATED") {
            remove("human_answer")
            getJSONObject("locked_answer").put("answer", "原材料已撤除，此回答不再可用。")
                .put("evidence", JSONArray()).put("evidence_ids", JSONArray()).put("response_type", "INSUFFICIENT")
        }
    } })
    suspend fun correct(id: String, human: String, expectedRevision: Int, consent: Boolean) = withContext(Dispatchers.IO) { mutex.withLock {
        requireConsent(consent); require(human.isNotBlank() && human.length <= 8000)
        val cal = calibration(id)
        if (cal.getString("state") == "COMPLETED") {
            require(cal.getString("human_answer") == human.trim()) { "此回答已有校正，请重新提问。" }
            return@withLock cal.copyJson()
        }
        val locked = cal.getJSONObject("locked_answer")
        check(cal.getString("state") == "LOCKED" && expectedRevision == state.getInt("revision") && locked.getInt("revision") == expectedRevision &&
            locked.getInt("memory_revision") == state.optInt("memory_revision")) { "理解或原材料已变化，请重新提问。" }
        begin(JSONObject().put("kind", "CORRECT").put("id", id).put("human_answer", human.trim())
            .put("evidence", evidence(newId("cev_"), human.trim(), "CALIBRATION", null, cal.getString("question"))
                .put("source_ref", "calibration:$id").put("related_evidence_ids", JSONArray(answerRoots(locked)))))
        execute()
    } }
    suspend fun retry(consent: Boolean) = withContext(Dispatchers.IO) { mutex.withLock {
        requireConsent(consent); if (pending() != null) execute()
    } }
    suspend fun cancelPending() = withContext(Dispatchers.IO) { mutex.withLock {
        val next = state.copyJson()
        next.optJSONObject("job")?.let { job -> if (job.getString("kind") == "CAPTURE") {
            publishMaterial(next, job); publishEpisode(next, job, "PENDING")
        } }
        next.remove("job"); persist(next)
    } }
    suspend fun withdrawEpisode(id: String) = withContext(Dispatchers.IO) { mutex.withLock {
        check(pending() == null) { "请先继续或取消待处理任务。" }; withdrawInternal(id)
    } }
    suspend fun deleteEpisode(id: String) = withContext(Dispatchers.IO) { mutex.withLock {
        check(pending() == null) { "请先继续或取消待处理任务。" }
        val next = eraseRecording(state, id)
        next.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }
            ?.apply { put("withdrawn", true); put("deleted", true); remove("asr_transcript") }
        persist(next)
    } }
    private fun begin(job: JSONObject) {
        check(pending() == null) { "请先继续或取消待处理任务。" }
        persist(state.copyJson().put("job", job.put("started_at", now()).put("attempts", 0)))
    }
    private suspend fun execute(): JSONObject {
        var job = checkNotNull(pending())
        job.put("attempts", job.getInt("attempts") + 1).put("status", "RUNNING").remove("error")
        persist(state.copyJson().put("job", job))
        try {
            // Raw evidence is committed independently of all derived model stages.
            persist(state.copyJson().apply {
                publishMaterial(this, job)
                if (job.getString("kind") == "CAPTURE") publishEpisode(this, job, "PENDING")
            })
            val source = job.getJSONObject("evidence")
            val full = source.getString("excerpt")
            val enabled = dimensions()
            val relatedIds = source.optJSONArray("related_evidence_ids")?.strings()?.toSet() ?: state.getJSONArray("calibrations").objects()
                .firstOrNull { source.getString("source_ref") == "calibration:${it.getString("calibration_id")}" }
                ?.getJSONObject("locked_answer")?.let(::answerRoots).orEmpty()
            val relatedObservations = JSONArray(state.optJSONArray("observations")?.objects().orEmpty().filter {
                source.getString("source_type") == "CALIBRATION" && it.getString("evidence_id") in relatedIds && it.optString("status", "ACTIVE") == "ACTIVE" })
            while (job.optInt("observation_offset") < full.length) {
                val offset = job.optInt("observation_offset")
                val batch = observer.extract(source, offset, enabled, relatedObservations)
                val accumulated = job.optJSONArray("observations") ?: JSONArray()
                batch.objects().forEach(accumulated::put)
                job.put("observations", accumulated).put("observation_offset", offset + sourceChunk(full, offset).length)
                persist(state.copyJson().put("job", job))
            }
            val observations = job.optJSONArray("observations") ?: JSONArray()
            persist(state.copyJson().apply {
                val previous = optJSONArray("observations")?.objects().orEmpty().filter { it.getString("evidence_id") != source.getString("evidence_id") }
                observations.objects().forEach { current ->
                    val replaces = current.optJSONArray("replaces")?.strings().orEmpty()
                    previous.filter { it.getString("observation_id") in replaces }.forEach { old ->
                        old.put("status", "SUPERSEDED").put("superseded_by", current.getString("observation_id"))
                    }
                }
                put("observations", JSONArray(previous + observations.objects())).put("portrait_status", "BUILDING")
            })
            val chunks = evidenceSpans(source)
            while (job.optInt("trait_chunks") < chunks.size) {
                val chunk = chunks[job.optInt("trait_chunks")]
                val newObservations = JSONArray(observations.objects().filter { !chunk.has("span_start") ||
                    it.getInt("start") < chunk.getInt("span_end") && it.getInt("end") > chunk.getInt("span_start") })
                val related = AgentEvidenceIndex(JSONArray(materials().objects().filter { it.getString("evidence_id") != source.getString("evidence_id") }),
                    state.optJSONArray("observations") ?: JSONArray()).retrieve(newObservations.objects().joinToString(" ") { it.getString("summary") }, fallback = false)
                val input = JSONArray(related.objects()).put(chunk)
                val current = model().put("traits", job.optJSONArray("traits") ?: model().getJSONArray("traits"))
                job.put("traits", inference.understand(current, input, newObservations)).put("trait_chunks", job.optInt("trait_chunks") + 1)
                persist(state.copyJson().put("job", job))
            }
            if (!job.has("habits")) {
                val psychologyIds = state.optJSONArray("observations")?.objects().orEmpty().filter {
                    it.getString("dimension") in setOf("psychological", "mood") }.map { it.getString("evidence_id") }.toSet() +
                    activeHabits().objects().flatMap { it.getJSONArray("evidence_ids").strings() } + source.getString("evidence_id")
                val input = JSONArray(materials().objects().filter { it.getString("evidence_id") in psychologyIds || it.getString("source_type") == "CALIBRATION" })
                job.put("habits", psychology.learn(job.getJSONArray("traits"), input, activeHabits()))
                persist(state.copyJson().put("job", job))
            }
            val next = state.copyJson()
            next.getJSONArray("history").put(model())
            publishMaterial(next, job)
            next.put("traits", job.getJSONArray("traits")).put("habits", job.getJSONArray("habits"))
                .put("portrait_status", "READY").put("portrait_memory_revision", state.optInt("memory_revision"))
                .put("revision", state.getInt("revision") + 1).put("model_version", client.modelVersion).remove("job")
            var result = JSONObject()
            if (job.getString("kind") == "CORRECT") {
                result = next.getJSONArray("calibrations").objects().first { it.getString("calibration_id") == job.getString("id") }
                result.put("state", "COMPLETED").put("resulting_revision", next.getInt("revision")).put("human_answer", job.getString("human_answer"))
            } else if (job.getString("kind") == "CAPTURE") publishEpisode(next, job, "READY")
            persist(next)
            return result
        } catch (e: Exception) {
            job = checkNotNull(pending())
            persist(state.copyJson().put("portrait_status", "FAILED")
                .put("job", job.put("status", "PAUSED").put("error", "任务未完成，可继续；已保存的材料保留。")))
            throw e
        }
    }
    private fun publishMaterial(next: JSONObject, job: JSONObject) {
        val evidence = job.getJSONObject("evidence")
        if (next.getJSONArray("materials").objects().none { it.getString("evidence_id") == evidence.getString("evidence_id") }) {
            next.put("memory_revision", next.optInt("memory_revision") + 1).put("portrait_status", "PENDING")
        }
        next.put("materials", JSONArray(next.getJSONArray("materials").objects().filter { it.getString("evidence_id") != evidence.getString("evidence_id") }).put(evidence))
    }
    private fun publishEpisode(next: JSONObject, job: JSONObject, status: String) {
        next.put("episodes", JSONArray(next.getJSONArray("episodes").objects().filter { it.getString("id") != job.getString("id") })
            .put(job.copyJson().apply { remove("evidence"); remove("traits"); remove("habits"); remove("observations"); put("understanding_status", status)
                if (status == "READY") put("observation_version", MemoryDimensionRegistry.version) }))
    }
    private suspend fun lockAnswer(question: String, id: String): JSONObject {
        state.getJSONArray("calibrations").objects().firstOrNull {
            val locked = it.getJSONObject("locked_answer")
            it.getString("state") == "LOCKED" && it.getString("question") == question &&
                locked.getInt("revision") == state.getInt("revision") && locked.getInt("memory_revision") == state.optInt("memory_revision")
        }?.let { return it.copyJson() }
        val pack = AgentEvidenceIndex(materials(), state.optJSONArray("observations") ?: JSONArray()).retrieve(question)
        val answer = inference.answer(question, model(), pack, activeHabits())
        val cal = JSONObject().put("calibration_id", id).put("question", question).put("locked_answer", answer)
            .put("locked_at", now()).put("lock_digest", stableDigest(answer.toString())).put("state", "LOCKED").put("resulting_revision", JSONObject.NULL)
        persist(state.copyJson().apply { getJSONArray("calibrations").put(cal) })
        return cal
    }
    private fun calibration(id: String) = state.getJSONArray("calibrations").objects().first {
        it.getString("calibration_id") == id
    }
    private fun withdrawInternal(id: String): JSONObject {
        val episode = state.getJSONArray("episodes").objects().first { it.getString("id") == id }
        if (episode.optBoolean("withdrawn")) return model()
        val next = state.copyJson()
        val removed = withdrawn().toMutableSet()
        next.getJSONArray("materials").objects().filter { it.optString("episode_id") == id }.forEach { removed.add(it.getString("evidence_id")) }
        // Propagate only along provenance edges. Keep unrelated records and revision history.
        var changed: Boolean
        do {
            changed = false
            next.getJSONArray("calibrations").objects().forEach { cal ->
                if (answerRoots(cal.getJSONObject("locked_answer")).any { it in removed }) {
                    cal.put("state", "INVALIDATED")
                    next.getJSONArray("materials").objects().filter { it.getString("source_ref") == "calibration:${cal.getString("calibration_id")}" }
                        .forEach { if (removed.add(it.getString("evidence_id"))) changed = true }
                }
            }
        } while (changed)
        next.put("withdrawn_evidence", JSONArray(removed)).put("revision", next.getInt("revision") + 1)
            .put("memory_revision", next.optInt("memory_revision") + 1).put("portrait_status", "PENDING")
        next.getJSONArray("episodes").objects().firstOrNull { it.getString("id") == id }?.put("withdrawn", true)
        persist(next)
        return model()
    }
    private fun evidence(id: String, text: String, source: String, episode: String?, context: String) = JSONObject()
        .put("evidence_id", id).put("excerpt", text).put("source_type", source).put("episode_id", episode ?: JSONObject.NULL)
        .put("source_ref", if (episode != null) "episode:$episode" else "calibration:$id")
        .put("context", context).put("observed_at", now()).put("speaker_authority", "SELF_ATTESTED")
}
